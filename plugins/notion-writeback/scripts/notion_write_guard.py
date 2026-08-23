#!/usr/bin/env python3
"""Notion 書き込みガード（PreToolUse フック）。

notion-update-page の呼び出しを実行前に検査する。目的は 4 つ。

1. **ページ ID の形式検査** — 空・32 桁 hex でない ID を止める（打ち間違いの最低限の防波堤）。
2. **update_content の抑制** — 1 回に複数置換をまとめない／1 ページ 3 回まで、を deny で強制する。
   「ルールを読んで従う」は繰り返し破られたので、意図ではなくフックで止める。
3. **@@FILE: センチネル注入** — replace_content の new_str / insert_content の content に
   `@@FILE:<プロジェクト相対パス>@@` と書くと、このフックがファイル実体を読んで引数に差し替える。
   ページ全文がモデルの出力を一切経由しないので、化け・転記ミス・記憶からの捏造が
   原理的に起きない。数万字ページの「正確に転記できない」問題の恒久対策。
4. **fetch していないページへの update_content の拒否** — old_str は Notion の**現物**と
   一致していなければならない。fetch していなければ古いローカル正本からアンカーを取ることに
   なり、マッチしなかった置換は**静かにスキップされる**。「書き戻し直前に必ず fetch」を
   機械的に強制する。
   🔴 **この検査を replace_content 側に付けてはいけない。** 安全な側の道を重くすると、
   記録されている逃げ先（update_content 連打）へ押し出すことになる——
   実測でも連打に逃げた回は「マッチ失敗 7 回・化け 2 件・fetch 連発・未解決 1 件」で、
   **fetch は減らずに増えた**。

方針：判定できないときは素通し（フェイルオープン）。フックの故障で書き込みを止めない。
状態：<tmpdir>/claude-notion-guard/<session_id>.json にページ別の update_content 回数を持つ。
"""
import json
import os
import re
import sys
import tempfile

UPDATE_LIMIT = 3  # 1 ページ・1 セッションあたりの update_content 呼び出し上限
STATE_DIR = os.path.join(tempfile.gettempdir(), "claude-notion-guard")
SENTINEL = re.compile(r"\s*@@FILE:(.+?)@@\s*", re.DOTALL)
PAGE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def emit(obj):
    # Windows の既定ロケール（cp932）では、注入する本文の絵文字（✅🔴 等）が
    # print() で UnicodeEncodeError になり、フックが**出力なしで異常終了**する。
    # Claude Code は出力の無いフックを「意見なし」として素通しするため、
    # 注入されないまま @@FILE:...@@ が本文になる（実際に起きた事故）。
    # stdout のエンコーディングに依存せず、UTF-8 バイト列を直接書く。
    payload = json.dumps(obj, ensure_ascii=False)
    sys.stdout.buffer.write(payload.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()
    sys.exit(0)


def deny(reason):
    emit({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    })


def fetched_this_session(data, page_id):
    """このセッション（＋そのサブエージェント）で page_id を fetch したか。

    見るのは今のセッションのトランスクリプトとその子、当該セッションの退避ファイルだけ。
    過去セッションまで見ると「古いアンカーを掴む」というまさに防ぎたい事故を通してしまう。
    判定できないときは None（＝フェイルオープン）。
    """
    try:
        from pathlib import Path
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from notion_mirror import harvest_session
        tp = data.get("transcript_path")
        base = Path(tp) if tp else None
        if base is not None and not base.exists():
            base = None
        found, _chain = harvest_session(base, data.get("cwd"))
        return page_id in found
    except BaseException:
        return None  # SystemExit（トランスクリプト不在）も含めて素通し


def main():
    try:
        # Windows の既定ロケール（cp932）で stdin を読むと、@@FILE: の
        # 日本語ファイル名が化けて「ファイルが見つからない」になる。
        # バイト列を明示的に UTF-8 として解釈する。
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        sys.exit(0)  # 入力が読めないときは素通し（フェイルオープン）

    tool = data.get("tool_name") or ""
    if "notion-update-page" not in tool:
        sys.exit(0)
    ti = data.get("tool_input") or {}
    cmd = ti.get("command")
    if cmd not in ("update_content", "replace_content", "insert_content"):
        sys.exit(0)  # update_properties 等は対象外

    # プロジェクトルート＝フック入力の cwd（無ければ CLAUDE_PROJECT_DIR、無ければカレント）。
    root = os.path.realpath(
        data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())

    # --- 1. ページ ID の形式検査 -------------------------------------------
    page_id = str(ti.get("page_id") or "").replace("-", "").lower()
    if not PAGE_ID_RE.match(page_id):
        deny(
            f"page_id の形式が不正: {page_id!r}。32 桁の hex（ハイフン可）で渡す。"
            "ID は記憶で打たず、notion-fetch の結果の <page url=...> から逐語コピーする"
        )

    # --- 3. @@FILE: センチネル注入 -----------------------------------------
    field = {"replace_content": "new_str", "insert_content": "content"}.get(cmd)
    if field:
        val = ti.get(field)
        m = SENTINEL.fullmatch(val) if isinstance(val, str) else None
        if m:
            rel = m.group(1).strip()
            path = os.path.realpath(os.path.join(root, rel))
            if not path.startswith(root + os.sep):
                deny(f"@@FILE:@@ に指定できるのはプロジェクト（{root}）内のファイルだけ: {rel}")
            if not os.path.isfile(path):
                deny(
                    f"@@FILE:@@ のファイルが見つからない: {rel}"
                    f"（プロジェクトルート {root} からの相対パスで指定する。例 @@FILE:docs/page.md@@）"
                )
            with open(path, encoding="utf-8") as f:
                content = f.read()
            # updatedInput は部分マージではなく tool_input 全体を置き換える（実測）。
            # 必ず元の入力に注入フィールドを重ねた完全な dict を返す。
            new_input = dict(ti)
            new_input[field] = content
            emit({
                "systemMessage": (
                    f"notion-guard: {rel}（{len(content):,}字）を {page_id} の "
                    f"{cmd} に注入した。内容はモデルの転記を経由していない"
                ),
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "updatedInput": new_input,
                },
            })
        sys.exit(0)  # センチネル無しの replace/insert はそのまま通常フローへ

    # --- 2. update_content の抑制 ------------------------------------------
    # 2-0. fetch していないページへの update_content を拒否する（→ 冒頭の 4.）。
    if fetched_this_session(data, page_id) is False:
        deny(
            f"ページ {page_id} をこのセッションでまだ fetch していない。"
            "update_content の old_str は Notion の現物と一致していなければならず、"
            "fetch していなければ古いローカル正本からアンカーを取ることになる"
            "（マッチしなかった置換は静かにスキップされる）。"
            "notion-fetch でそのページを取り直してから出し直すか、"
            "そもそも replace_content の new_str に @@FILE:<ローカル正本のパス>@@ と書く"
            "——そちらは現物のアンカーが要らず、転記も化けも起きない"
        )

    updates = ti.get("content_updates") or []
    if len(updates) > 1:
        deny(
            "1 回の update_content に複数置換をまとめない（マッチしなかった置換だけ"
            "静かにスキップされ、化けも出やすい）。1 件ずつに分ける。"
            "そもそも修正が 3 件を超えるなら replace_content で全文を差し替える"
        )

    os.makedirs(STATE_DIR, exist_ok=True)
    sid = data.get("session_id") or "nosession"
    state_file = os.path.join(STATE_DIR, f"{sid}.json")
    try:
        with open(state_file, encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {}
    count = int(state.get(page_id, 0))
    if count >= UPDATE_LIMIT:
        deny(
            f"ページ {page_id} への update_content はこのセッションで既に {count} 回"
            f"（上限 {UPDATE_LIMIT}）。ローカル正本を編集し、"
            "replace_content の new_str に @@FILE:<ローカル正本のパス>@@ と書いて"
            "全文を差し替える——フックがファイル実体を注入するので転記も化けも起きない"
        )
    state[page_id] = count + 1
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f)
    sys.exit(0)


if __name__ == "__main__":
    main()
