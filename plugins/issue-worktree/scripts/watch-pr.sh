#!/bin/sh
# Poll a pull request's checks and emit each newly completed one, then the merge state.
#
# Written for the Monitor tool: every stdout line becomes a notification, so only
# newly completed checks are printed. Reprinting the finished ones on every poll
# would deliver the same notification over and over.
#
# Usage: sh watch-pr.sh <pr-number> [interval-seconds]

set -u

pr="${1:-}"
interval="${2:-30}"

if [ -z "$pr" ]; then
  echo "usage: watch-pr.sh <pr-number> [interval-seconds]" >&2
  exit 2
fi

seen=""
while true; do
  # A failed call (network blip, rate limit) must not kill the watch: keep the
  # previous snapshot so nothing is re-emitted, and try again next round.
  cur=$(gh pr checks "$pr" --json name,bucket \
          --jq '.[] | select(.bucket != "pending") | "\(.name): \(.bucket)"' 2>/dev/null | sort) || cur="$seen"

  # bucket is pass/fail/pending/skipping/cancel. Every terminal state is emitted,
  # not just the successful ones, so a failing run is never silent.
  # grep . suppresses the blank line printf emits when there is no new check.
  printf '%s\n' "$cur" | grep -vxF "$seen" | grep .

  seen="$cur"

  # all(.[]; cond) — all(cond) would test the array itself, always be true, and
  # break out of the loop before CI has finished.
  if gh pr checks "$pr" --json bucket --jq 'all(.[]; .bucket != "pending")' 2>/dev/null | grep -q true; then
    break
  fi

  sleep "$interval"
done

gh pr view "$pr" --json mergeable,mergeStateStatus \
  --jq '"MERGE STATE: \(.mergeable) / \(.mergeStateStatus)"'
