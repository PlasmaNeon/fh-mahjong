# ai/src/fh_mahjong_ai/scripts/

> Entry points for the package's `fh-mj-*` console scripts.

Each module here backs one console script declared in `ai/pyproject.toml`'s
`[project.scripts]`. Four are **not** registered and must be run as modules:
`evaluate_guarded`, `evaluate_tail_constrained`, `extract_near_state_discards`, and
`build_counterfactual_risk_data`.

- **[`ai/CLAUDE.md`](../../../CLAUDE.md)** — the full command list, grouped by task
  (generate / train / evaluate / serve / diagnose), plus the `uv run --project ai` invocation rule.
- **[`ai/MODULES.md`](../../../MODULES.md)** — per-script reference: flags, when to reach for
  each one, and what its output means.

Adding a script means adding it to `[project.scripts]` **and** giving it an entry in
`MODULES.md` and a row in `CLAUDE.md`'s command tables — otherwise it is invisible to
anyone reading the docs.
