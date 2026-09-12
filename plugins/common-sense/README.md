# common-sense

A plugin for the judgment processes that form shared context between AI and its users. Its name comes from Perl's
[`common::sense`](https://metacpan.org/pod/common::sense).

## Skills

### `commit-message`

Reads a diff before writing a commit message and routes information about the change to the right destination.
The commit retains why the change is needed now and why this approach was chosen, without repeating the diff or
turning the message into a work report.

A repository can define its own routing table in `AGENTS.md`; otherwise, the skill uses its default.

### `decision-record`

Records a decision as an ADR when one option was chosen from multiple alternatives. It uses a MADR v4-based template
to preserve the rejected options, the reason for the choice, and the `enforced_by` mechanism that upholds it.

Unlike `commit-message`, which explains the current change, this skill covers decisions that remain relevant beyond
that change.
