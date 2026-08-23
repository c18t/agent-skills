#!/usr/bin/env python3
"""marketplace.json / plugin.json の `claude plugin validate` が拾わない壊れ方を検査する。

Claude Desktop は名前が規約外（128 文字以内、英数字と . _ -、先頭は英数字）の
プラグイン entry を**エラーにせず落とす**ので、手元でもここで止める。
あわせて名前の重複、source パスの実在、entry と plugin.json の整合を見る。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NAME_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,127}$")

errors = []


def check_name(label, name):
    if not isinstance(name, str) or not NAME_RE.match(name):
        errors.append(
            f"{label}: 名前 {name!r} が規約外"
            "（128 文字以内、英数字と . _ -、先頭は英数字）。"
            "Claude Desktop はこの entry をエラーにせず落とす")


def main():
    marketplace_path = os.path.join(ROOT, ".claude-plugin", "marketplace.json")
    with open(marketplace_path, encoding="utf-8") as f:
        marketplace = json.load(f)

    check_name("marketplace", marketplace.get("name"))

    seen = set()
    for entry in marketplace.get("plugins", []):
        name = entry.get("name")
        label = f"plugins[{name!r}]"
        check_name(label, name)
        if name in seen:
            errors.append(f"{label}: 名前が重複している")
        seen.add(name)

        source = entry.get("source")
        if not isinstance(source, str):
            errors.append(f"{label}: source が文字列でない: {source!r}")
            continue
        plugin_dir = os.path.normpath(os.path.join(ROOT, source))
        plugin_json_path = os.path.join(plugin_dir, ".claude-plugin", "plugin.json")
        if not os.path.isdir(plugin_dir):
            errors.append(f"{label}: source のディレクトリが無い: {source}")
            continue
        if not os.path.isfile(plugin_json_path):
            errors.append(f"{label}: {source}/.claude-plugin/plugin.json が無い")
            continue
        with open(plugin_json_path, encoding="utf-8") as f:
            plugin = json.load(f)
        if plugin.get("name") != name:
            errors.append(
                f"{label}: plugin.json の name {plugin.get('name')!r} が entry と一致しない")
        if "version" in entry and entry["version"] != plugin.get("version"):
            errors.append(
                f"{label}: entry の version {entry['version']!r} と "
                f"plugin.json の version {plugin.get('version')!r} が一致しない")

    if errors:
        for e in errors:
            print(f"NG: {e}")
        sys.exit(1)
    print(f"OK: {len(seen)} plugin entries checked")


if __name__ == "__main__":
    main()
