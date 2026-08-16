# ai/src/fh_mahjong_ai/

> The Python RL package. Documentation for this tree lives two levels up.

- **[`ai/CLAUDE.md`](../../CLAUDE.md)** — commands (all 43 `fh-mj-*` CLIs), architecture, and the cross-cutting gotchas. Read this first.
- **[`ai/MODULES.md`](../../MODULES.md)** — per-module reference for every file in this directory and `scripts/`.

## Where to write changes

| You changed | Update |
|---|---|
| A module's behavior, API, or invariants | its entry in `ai/MODULES.md` |
| A CLI, a command's flags, or a project-wide invariant | `ai/CLAUDE.md` |

There is deliberately no per-file detail here — keeping it in one place is what stops the
two from drifting. `generated/` holds the protobuf bindings shared with the Go RL bridge
and is not hand-edited.
