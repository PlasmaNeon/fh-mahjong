import os

import numpy as np
import pytest
import torch

from conftest import SMALL_MODEL
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.search_diagnostic import (PRIMARY, RULES, DiagnosticConfig, Forward, clustered_mean_ci,
                                             rule_choice, run_diagnostic, summarize)

requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library")


def test_rule_keeps_greedy_unless_the_paired_gain_clears_the_margin():
    scores = np.array([[0.0, 0.0, 0.0, 0.0], [0.1, 0.1, 0.1, 0.1], [0.5, -0.5, 0.5, -0.5]])
    assert rule_choice(scores, 0.0) == 1          # best mean, constant gain
    assert rule_choice(scores, 2.0) == 1          # zero-variance gain clears any margin
    noisy = np.array([[0.0, 0.0, 0.0, 0.0], [0.4, -0.3, 0.2, -0.2]])
    assert rule_choice(noisy, 0.0) == 1 and rule_choice(noisy, 1.0) == 0
    assert rule_choice(np.array([[0.2, 0.2], [0.1, 0.1]]), 0.0) == 0


def test_clustered_ci_and_summary_count_deltas_and_overrides():
    mean, half = clustered_mean_ci(np.array([1.0, 1.0, -1.0, -1.0]), np.array([0, 0, 1, 1]), critical=2.0)
    assert mean == 0.0 and half > 0
    rec = {"game_seed": 1, "truth": [0.0, 1.0, -1.0], "ess": 10.0,
           "scores": {f"{s}/{h}": [[0.0] * 4, [1.0] * 4, [-1.0] * 4] for s in ("uniform", "belief")
                      for h in ("next", "hand")}}
    keep = {"game_seed": 2, "truth": [0.3, 0.9, 0.0], "ess": 10.0,
            "scores": {f"{s}/{h}": [[1.0] * 4, [0.0] * 4, [0.0] * 4] for s in ("uniform", "belief")
                       for h in ("next", "hand")}}
    out = summarize([rec, keep])
    primary = out["rules"]["belief/next/z1"]
    assert primary["override_rate"] == 0.5 and abs(primary["mean_delta"] - 0.5) < 1e-12
    assert out["rules"]["uniform/hand/z0"]["hindsight_best_rate"] == 0.5
    assert out["primary"] == "belief/next/z1" and len(out["rules"]) == len(RULES) == 12
    assert PRIMARY == ("belief", "next", 1.0)


@requires_go_lib
def test_diagnostic_runs_end_to_end_on_two_states():
    from fh_mahjong_ai.bridge import CtypesGoBridge
    torch.manual_seed(0)
    model = PolicyValueNet(EnvConfig(), ModelConfig(**SMALL_MODEL, event_window=8, privileged_critic=True,
                                                    aux_heads=True)).eval()
    config = EnvConfig(bridge_kind="go", bridge_library_path=os.environ["FH_MAHJONG_BRIDGE_LIB"],
                       learning_seats=(0, 1, 2, 3), auto_play_heuristics=False, match_mode="chongci",
                       chongci_max_hands=2, max_steps_per_episode=4000, event_history_window=8)
    cfg = DiagnosticConfig(worlds=4, pool_worlds=8, contested_min=0.0, keep_every=1)
    records = []
    with CtypesGoBridge(config) as bridge:
        run_diagnostic(bridge, Forward(model, "cpu"), cfg, states=2, seed_base=910000, sink=records.append)
    assert len(records) == 2
    for record in records:
        m = len(record["candidates"])
        assert 2 <= m <= 3 and len(record["truth"]) == m
        for key, matrix in record["scores"].items():
            assert np.asarray(matrix).shape == (m, 4), key
        assert record["ess"] is not None and 1.0 <= record["ess"] <= 8.0
    summary = summarize(records)
    for name, rule in summary["rules"].items():
        if rule["override_rate"] == 0.0:
            assert rule["mean_delta"] == 0.0, name


class _FakeMeta:
    def __init__(self, slot, seat=0, rewards=(0.0, 0.0, 0.0, 0.0), terminated=False, truncated=False,
                 has_observation=True, error="", round_outcome=None):
        self.slot, self.seat, self.terminated, self.truncated = slot, seat, terminated, truncated
        self.step_rewards = np.asarray(rewards, dtype=np.float32)
        self.has_observation, self.error, self.round_outcome = has_observation, error, round_outcome


class _FakeResult:
    def __init__(self, metas):
        self.slots = metas
        self.row_of_slot = {m.slot: i for i, m in enumerate(metas)}
        n = len(metas)
        self.planes = np.zeros((n, 51, 42, 1), dtype=np.float32)
        self.scalars = np.zeros((n, 58), dtype=np.float32)
        self.action_masks = np.ones((n, 204), dtype=np.int8)
        self.event_grid = self.event_counts = None


class _FakePool:
    def __init__(self, script):
        self.script = list(script)

    def step(self, commands):
        return self.script.pop(0)


class _FakeForward:
    def rows(self, planes, scalars, masks, grid, counts):
        return np.zeros(len(planes), dtype=np.int64), np.full(len(planes), 2.0)


def test_play_out_raises_on_a_clone_error():
    pool = _FakePool([_FakeResult([_FakeMeta(0, error="boom")])])
    with pytest.raises(RuntimeError, match="boom"):
        from fh_mahjong_ai.search_diagnostic import play_out
        play_out(pool, _FakeForward(), [5], 0, "hand", 0.99)


def test_play_out_horizons_at_a_hand_boundary():
    from fh_mahjong_ai.search_diagnostic import play_out
    # The hand ends on the first step (score +1 for root seat 0) and the row is the root's next decision.
    boundary = lambda: _FakeResult([_FakeMeta(0, seat=0, rewards=(1.0, 0, 0, 0), round_outcome={"x": 1})])  # noqa: E731
    assert play_out(_FakePool([boundary()]), _FakeForward(), [5], 0, "hand", 0.99)[0] == 1.0
    assert abs(play_out(_FakePool([boundary()]), _FakeForward(), [5], 0, "next", 0.99)[0] - (1.0 + 0.99 * 2.0)) < 1e-12


@requires_go_lib
def test_cli_writes_records_and_summary(tmp_path, monkeypatch):
    import json
    import fh_mahjong_ai.scripts.search_diagnostic as cli
    from fh_mahjong_ai.storage import model_config_metadata, save_checkpoint
    config = ModelConfig(**SMALL_MODEL, event_window=8, privileged_critic=True, aux_heads=True)
    path = tmp_path / "m.pt"
    save_checkpoint(path, PolicyValueNet(EnvConfig(), config), metadata={"model_config": model_config_metadata(config)})
    monkeypatch.setattr("sys.argv", ["fh-mj-search-diagnostic", "--checkpoint", str(path),
                                     "--bridge-lib", os.environ["FH_MAHJONG_BRIDGE_LIB"], "--out", str(tmp_path / "out"),
                                     "--states", "1", "--worlds", "4", "--pool-worlds", "8",
                                     "--contested-min", "0", "--keep-every", "1", "--device", "cpu",
                                     "--chongci-max-hands", "2"])
    cli.main()
    records = (tmp_path / "out" / "records.jsonl").read_text().splitlines()
    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    assert len(records) == 1 and summary["states"] == 1 and summary["primary"] == "belief/next/z1"
