# Docs Directory

## Scope

- Long-form project documentation lives under `docs/`.
- `docs/rl-papers/` stores RL paper read reports, follow-up reading, and implementation takeaways for the Mahjong AI roadmap.
- `docs/rl-papers/roadmap-and-development-plan.md` is the durable study path and development plan tying the reports to repo work.

## Update Rules

- When adding a new research note, create a dedicated Markdown file instead of appending unrelated notes into an existing report.
- Keep the original paper or project website near the top of each note.
- Keep implementation notes grounded in this repo's architecture: Go simulator in `core/` and `rlenv/`, Python training stack in `ai/`.
- When documenting Python commands for the `ai/` package, use uv commands such as `uv sync --project ai --extra dev` and `uv run --project ai ...`; avoid non-uv package or environment commands.
