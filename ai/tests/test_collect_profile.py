"""Tests for fh-mj-collect-profile (data-scale-960 Amendment 4): the
measurement-only memory profile of the unchanged collection + update path.

The load-bearing property is that instrumentation is measurement-ONLY: with
probes installed the collected batch and the PPO update must be
byte-identical to the uninstrumented path (the amendment's parity anchor for
the later copy-elimination change)."""
import copy
import json
import subprocess
import sys

import numpy as np
import torch

from fh_mahjong_ai import memprobe
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig, RolloutBatch, compute_gae, ppo_update
from fh_mahjong_ai.scripts import collect_bench, collect_profile
from fh_mahjong_ai.storage import save_checkpoint

_SMALL = dict(channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
              trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16)


def _champion(tmp_path):
    env39 = EnvConfig(bridge_kind="mock")
    model = PolicyValueNet(env39, ModelConfig(**_SMALL))
    path = tmp_path / "champion.pt"
    save_checkpoint(path, model)
    return path


def _profile_kwargs(tmp_path, **overrides):
    kwargs = dict(
        champion=_champion(tmp_path),
        model_config=ModelConfig(**_SMALL, event_window=8),
        growth_blocks=0,
        workers=2,
        matches=4,
        base_seed=100,
        match_mode="classic",
        bridge_kind="mock",
        bridge_lib=None,
        device="cpu",
        max_steps_per_episode=16,
        event_window=8,
        dispatch_chunk=3,
        full_cycle=None,
    )
    kwargs.update(overrides)
    return kwargs


def _labels(report):
    return [c["label"] for c in report["checkpoints"]]


def test_profile_reports_chunk_checkpoints_and_field_accounting(tmp_path):
    """A chunked profile must checkpoint every dispatch, chunk, outer concat
    field, the collector return, and field accounting — the exact sequence
    Amendment 4 registers."""
    report = collect_profile.run_profile(**_profile_kwargs(tmp_path))
    labels = _labels(report)
    # 4 matches at chunk cap 3 -> chunks of 3 and 1.
    assert labels.count("chunk_collected") == 2
    assert labels.count("dispatch_return") == 2
    assert labels.count("collector_return") == 1
    assert "concat_field" in labels
    assert labels[0] == "profile_start"
    assert labels[-1] == "profile_end"
    # Chunk metadata records the registered seed-block split.
    chunk_infos = [c for c in report["checkpoints"] if c["label"] == "chunk_collected"]
    assert [c["matches"] for c in chunk_infos] == [3, 1]

    fa = report["field_accounting"]
    for name in collect_bench._ROLLOUT_DIGEST_ARRAY_FIELDS:
        assert name in fa
        assert fa[name] is None or {"shape", "dtype", "nbytes", "ownership"} <= set(fa[name])
    assert fa["total_nbytes"] > 0
    assert fa["planes"]["ownership"] in ("owned", "view")
    assert report["transition_rows"] > 0
    assert report["collect_seconds"] > 0
    assert isinstance(report["digest"], str) and len(report["digest"]) == 64


def test_profile_digest_matches_uninstrumented_bench(tmp_path):
    """Parity anchor: the profile's instrumented collection must produce the
    byte-identical batch the uninstrumented bench produces for the same seeds,
    weights, and chunking — probes never touch data."""
    kwargs = _profile_kwargs(tmp_path)
    profile = collect_profile.run_profile(**kwargs)
    bench = collect_bench.run_bench(
        champion=kwargs["champion"],
        model_config=ModelConfig(**_SMALL, event_window=8),
        growth_blocks=0, workers=[2], matches=4, base_seed=100,
        match_mode="classic", bridge_kind="mock", bridge_lib=None,
        device="cpu", max_steps_per_episode=16, event_window=8,
        dispatch_chunk=3)
    assert profile["digest"] == bench["results"][2]["digest"]


def test_probe_cleared_after_profile(tmp_path):
    collect_profile.run_profile(**_profile_kwargs(tmp_path))
    assert memprobe._probe_fn is None


def test_pool_teardown_before_final_concat(tmp_path):
    """Amendment 5: the worker pool must close after the FINAL dispatch's
    results are received and before remaining assembly — the checkpoint
    stream must show pool_closed_before_concat, then the final
    dispatch_return, then collector_return."""
    report = collect_profile.run_profile(**_profile_kwargs(tmp_path))
    labels = _labels(report)
    assert labels.count("pool_closed_before_concat") == 1
    closed_at = labels.index("pool_closed_before_concat")
    final_dispatch = max(i for i, l in enumerate(labels) if l == "dispatch_return")
    collector_return = labels.index("collector_return")
    assert closed_at < final_dispatch < collector_return
    # The closed-pool checkpoint must observe zero live child processes.
    assert report["checkpoints"][closed_at]["children_count"] == 0


def test_teardown_does_not_perturb_digest_across_runs(tmp_path):
    """Amendment 5: teardown cannot perturb seed coverage or row order — two
    profiles through the same settings must reproduce the digest. (Pool
    auto-restart on a reused collector is exercised by test_collect_bench's
    warmup+steady runs, which now span a teardown between collects.)"""
    kwargs = _profile_kwargs(tmp_path)
    first = collect_profile.run_profile(**kwargs)
    second = collect_profile.run_profile(**kwargs)
    assert first["digest"] == second["digest"]


def test_full_cycle_profile_covers_gae_and_update_checkpoints(tmp_path):
    settings = collect_bench.FullCycleSettings(
        minibatch_size=8, ppo_epochs=1, gamma=0.99, gae_lambda=0.95,
        lr=2e-5, entropy_coef=0.0, device="cpu", update_seed=0)
    report = collect_profile.run_profile(
        **_profile_kwargs(tmp_path, full_cycle=settings))
    labels = _labels(report)
    for label in ("gae_done", "ppo_tensors_ready", "ppo_update_done"):
        assert label in labels, label
    fc = report["full_cycle"]
    assert fc["transition_rows"] == report["transition_rows"]
    assert fc["optimizer_steps"] > 0
    assert np.isfinite(fc["approx_kl"])


def _tiny_update_batch(n=12):
    rng = np.random.default_rng(0)
    return RolloutBatch(
        planes=rng.standard_normal((n, 4, 34)).astype(np.float32),
        scalars=rng.standard_normal((n, 8)).astype(np.float32),
        action_mask=np.ones((n, 61), dtype=np.int8),
        actions=rng.integers(0, 61, n).astype(np.int64),
        old_logprobs=rng.standard_normal(n).astype(np.float32),
        values=rng.standard_normal(n).astype(np.float32),
        rewards=rng.standard_normal(n).astype(np.float32),
        dones=(np.arange(n) % 4 == 3).astype(np.float32),
    )


class _TinyNet(torch.nn.Module):
    """Minimal model exposing the forward signature ppo_update needs."""

    def __init__(self):
        super().__init__()
        self.body = torch.nn.Linear(4 * 34 + 8, 32)
        self.policy = torch.nn.Linear(32, 61)
        self.value = torch.nn.Linear(32, 1)

    def forward(self, planes, scalars, action_mask, events=None, event_lengths=None):
        x = torch.cat([planes.flatten(1), scalars], dim=1)
        h = torch.relu(self.body(x))
        logits = self.policy(h)
        logits = logits.masked_fill(action_mask == 0, torch.finfo(logits.dtype).min)
        return logits, self.value(h).squeeze(-1)


def _run_tiny_update():
    torch.manual_seed(7)
    model = _TinyNet()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    batch = _tiny_update_batch()
    config = PPOConfig(minibatch_size=5, ppo_epochs=2, device="cpu")
    torch.manual_seed(11)
    advantages, returns = compute_gae(batch.rewards, batch.values, batch.dones, 0.99, 0.95)
    metrics = ppo_update(model, optimizer, batch, advantages, returns, config)
    return metrics, {k: v.detach().clone() for k, v in model.state_dict().items()}


def test_ppo_update_bit_identical_with_probe_installed():
    """The probes inside compute_gae/ppo_update must not perturb the update:
    identical seeds and inputs give bit-identical metrics and weights with a
    recording probe installed vs no probe."""
    baseline_metrics, baseline_state = _run_tiny_update()
    recorded = []
    memprobe.set_memory_probe(lambda label, info: recorded.append(label))
    try:
        probed_metrics, probed_state = _run_tiny_update()
    finally:
        memprobe.set_memory_probe(None)
    assert probed_metrics == baseline_metrics
    for key, value in baseline_state.items():
        assert torch.equal(value, probed_state[key]), key
    assert "gae_done" in recorded
    assert "ppo_tensors_ready" in recorded
    assert "ppo_update_done" in recorded


def test_rss_snapshot_shape():
    snap = memprobe.rss_snapshot()
    expected = {"master_rss_bytes", "master_hwm_bytes", "master_pss_bytes",
                "children_rss_bytes", "children_count",
                "cgroup_current_bytes", "cgroup_peak_bytes"}
    assert expected <= set(snap)
    assert isinstance(snap["children_count"], int)


def _run_cli(tmp_path, extra_args):
    champion = _champion(tmp_path)
    args = [
        sys.executable, "-m", "fh_mahjong_ai.scripts.collect_profile",
        "--champion", str(champion),
        "--workers", "2",
        "--matches", "4",
        "--base-seed", "100",
        "--dispatch-chunk", "3",
        "--match-mode", "classic",
        "--bridge-kind", "mock",
        "--device", "cpu",
        "--max-steps-per-episode", "16",
        "--event-window", "8",
        "--model-channels", "16",
        "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "32",
        "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "32",
        "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
    ] + extra_args
    return subprocess.run(args, capture_output=True, text=True)


def test_cli_writes_json_report(tmp_path):
    out = tmp_path / "profile.json"
    result = _run_cli(tmp_path, ["--json", str(out), "--tracemalloc",
                                 "--full-cycle", "--minibatch-size", "8",
                                 "--ppo-epochs", "1", "--ppo-device", "cpu"])
    assert result.returncode == 0, result.stderr
    payload = json.loads(out.read_text())
    assert payload["matches"] == 4
    assert payload["dispatch_chunk"] == 3
    assert payload["transition_rows"] > 0
    assert payload["field_accounting"]["total_nbytes"] > 0
    labels = [c["label"] for c in payload["checkpoints"]]
    assert "collector_return" in labels
    assert "ppo_update_done" in labels
    assert any("tracemalloc_current_bytes" in c for c in payload["checkpoints"])
    assert "digest" in payload


def test_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "fh_mahjong_ai.scripts.collect_profile", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "--matches" in result.stdout
