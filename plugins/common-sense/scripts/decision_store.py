#!/usr/bin/env python3
"""Resolve and initialize a repository-local private ADR store."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys


class StoreError(RuntimeError):
    """A safe, actionable failure while resolving the decision store."""


@dataclass(frozen=True)
class Store:
    public_root: Path
    repository: str
    owner: str
    clone_root: Path

    @property
    def decisions(self) -> Path:
        return self.clone_root / "docs" / "decisions"

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repository}-decisions"


def run(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args, cwd=cwd, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    if check and proc.returncode:
        detail = proc.stderr.strip() or proc.stdout.strip() or "command failed"
        raise StoreError(f"{' '.join(args)}: {detail}")
    return proc


def github_name(remote: str) -> tuple[str, str]:
    match = re.search(r"github\.com(?::|/)([^/]+)/([^/]+?)(?:\.git)?$", remote.strip())
    if not match:
        raise StoreError("origin is not a GitHub repository; pass --owner explicitly")
    return match.group(1), match.group(2)


def resolve(start: Path, owner: str | None = None) -> Store:
    start = start.resolve()
    common = Path(run(
        "git", "-C", str(start), "rev-parse", "--path-format=absolute",
        "--git-common-dir").stdout.strip()).resolve()
    if common.name != ".git":
        raise StoreError(f"unsupported git common directory: {common}")
    public_root = common.parent
    remote_proc = run(
        "git", "-C", str(start), "remote", "get-url", "origin", check=False)
    if remote_proc.returncode:
        if not owner:
            raise StoreError("origin is missing; pass --owner explicitly")
        repository = public_root.name
    else:
        remote_owner, repository = github_name(remote_proc.stdout)
        owner = owner or remote_owner
    assert owner is not None
    clone_root = public_root / ".claude" / "decisions" / f"{repository}-decisions"
    return Store(public_root, repository, owner, clone_root)


def require_ignored(store: Store) -> None:
    proc = run(
        "git", "-C", str(store.public_root), "check-ignore", "-q", "--no-index",
        str(store.clone_root), check=False)
    if proc.returncode != 0:
        raise StoreError(
            "private store is not ignored; add `.claude/decisions/` to the "
            "public repository's .gitignore and commit that change before setup")


def require_clone(store: Store) -> None:
    if not store.clone_root.is_dir():
        raise StoreError(
            f"private decision store is not cloned: {store.clone_root}; run setup first")
    proc = run(
        "git", "-C", str(store.clone_root), "rev-parse", "--show-toplevel",
        check=False)
    if proc.returncode or Path(proc.stdout.strip()).resolve() != store.clone_root.resolve():
        raise StoreError(f"decision store is not an independent git repository: {store.clone_root}")
    try:
        store.decisions.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StoreError(f"decision store is not writable: {store.clone_root}: {exc}") from exc


def remote_visibility(store: Store) -> str | None:
    proc = run(
        "gh", "repo", "view", store.slug, "--json", "visibility", "--jq",
        ".visibility", check=False)
    if proc.returncode:
        return None
    return proc.stdout.strip().upper()


def setup(store: Store, approve_create: bool) -> None:
    require_ignored(store)
    if store.clone_root.exists():
        require_clone(store)
        return
    visibility = remote_visibility(store)
    if visibility is None:
        if not approve_create:
            raise StoreError(
                f"{store.slug} does not exist or is inaccessible; creating it is an "
                "external change. Ask the user for approval, then rerun with "
                "--approve-create")
        run("gh", "repo", "create", store.slug, "--private")
        visibility = remote_visibility(store)
    if visibility != "PRIVATE":
        raise StoreError(
            f"refusing to use {store.slug}: expected PRIVATE visibility, got "
            f"{visibility or 'unknown'}")
    store.clone_root.parent.mkdir(parents=True, exist_ok=True)
    run("gh", "repo", "clone", store.slug, str(store.clone_root))
    require_clone(store)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("command", choices=("path", "check", "setup"))
    result.add_argument("--repository", default=".")
    result.add_argument("--owner")
    result.add_argument("--approve-create", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        store = resolve(Path(args.repository), args.owner)
        if args.command == "setup":
            setup(store, args.approve_create)
        else:
            require_clone(store)
        print(store.decisions)
        return 0
    except (OSError, StoreError) as exc:
        print(f"decision-store: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
