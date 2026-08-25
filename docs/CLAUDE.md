# Docs Directory

## Scope

- Long-form **reference** documentation lives under `docs/` — what the system is and what the
  literature says. Records of **how the work happened** (plans, specs, runbooks, experiment
  logs) live in `/worklog/` instead; see `worklog/CLAUDE.md`.
- `docs/rules/` is the canonical Fenghua rules reference.
- `docs/refactoring-notes.md` records where shared/de-duplicated logic now lives.
- `docs/rl-papers/` stores RL paper read reports, follow-up reading, and implementation takeaways for the Mahjong AI roadmap.
- `docs/rl-papers/roadmap-and-development-plan.md` is the durable study path and development plan tying the reports to repo work.
- `docs/rl-papers/rl-research-directions-2026-07.md` is a literature sweep on alternatives to pure self-play.
- `docs/rl-papers/implementation-takeaways.md` records repo-specific RL design defaults, with Mortal-style operation-level Q/value learning as the primary path and Suphx-style oracle/global-reward ideas as later auxiliaries.

**Boundary:** `docs/rl-papers/` holds knowledge about the field (papers, study path,
derived defaults). Our own experiment records — the Chongci progress notebook, risk-target
design note, and lap status files — moved to `worklog/rl-experiment/` on 2026-08-21.

## Update Rules

- When adding a new research note, create a dedicated Markdown file instead of appending unrelated notes into an existing report.
- Keep the original paper or project website near the top of each note.
- Keep implementation notes grounded in this repo's architecture: Go simulator in `internal/engine/` and `internal/rl/`, Python training stack in `ai/`.
- When documenting Python commands for the `ai/` package, use uv commands such as `uv sync --project ai --extra dev` and `uv run --project ai ...`; avoid non-uv package or environment commands.
- When a Chongci checkpoint is promoted or rejected, update both `ai/checkpoints/best-checkpoints.json` and the progress note in `worklog/rl-experiment/` with the run directory, seed windows, MLflow run ids, and promotion/rejection rationale.
- For paired-trace notes, distinguish strict first-divergence counterfactuals from later aligned disagreements. Later disagreements can support risk calibration and data mining, but they are not promotion-gate proof by themselves.
