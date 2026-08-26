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

Nothing here is required to build, test, or run the project. When a worklog document and
the code disagree, the code wins — these are point-in-time records, not live specifications.

## Layout

| Directory | Contents |
|---|---|
| `specs/` | Approved design documents, one per feature or campaign. Written before implementation. |
| `plans/` | Implementation plans and operational runbooks derived from a spec. |
| `rl-experiment/` | Running experiment notebooks and closed lap records. |

| `rl-experiment/` file | What it is |
|---|---|
| `chongci-rl-experiment-progress.md` | The running RL notebook. Append here. |
| `20260825-chongci-iql-era-experiment-ledger.md` | Archive of the 2026-03..06 offline-IQL ledger. Search before proposing any risk, auxiliary, or counterfactual-supervision scheme. |
| `chongci-risk-target-design.md` | Superseded design note from that era. |
| `placement-reshape-experiment.md` | The one open experiment thread. |
| `data-scale-960-lap-status.md` | Closed lap record. |
| `20260825-mortal-scale-scratch-status.md` | Live status for the mortal-scale scratch experiment (Amendments 1–2 ratified; not launched). |

## Conventions

- **Name new files `yyyymmdd-<topic>.md`** (enforced by the `doc-name-gate` hook). Files
  from before 2026-08-21 use a dashed `YYYY-MM-DD-` prefix and keep their names; both sort
  correctly. The `rl-experiment/` notebooks are exempt — they are long-lived records with
  stable names that other documents and memories cite.
- **Specs before plans.** A plan opens with a `**Spec:**` line pointing at the spec it
  implements; specs and plans are siblings, so `../specs/…` resolves.
- **One file per effort.** Append to the existing notebook rather than starting a parallel
  record.
- **Never renumber a filename.** Source comments cite these paths — for example
  `internal/api/room_decisions.go` cites the paipu-v2 spec — so a rename means updating
  referrers.
- **Historical documents keep their original wording.** Record a reversal in a newer file
  rather than editing an old one to look correct.

## Traps

- **Before merging a branch cut before 2026-08-21, check it for a resurrected
  `docs/superpowers/`.** A rebase relocates nothing — it replays commits that still write
  the old paths. PR #220 recreated the directory this way.
- **Never put progress records under `.claude/`.** It is gitignored, so records there are
  invisible to the repo and absent from a fresh clone.
- `git log --follow` preserves history across the 2026-08-21 move from `docs/superpowers/`.
