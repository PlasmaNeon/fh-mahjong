# docs/

> Reference documentation: how the system, the rules, and the AI work.

## Files

| File | Content |
|---|---|
| `architecture.md` | System map, engine, rules plugin, server, bots and serving, frontend, deployment |
| `ai-player.md` | The RL agent: observation, action catalog, model, training recipe, decision rule, serving, current champions |
| `ai-evaluation.md` | Metrics, gate tools, statistics, lap registration, spent seed windows, training-box operation |
| `ai-findings.md` | Champion lineage, every lever tried and its result, rules learned, measured policy behavior |
| `replay-review.md` | Replay viewer and AI review: pipeline, definitions, configuration |
| `rules/official-rules.md` | Raw Fenghua rules source (canonical human-readable reference) |
| `rules/rules.md` | Synthesized rules and their Go implementation |
| `rl-papers/` | Paper read reports, surveyed directions, and the RL study roadmap |

## Update rules

- State the current answer. Replace wrong text; do not narrate what changed — that belongs in
  the commit message.
- Reference docs here keep stable undated names; other docs link to them.
- Keep design and findings in sync with the code: a promotion or rejection updates
  `ai/checkpoints/best-checkpoints.json`, the current-state table in `ai-player.md`, and the
  relevant table in `ai-findings.md`. A new evaluation window goes into `ai-evaluation.md`.
- Process records (plans, runbooks, lap logs) live in the local, gitignored `worklog/`; distill
  durable conclusions into these docs.
- A new paper report gets its own file under `rl-papers/` with the source link near the top.
- Document Python commands with uv: `uv sync --project ai --extra dev`,
  `uv run --project ai ...`.
