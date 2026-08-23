#!/usr/bin/env python3
"""GitHub 書き込みガード（PreToolUse フック）。

GitHub MCP の書き込み系ツールを実行前に検査し、`@@FILE:<基準ディレクトリからの相対パス>@@`
と書かれたフィールドをファイル実体に差し替える。

**なぜ必要か。** MCP 経路では本文もファイル内容も*モデルがツール引数へ転記する*。
`gh` 経路の `--body-file` が持っていた「ファイル実体がモデルの出力を一切経由しない」
という性質が失われている。実際に PR #28 で、10 ファイルの `push_files` のうち 3 ファイルで
「続けて**進めて**よい」が「続けて**進んで**よい」に置き換わった。意味の近い自然な
言い回しへ無意識に"補正"する LLM 特有の壊れ方で、**目視レビューでは検出できない。**
センチネルを使えば内容がディスク → フック → API と流れるので、化け・"補正"・
記憶からの捏造が原理的に起きない。

守る不変条件はひとつ:
    センチネルに fullmatch した文字列は、ファイル内容になるか呼び出しを止めるかの
    どちらかで、`@@FILE:...@@` のまま引数に残る道は無い。

方針:
- **注入できないなら deny（フェイルクローズ）。** ファイル不在・基準ディレクトリ外・
  読めない、はすべて拒否する。`@@FILE:...@@` という文字列がそのまま push され、
  コミットに乗るのが最悪ケースなので、注入できないなら呼び出しごと止める。
- **それ以外の判定不能は素通し（フェイルオープン）。** 入力が読めない・対象外ツール・
  センチネルが無い、ではフックの都合で書き込みを止めない。センチネルを書かなければ
  従来どおり文字列がそのまま通る（後方互換）。

🔴 **notion_write_guard.py の状態管理（呼び出し回数の上限・fetch 済み判定）は移植しない。**
issue-flow に `update_content` 濫用の相当物は無い。notion 側が身をもって記録している
「安全な側の道を重くすると、記録されている逃げ先へ押し出すことになる」がそのまま
当てはまる。将来これを"復元"しないこと。
"""
import json
import os
import re
import sys

SENTINEL = re.compile(r"\s*@@FILE:(.+?)@@\s*", re.DOTALL)

# ツール名 → (種別, ...フィールド)。
#   scalar … tool_input[field] が本文そのもの
#   array  … tool_input[list_key] の各要素の [item_key] が本文
FIELDS = {
    "push_files":            ("array", "files", "content"),
    "create_or_update_file": ("scalar", "content"),
    "issue_write":           ("scalar", "body"),
    "create_pull_request":   ("scalar", "body"),
    "merge_pull_request":    ("scalar", "commit_message"),
    "add_issue_comment":     ("scalar", "body"),
}

# 🔴 GitHub MCP に限定する。ツール名だけで判定してはいけない。
# `issue_write` / `create_pull_request` / `add_issue_comment` は GitHub 固有の名前ではなく、
# GitLab / Gitea / Forgejo など別の MCP サーバーが同名のツールを出しうる。名前だけで
# 捕まえると、このプラグインが関知しないサーバーの呼び出しにフックが割り込む。しかも
# フェイルクローズなので、空振りでは済まず**無関係な呼び出しを deny しうる。**
# ハーネスによる接頭辞の揺れ（mcp__github__... / mcp__remote-devices__github__...）は
# どちらも `github` セグメントを含むので、揺れるのは `github` の前だけ。そこだけ自由にする。
# 末尾は `$` で閉じ、FIELDS の完全一致と合わせて push_files_v2 / list_push_files を除く。
TOOL_RE = re.compile(r"mcp__.*github.*__([a-z_]+)$")

MAX_LISTED = 5  # systemMessage に列挙するファイル数の上限


def emit(obj):
    # Windows の既定ロケール（cp932）では、注入する本文の絵文字（✅🔴 等）が
    # print() で UnicodeEncodeError になり、フックが**出力なしで異常終了**する。
    # Claude Code は出力の無いフックを「意見なし」として素通しするため、
    # 注入されないまま @@FILE:...@@ が本文になる（notion 側で実際に起きた事故）。
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


def resolve(rel, root, where):
    """センチネルのパスをファイル内容へ解決する。解決できなければ deny する。"""
    path = os.path.realpath(os.path.join(root, rel))
    # realpath 済み同士で比較するので、`../` も symlink 経由の脱出も塞げる。
    if not path.startswith(root + os.sep):
        deny(
            f"@@FILE:@@ に指定できるのは基準ディレクトリ（{root}）内のファイルだけ: "
            f"{rel}（{where}）"
        )
    if not os.path.isfile(path):
        deny(
            f"@@FILE:@@ のファイルが見つからない: {rel}（{where}）。"
            f"基準ディレクトリ {root} からの相対パスで指定する。"
            "例 @@FILE:docs/pr-body.md@@"
        )
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        deny(f"@@FILE:@@ のファイルが読めない: {rel}（{where}）: {e}")
    except UnicodeDecodeError as e:
        deny(f"@@FILE:@@ のファイルが UTF-8 として読めない: {rel}（{where}）: {e}")


def sentinel_path(val):
    """val がセンチネルそのものなら相対パスを返す。違えば None。

    fullmatch なので、文中に埋め込まれた @@FILE:...@@ は展開しない
    （前後の空白だけは SENTINEL 側の \\s* が吸収する）。
    """
    if not isinstance(val, str):
        return None
    m = SENTINEL.fullmatch(val)
    return m.group(1).strip() if m else None


def describe(injected):
    head = " / ".join(f"{w} {rel}（{n:,}字）" for w, rel, n in injected[:MAX_LISTED])
    rest = len(injected) - MAX_LISTED
    if rest > 0:
        head += f" 他 {rest} 件"
    return head


def main():
    try:
        # Windows の既定ロケール（cp932）で stdin を読むと、@@FILE: の
        # 日本語ファイル名が化けて「ファイルが見つからない」になる。
        # バイト列を明示的に UTF-8 として解釈する。
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        sys.exit(0)  # 入力が読めないときは素通し（フェイルオープン）

    m = TOOL_RE.match(data.get("tool_name") or "")
    spec = FIELDS.get(m.group(1)) if m else None
    if spec is None:
        sys.exit(0)  # GitHub MCP の書き込み系ツール以外は対象外

    ti = data.get("tool_input")
    if not isinstance(ti, dict):
        sys.exit(0)  # 判定不能 → 素通し

    # 基準ディレクトリ＝CLAUDE_PROJECT_DIR（無ければフック入力の cwd、無ければカレント）。
    # Claude Code では起動位置に関わらずリポジトリルートが入るので、
    # 「プロジェクトルートからの相対パス」という説明が実際に真になる。
    # cwd を先に見ると、サブディレクトリで起動しただけで基準がそこへずれる。
    # Cowork には CLAUDE_PROJECT_DIR が無いのでセッションの cwd に落ちる。
    root = os.path.realpath(
        os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd())

    # updatedInput は部分マージではなく tool_input 全体を置き換える（実測）。
    # 必ず元の入力に注入フィールドを重ねた完全な dict を返す。
    new_input = dict(ti)
    injected = []  # [(where, rel, 文字数)]

    if spec[0] == "array":
        _, list_key, item_key = spec
        files = ti.get(list_key)
        if not isinstance(files, list):
            sys.exit(0)  # 判定不能 → 素通し
        new_files = []
        for i, item in enumerate(files):
            if not isinstance(item, dict):
                new_files.append(item)  # 判定不能な要素はそのまま残す
                continue
            rel = sentinel_path(item.get(item_key))
            if rel is not None:
                where = f"{list_key}[{i}].{item_key}"
                content = resolve(rel, root, where)
                item = dict(item)  # path 等の他キーを保つ（in-place にしない）
                item[item_key] = content
                injected.append((where, rel, len(content)))
            new_files.append(item)
        if not injected:
            sys.exit(0)  # センチネルが 1 つも無いなら updatedInput を出さない
        new_input[list_key] = new_files
    else:
        _, field = spec
        rel = sentinel_path(ti.get(field))
        if rel is None:
            sys.exit(0)
        content = resolve(rel, root, field)
        new_input[field] = content
        injected.append((field, rel, len(content)))

    emit({
        "systemMessage": (
            f"github-guard: {m.group(1)} に実体を注入した（{describe(injected)}）。"
            "内容はモデルの転記を経由していない"
        ),
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": new_input,
        },
    })


if __name__ == "__main__":
    main()
