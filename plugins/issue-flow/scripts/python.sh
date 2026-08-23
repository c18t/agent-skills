#!/bin/sh
# python3 / python / py -3 のうち最初に見つかったもので引数を実行する。
# どれも無ければ 2 で失敗する（暗黙のフォールバックはしない）。
for p in python3 python py; do
  if command -v "$p" >/dev/null 2>&1; then
    [ "$p" = py ] && exec "$p" -3 "$@"
    exec "$p" "$@"
  fi
done
echo 'python not found (tried: python3, python, py)' >&2
exit 2
