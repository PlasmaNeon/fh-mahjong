# Docs Directory

## Scope

- Long-form project documentation lives under `docs/`.
- `docs/rl-papers/` stores RL paper read reports, follow-up reading, and implementation takeaways for the Mahjong AI roadmap.
- `docs/rl-papers/roadmap-and-development-plan.md` is the durable study path and development plan tying the reports to repo work.
- `docs/rl-papers/implementation-takeaways.md` records repo-specific RL design defaults, with Mortal-style operation-level Q/value learning as the primary path and Suphx-style oracle/global-reward ideas as later auxiliaries.
- `docs/rl-papers/chongci-rl-experiment-progress.md` is the running experiment notebook for Chongci reward-learning work. Update it after new remote data-generation, training, evaluation, promotion, or rejection runs.
- `docs/rl-papers/chongci-risk-target-design.md` is the current design note for the next Chongci risk-learning direction: visible history inputs plus action-conditioned critic-side risk.

## Update Rules

- When adding a new research note, create a dedicated Markdown file instead of appending unrelated notes into an existing report.
- Keep the original paper or project website near the top of each note.
- Keep implementation notes grounded in this repo's architecture: Go simulator in `core/` and `rlenv/`, Python training stack in `ai/`.
- When documenting Python commands for the `ai/` package, use uv commands such as `uv sync --project ai --extra dev` and `uv run --project ai ...`; avoid non-uv package or environment commands.
- When a Chongci checkpoint is promoted or rejected, update both `ai/checkpoints/best-checkpoints.json` and the progress note with the run directory, seed windows, MLflow run ids, and promotion/rejection rationale.
