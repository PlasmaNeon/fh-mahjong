# ai/tests/

> The pytest suite for `fh_mahjong_ai`. Run `uv run --project ai pytest ai/tests`; CI does not run
> it.

- **conftest.py** — shared fixtures: `SMALL_MODEL`, `small_model_config`, `make_observation`,
  `save_checkpoint`.
- **_ppo_update_reference.py** — the previous `ppo_update`, kept verbatim as the oracle for
  `test_ppo_update_equiv.py`.
- Golden digests in `test_b2b_collector_parity.py` and the event-codec vector in
  `test_events.py` (shared with Go) pin exact bytes: when they fail, fix the code, never the
  constants.

Per-test descriptions are in [`../MODULES.md`](../MODULES.md#tests).
