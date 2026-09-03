#!/usr/bin/env python3
"""Notion ページ1枚のローカル正本を、セッションのトランスクリプトから作る／照合する。

なぜ要るか
----------
Notion MCP のコネクタは OAuth なのでローカルに API トークンがなく、ページ本文を
ファイルへ落とす手段がモデルの打ち直ししかない。それは日本語が化ける操作そのもの。

ところが MCP のツール結果はセッションのトランスクリプト（JSONL）に逐語で残っている。
そこから抜き出せば、モデルの出力を一切経由せずに Notion の現行内容をローカルへ落とせる。

使い方
------
  sh python.sh notion_mirror.py pull --page <ID or URL> --out <file>   # fetch 結果をファイルへ
  sh python.sh notion_mirror.py diff --page <ID or URL> --file <file>  # ローカル正本と fetch 結果を照合

どちらも **先に notion-fetch でそのページを取得しておく**（最新状態が要るなら取り直す）。
同じページが複数回 fetch されていれば最後（＝最新）を採用する。

diff の読み方（⚠️ DIRTY は「止まれ」ではない）
--------------------------------------------
DIRTY の意味は「ローカルと Notion が違う」だけ。運用は必ず「ローカル正本を編集してから
書き戻す」ので、**編集したページが DIRTY になるのは正常**。判定はラベルではなく差分の中身：

  - 差分が自分の編集だけ           → そのまま書き戻す
  - 自分がやっていない変更が混じる → Notion 側で誰かが直した。止まる。pull し直して編集を積み直す
  - 見覚えのない古い本文が出る     → 比較相手が古い fetch。fetch し直す

差分行のラベル（difflib の tag は [] に併記する）。tag は a（＝ローカル）基準で付くので、
**`delete` が自分の追記、`insert` が書き戻すと消える側**になる。逆に読まない：

  - 追記(ローカルのみ)      [delete]  ローカルにあって Notion にない  → 自分の追記。安全側
  - ⚠️消える(Notionのみ)    [insert]  Notion にあってローカルにない  → 書き戻すと消える。読む
  - ⚠️食い違い              [replace] 両側にあって内容が違う          → 要確認

チェックボックスは ☐（未チェック）/ ☑（チェック済み）に畳んで比較する。
チェックのオンオフだけが変わった項目は **⚠️食い違い [replace]** として
`ローカル='☐' / Notion='☑'` の形で出る。Notion 側で誰かがチェックを入れた合図。

終了コード 1 は **エラーではなく「差分を読め」の合図**（DIRTY と STALE の両方で 1）。
2 以上は本物の失敗（argparse の 2、_die が出す 3＝ページ ID 不正・ローカル正本不在・
トランスクリプト不在）。

CLEAN でも DIRTY でも **必ず 1 行は出す**。だから出力が空なら、それは「差分なし」ではなく
このスクリプトが走らなかったということ（インタプリタ不在・リダイレクト失敗など）。空を
CLEAN と読むと、書き戻しを止める唯一のゲートが黙って開く（#31）。

実装上の落とし穴（実際に踏んだもの）
------------------------------------
- ツール結果は「JSON 文字列の中の JSON 文字列」で二重にエンコードされている。
- ページ ID は他ページの <ancestor-path> や本文末尾の子ページリンクにも出てくる。
  最初の <page url=...> がそのページ自身なので、そこで判定する。
- サブエージェントの fetch 結果は親の JSONL に入らず <session>/subagents/agent-*.jsonl に残る。
- 出力上限を超えた fetch 結果は <session>/tool-results/*.txt に退避される。
  大きいページほどここに落ちるので、見ないと「fetch したのに STALE」になる。
- 退避ファイルの探索は**当該セッションのディレクトリに限定**する。プロジェクト全体を
  glob すると過去セッションの古い本文を掴み、「古いアンカーで上書き」事故の入口になる。
- Notion は保存時に「ドットを含む英数字トークン」を自動でリンクにする
  （`notion_mirror.py` → `notion_[mirror.py](http://mirror.py)`）。放っておくと書き戻した
  直後の diff が恒久的に DIRTY になり、収束しない。normalize() で「リンクテキストと
  リンク先が一致するもの」だけを畳んで吸収する。ローカル正本側でバッククォートで
  囲めばそもそも変換されない（SKILL.md「落ちる原因（既知）」）。
- チェックボックスは **捨てずに ☐/☑ へ畳む**。かつて `[ ]` と `[x]` を両方とも
  空文字にしていたため、Notion 側で入れたチェックが diff に出ず、書き戻しで
  黙って消えていた（#36）。畳み先は「地の文に出てこない記号」であることが要件で、
  素朴に除去をやめるだけだと空白除去が `[ ]` を `[]` にして地の文と衝突する。
  なお Notion は `[X]` を `[x]` に正規化して返すので、大文字はローカル側にしか
  現れない。吸収しないとローカルに `[X]` と書いた瞬間に恒久 DIRTY になる。
"""
import argparse
import json
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

CONTENT_RE = re.compile(r"<content>\n?(.*?)\n?</content>", re.S)
FIRST_PAGE_RE = re.compile(r'<page url="https://app\.notion\.com/p/([0-9a-f]{32})"')
FIRST_PAGE_ESC_RE = re.compile(r'<page url=\\"https://app\.notion\.com/p/([0-9a-f]{32})\\"')
PAGE_ID_RE = re.compile(r"[0-9a-f]{32}")


# --- 失敗の出し方 --------------------------------------------------------------

# 本物の失敗の終了コード。1 は DIRTY / STALE（＝「差分を読め」の合図）で埋まっており、
# 2 は argparse と python.sh のインタプリタ不在が使っている。呼び出し側が「照合が
# 済んだ上での DIRTY」と「そもそも照合できていない」を区別できるよう、別の番号にする。
EXIT_ERROR = 3


def _die(message: str) -> None:
    """本物の失敗。報告する語を先頭の印から決められるよう ERROR: を前に置く（#31）。"""
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(EXIT_ERROR)


# --- ページ ID ----------------------------------------------------------------

def normalize_page_id(value: str):
    """URL・ハイフン付き UUID・32 桁 hex のどれを渡されても 32 桁 hex にする。形式外なら None。"""
    s = (value or "").strip().replace("-", "").lower()
    m = PAGE_ID_RE.search(s)
    return m.group(0) if m and len(s) >= 32 else None


# --- トランスクリプトの所在 ----------------------------------------------------

def codex_transcript() -> Optional[Path]:
    """Codex の現在の rollout をセッション ID から特定する。

    `transcript_path` が使える呼び出し元は --transcript / 環境変数で明示するのが第一選択。
    通常コマンドでは、Codex がプロセスへ渡すセッション ID と一致する rollout だけを選ぶ。
    ID やファイルが見つからない、または複数一致する場合は推測せず None を返す。
    """
    root = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
    session_id = os.environ.get("CODEX_SESSION_ID") or os.environ.get("CODEX_THREAD_ID")
    if not session_id or not re.fullmatch(r"[0-9a-f-]+", session_id):
        return None
    candidates = list((root / "sessions").glob(f"**/*{session_id}.jsonl"))
    return candidates[0] if len(candidates) == 1 else None

def project_dir(cwd: str = None) -> Path:
    """Claude Code のトランスクリプト置き場。環境変数 NOTION_MIRROR_PROJECT_DIR で上書き可。

    Claude Code は ~/.claude/projects/<cwd の英数字以外を '-' にした名前>/ に置く。
    ⚠️ 絶対パスをベタ書きしない——マウント先が変わる環境（Cowork のデバイスブリッジ等）で止まる。
    """
    env = os.environ.get("NOTION_MIRROR_PROJECT_DIR")
    if env:
        return Path(env)
    cwd = cwd or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(Path(cwd).resolve()))
    return Path.home() / ".claude" / "projects" / slug


def session_transcript(pdir: Path) -> Path:
    """**このセッションの**トランスクリプト。

    ⚠️ mtime で「最新」を選ぶと、別セッションが同時に動いているとそちらを掴む。
    照合相手が知らないセッションの古い fetch にすり替わるのは、ミラー方式で唯一防ぎたい
    事故（Notion 側の変更を見落として古いローカル正本で上書き）に直結する。
    Claude Code が渡す CLAUDE_CODE_SESSION_ID を最優先し、無いときだけ mtime に落ちる。
    """
    sid = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if sid:
        path = pdir / f"{sid}.jsonl"
        if path.exists():
            return path
    files = sorted(pdir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not files:
        _die(f"トランスクリプトが見つからない: {pdir}"
             "（--transcript で指定するか、NOTION_MIRROR_PROJECT_DIR を設定する）")
    return files[-1]


def transcript_chain(base: Path) -> list:
    """harvest 対象（本体＋サブエージェント）を mtime 昇順で返す。呼び出し側は後勝ちで update する。"""
    files = [base]
    subdir = base.parent / base.stem / "subagents"
    if subdir.is_dir():
        files += list(subdir.glob("*.jsonl"))
    return sorted(files, key=lambda p: p.stat().st_mtime)


# --- 抽出 ---------------------------------------------------------------------

def walk_strings(obj, depth=0):
    """入れ子の JSON 文字列も追いかけて、あらゆる文字列を吐き出す。"""
    if isinstance(obj, str):
        yield obj
        if depth < 4:
            head = obj.lstrip()[:1]
            if head in "{[":
                try:
                    yield from walk_strings(json.loads(obj), depth + 1)
                except (json.JSONDecodeError, ValueError):
                    pass
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from walk_strings(v, depth)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v, depth)


def harvest(transcript: Path) -> dict:
    """トランスクリプト1本から {page_id: (line_no, content)} を集める（全ページ）。"""
    found = {}
    with transcript.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            if "<content>" not in line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            for s in walk_strings(rec):
                if "<content>" not in s:
                    continue
                pm = FIRST_PAGE_RE.search(s)
                cm = CONTENT_RE.search(s)
                if pm and cm:
                    found[pm.group(1)] = (line_no, cm.group(1))
    return found


def harvest_tool_results(session_dir: Path) -> dict:
    """出力上限を超えて <session>/tool-results/*.txt に退避された fetch 結果を拾う。

    退避ファイルは生テキストで、<content> の中身が \\n エスケープのまま入っていることがある。
    両方の形を試してデコードできたほうを採る。
    """
    found = {}
    if not session_dir.is_dir():
        return found
    for path in sorted(session_dir.glob("tool-results/*.txt"), key=lambda p: p.stat().st_mtime):
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "<content>" not in raw:
            continue
        content = None
        m = re.search(r"<content>\\n?(.*?)\\n?</content>", raw, re.S)
        if m:
            try:
                content = (m.group(1).encode().decode("unicode_escape")
                           .encode("latin1").decode("utf-8"))
            except (UnicodeDecodeError, UnicodeEncodeError):
                content = None
        if content is None:
            m = re.search(r"<content>\n?(.*?)\n?</content>", raw, re.S)
            content = m.group(1) if m else None
        if content is None:
            continue
        pm = FIRST_PAGE_RE.search(raw) or FIRST_PAGE_ESC_RE.search(raw)
        if pm:
            found[pm.group(1)] = (f"tool-results/{path.name}", content)
    return found


def harvest_session(transcript: Path = None, cwd: str = None) -> tuple:
    """このセッションで fetch されたページを全経路からまとめて集める。

    ⚠️ 探索先はここ一箇所に集約する（フックと mirror が別々に探すと食い違う）。
    返り値は (found, chain)。found は {page_id: (出所, 本文)}。
    退避ファイル → 本体 → サブエージェント の順に入れ、後から入ったものが勝つ。
    """
    explicit = os.environ.get("NOTION_MIRROR_TRANSCRIPT")
    base = transcript or (Path(explicit) if explicit else None) or codex_transcript()
    if base is None:
        base = session_transcript(project_dir(cwd))
    if not base.is_file():
        _die(f"トランスクリプトが見つからない: {base}")
    session_dir = base.parent / base.stem
    found = dict(harvest_tool_results(session_dir))
    chain = transcript_chain(base)
    for path in chain:
        for page_id, (line_no, content) in harvest(path).items():
            found[page_id] = (f"{path.name} 行{line_no}", content)
    return found, chain


# --- 照合 ---------------------------------------------------------------------

def normalize(text: str) -> str:
    """マークアップと空白を落とす。fetch 結果と内部保存には整形差があり、素朴な比較は誤検出だらけ。"""
    text = re.sub(r"<[^>]+>", "", text)      # <table_of_contents/> 等のタグ
    text = text.replace("\\", "")            # markdown エスケープ
    # Notion は保存時に「ドットを含む英数字トークン」を自動でリンクにする
    # （notion_mirror.py → notion_[mirror.py](http://mirror.py)）。
    # リンクテキストとリンク先が一致するものだけを畳む。テキストと URL が違う
    # 「手で貼った本物のリンク」は畳まないので、それを消す編集は差分に残る。
    # 🔴 残すのは \1（リンクテキストそのまま）。スキームを外した \2 を残すと
    # [https://example.com](https://example.com) が example.com に畳まれ、
    # ローカル正本側の素の https://example.com と一致しなくなる。
    text = re.sub(r"\[((?:https?://)?([^\]]+?))\]\((?:https?://)?\2/?\)", r"\1", text)
    # チェックの有無は飾りではなく**内容**。捨てると Notion 側で入れたチェックを
    # 書き戻しで消しても diff が CLEAN になり、唯一のゲートが黙って開く（#36）。
    # 🔴 捨てずに「地の文に出てこない記号」へ畳む。空白除去より**前**に置く——
    # 後だと [ ] の中の空白が先に消えて [] になり、地の文の [] と区別できない。
    # リンク畳み込みより**後**に置く——[x](x) のような「テキストと URL が一致する
    # 本物のリンク」を先にリンクとして処理させるため。
    # 大文字 [X] も畳む。Notion は保存時に [x] へ正規化して返すので大文字は
    # ローカル側にしか現れず、吸収しないと書いた瞬間に恒久 DIRTY になる（実測）。
    text = re.sub(r"\[[xX]\]", "☑", text)
    text = re.sub(r"\[ \]", "☐", text)
    text = re.sub(r"[*#>|\-\t \n　​]", "", text)
    return text


# difflib の tag は a（＝ローカル）基準。`delete` は自分の追記、`insert` が書き戻すと
# 消える側になる。英単語のままだと逆に読まれる（#6）ので、意味を前に置いて出す。
# 生の tag は [] で併記して残す（grep と既存の読み方を切らないため）。
DIFF_LABELS = {
    "delete":  "追記(ローカルのみ)",
    "insert":  "⚠️消える(Notionのみ)",
    "replace": "⚠️食い違い",
}


def compare(local: str, remote: str, label: str, context: int = 30) -> bool:
    a, b = normalize(local), normalize(remote)
    sm = SequenceMatcher(None, a, b, autojunk=False)
    diffs = [op for op in sm.get_opcodes() if op[0] != "equal"]
    if not diffs:
        print(f"CLEAN: {label}（正規化後 {len(a):,} 文字が一致）")
        return True
    print(f"DIRTY: {label} — {len(diffs)} 件の差分。"
          "追記(ローカルのみ)=自分の編集なら正常。"
          "⚠️消える(Notionのみ)/⚠️食い違い=書き戻すと失われる側なので必ず読む")
    for tag, i1, i2, j1, j2 in diffs[:20]:
        print(f"  - {DIFF_LABELS.get(tag, tag)} [{tag}]: "
              f"ローカル={a[i1:i2]!r} / Notion={b[j1:j2]!r}")
        print(f"    文脈 ローカル: …{a[max(0, i1 - context):i2 + context]}…")
        print(f"    文脈 Notion  : …{b[max(0, j1 - context):j2 + context]}…")
    if len(diffs) > 20:
        print(f"  （ほか {len(diffs) - 20} 件）")
    return False


# --- CLI ----------------------------------------------------------------------

def _lookup(args):
    page_id = normalize_page_id(args.page)
    if not page_id:
        _die(f"ページ ID の形式が不正: {args.page!r}（URL か 32 桁の hex を渡す）")
    found, chain = harvest_session(args.transcript)
    return page_id, found.get(page_id), chain


def cmd_pull(args) -> int:
    page_id, hit, chain = _lookup(args)
    if hit is None:
        print(f"STALE: {page_id} — このセッションに fetch がない。notion-fetch してから再実行する")
        print("  探索したトランスクリプト: " + ", ".join(p.name for p in chain))
        return 1
    origin, content = hit
    out = Path(args.out)
    old = len(out.read_text(encoding="utf-8")) if out.exists() else 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content + "\n", encoding="utf-8")
    delta = f"旧{old:,}字" if old else "新規"
    print(f"OK  : {out} <- {origin}, {len(content):,}字, {delta}")
    return 0


def cmd_diff(args) -> int:
    page_id, hit, chain = _lookup(args)
    path = Path(args.file)
    if not path.exists():
        _die(f"ローカル正本がない: {path}（先に pull する）")
    if hit is None:
        print(f"STALE: {page_id} — このセッションに fetch がない。notion-fetch してから再実行する")
        print("  探索したトランスクリプト: " + ", ".join(p.name for p in chain))
        return 1
    clean = compare(path.read_text(encoding="utf-8"), hit[1], str(path))
    if not clean:
        print("⚠️ DIRTY は「書き戻すな」ではない。編集済みなら DIRTY が正常。"
              "読むのは ⚠️消える(Notionのみ) と ⚠️食い違い"
              "（＝Notion 側にしかない＝書き戻すと消える）")
    # 終了コードは「人が差分を読んだか」を代弁できないので、DIRTY と STALE を 1 にする。
    return 0 if clean else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--transcript", type=Path, default=None,
                    help="本体トランスクリプト（省略時は Codex のセッション ID / CLAUDE_CODE_SESSION_ID / 最新）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pull", help="fetch 結果をローカル正本へ書き出す")
    p.add_argument("--page", required=True, help="ページ ID または URL")
    p.add_argument("--out", required=True, help="書き出し先ファイル")
    p.set_defaults(func=cmd_pull)
    d = sub.add_parser("diff", help="ローカル正本と fetch 結果を照合する")
    d.add_argument("--page", required=True, help="ページ ID または URL")
    d.add_argument("--file", required=True, help="ローカル正本ファイル")
    d.set_defaults(func=cmd_diff)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
