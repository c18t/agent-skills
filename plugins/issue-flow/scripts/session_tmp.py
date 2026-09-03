#!/usr/bin/env python3
"""Create and print this Codex thread's temporary directory."""
import argparse
import os
from pathlib import Path
import re
import tempfile


SAFE_ID = re.compile(r"[A-Za-z0-9._-]+")


def runtime_id(environ=None):
    """Prefer a thread ID, then a session ID; reject unsafe path components."""
    environ = os.environ if environ is None else environ
    for name in ("CODEX_THREAD_ID", "CODEX_SESSION_ID"):
        value = environ.get(name, "")
        if value and SAFE_ID.fullmatch(value) and value not in (".", ".."):
            return value
    return None


def session_tmp(root: Path, environ=None) -> Path:
    base = root.resolve() / ".codex" / "tmp"
    base.mkdir(parents=True, exist_ok=True)
    identifier = runtime_id(environ)
    if identifier:
        target = base / identifier
        target.mkdir(exist_ok=True)
        return target
    return Path(tempfile.mkdtemp(prefix="session-", dir=base))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    print(session_tmp(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
