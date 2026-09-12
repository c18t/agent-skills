#!/usr/bin/env python3
"""Poll a pull request's checks and print newly completed checks."""

import json
import subprocess
import sys
import time


def gh_json(*args):
    """Run gh and return decoded JSON, or None for a transient failure."""
    proc = subprocess.run(
        ["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def watch(pr_number, interval=30.0):
    """Emit each terminal check once, then print the final merge state."""
    seen = set()
    while True:
        checks = gh_json("pr", "checks", pr_number, "--json", "name,bucket")
        if checks is not None:
            current = {
                f"{check['name']}: {check['bucket']}"
                for check in checks
                if check.get("bucket") != "pending"
            }
            for line in sorted(current - seen):
                print(line, flush=True)
            seen = current
            if all(check.get("bucket") != "pending" for check in checks):
                break
        time.sleep(interval)

    state = gh_json(
        "pr", "view", pr_number, "--json", "mergeable,mergeStateStatus")
    if state is None:
        return 1
    print(
        f"MERGE STATE: {state.get('mergeable')} / "
        f"{state.get('mergeStateStatus')}",
        flush=True,
    )
    return 0


def main(argv):
    if len(argv) not in (2, 3):
        print("usage: watch_pr.py <pr-number> [interval-seconds]", file=sys.stderr)
        return 2
    try:
        interval = float(argv[2]) if len(argv) == 3 else 30.0
        if interval < 0:
            raise ValueError
    except ValueError:
        print("interval-seconds must be a non-negative number", file=sys.stderr)
        return 2
    return watch(argv[1], interval)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
