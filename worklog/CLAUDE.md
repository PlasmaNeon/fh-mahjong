# worklog/

> How the work happened — implementation plans, design specs, runbooks, and experiment logs.

## Scope

`worklog/` is the record of process. `docs/` is the record of product.

| Ask | Look in |
|---|---|
| How does the Fenghua ruleset work? | `docs/rules/` |
| Where does shared tile logic live? | `docs/refactoring-notes.md` |
| What does the RL literature say? | `docs/rl-papers/` |
| Why was this built this way, and in what order? | `worklog/specs/`, `worklog/plans/` |
| What happened in experiment N? | `worklog/rl-experiment/` |

Nothing here is required to build, test, or run the project. These files are the
design and execution history — read them to understand *why* a change was made, not
*how the system behaves today*. When a worklog document and the code disagree, the
code wins; the worklog is a point-in-time record, not a live specification.

## Layout

| Directory | Contents |
|---|---|
| `specs/` | Approved design documents, one per feature or campaign. Written before implementation, named `YYYY-MM-DD-<topic>-design.md`. |
| `plans/` | Implementation plans and operational runbooks derived from a spec, named `YYYY-MM-DD-<topic>.md` / `-runbook.md`. |
| `rl-experiment/` | Running experiment notebooks and lap status for the RL campaigns. |

Every file is dated in its filename, so the directory listing reads chronologically.

## Conventions

- **Specs before plans.** A plan opens with a `**Spec:**` line pointing at the spec it
  implements; specs and plans are siblings, so relative links (`../specs/…`) resolve.
- **One file per effort.** Append to the existing experiment notebook rather than
  creating a parallel record — `rl-experiment/chongci-rl-experiment-progress.md` is the
  running log for Chongci work.
- **Dated filenames, never renumbered.** Other documents and source comments cite these
  paths (for example `internal/api/room_decisions.go` cites the paipu-v2 spec), so
  renaming a file means updating its referrers.
- Historical documents keep their original wording even when superseded. Record the
  reversal in a newer file instead of editing the old one to look correct.

## History

Moved here from `docs/superpowers/` on 2026-08-21. The old name described the tooling
that produced the files rather than their contents, which made the directory
unguessable; `docs/` was also mixing reference material with process records. The RL
experiment logs (`chongci-rl-experiment-progress.md`, `chongci-risk-target-design.md`,
`data-scale-960-lap-status.md`) came from `docs/rl-papers/` and `docs/superpowers/status/`
in the same move. `git log --follow` preserves history across the move.

`rl-experiment/placement-reshape-experiment.md` came from `.claude/docs/`, an earlier
convention for progress records. That directory is gitignored, so records kept there were
invisible to the repo and absent from a fresh clone — this directory replaces it. Do not
put progress records under `.claude/` again.
