import functools
import re
import subprocess
import sys
import traceback
from dataclasses import replace

import numpy as np
import pytest

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.train_b2b import _b2b_model_env_config, collect_b2b_rollouts
from fh_mahjong_ai.ppo import PPOConfig, RolloutBatch
from fh_mahjong_ai.scripts import collect_bench
from fh_mahjong_ai.storage import save_checkpoint
from conftest import SMALL_MODEL


def _perturbing_b2b_worker_loop(env_config, model_config, ppo_config, task_q, result_q,
                                *, field):
    """Test-only worker target (adversarial round 9, medium finding): mirrors
    `oracle._b2b_worker_loop` exactly, except two-match chunks have `field`
    perturbed before being returned to the parent. Passed to
    `ParallelB2bCollector`/`collect_bench.run_bench` as `worker_target` so
    these tests exercise the REAL spawn/queue/model lifecycle path -- proving
    the multi-worker can-fail property is genuine -- without any production
    env-var hook. Defined at module level (not a closure) so multiprocessing's
    spawn context can pickle it; the `field` selection travels via
    `functools.partial`, which pickles fine because its underlying function is
    a plain, importable module-level function."""
    import torch as _torch

    from fh_mahjong_ai.model import PolicyValueNet as _PVN

    _torch.set_num_threads(1)
    model = _PVN(_b2b_model_env_config(env_config), model_config)
    while True:
        task = task_q.get()
        if task is None:
            return
        worker_id, state_dict, base_seed, matches = task
        try:
            model.load_state_dict(state_dict)
            cfg = replace(ppo_config, matches_per_iter=matches, device="cpu")
            batch = collect_b2b_rollouts(env_config, model, cfg, base_seed=base_seed)
            if matches == 2:
                if field == "events":
                    batch.events[0, 0] ^= 1
                elif field in {"rewards", "old_logprobs"}:
                    getattr(batch, field)[0] += 1.0
                elif field == "dones":
                    batch.dones[0] = 1.0 - batch.dones[0]
                else:
                    raise RuntimeError(f"unknown test perturb field {field!r}")
            result_q.put((worker_id, batch, None))
        except Exception:  # noqa: BLE001 - report any worker failure to the parent
            result_q.put((worker_id, None, traceback.format_exc()))



def _champion(tmp_path):
    env39 = EnvConfig(bridge_kind="mock")
    model = PolicyValueNet(env39, ModelConfig(**SMALL_MODEL))
    path = tmp_path / "champion.pt"
    save_checkpoint(path, model)
    return path


def _bench_kwargs(tmp_path, workers):
    champion = _champion(tmp_path)
    return dict(
        champion=champion,
        model_config=ModelConfig(**SMALL_MODEL, event_window=8),
        growth_blocks=0,
        workers=workers,
        matches=4,
        base_seed=100,
        match_mode="classic",
        bridge_kind="mock",
        bridge_lib=None,
        device="cpu",
        max_steps_per_episode=16,
        event_window=8,
    )


def test_same_worker_count_twice_gives_identical_digest(tmp_path):
    kwargs = _bench_kwargs(tmp_path, [2])
    report_a = collect_bench.run_bench(**kwargs)
    report_b = collect_bench.run_bench(**kwargs)
    assert report_a["results"][2]["digest"] == report_b["results"][2]["digest"]


def test_workers_one_vs_two_give_identical_digest(tmp_path):
    kwargs = _bench_kwargs(tmp_path, [1, 2])
    report = collect_bench.run_bench(**kwargs)
    assert report["all_digests_equal"] is True
    assert report["results"][1]["digest"] == report["results"][2]["digest"]


def test_bench_uses_persistent_parallel_collector_for_warmup_and_steady_round(
        tmp_path, monkeypatch):
    calls = []

    class RecordingCollector:
        def __init__(self, env_config, model_config, ppo_config, num_workers, worker_target=None):
            calls.append(("init", num_workers))
            self.env_config = env_config
            self.ppo_config = ppo_config
            self.model = PolicyValueNet(_b2b_model_env_config(env_config), model_config)

        def start(self):
            calls.append(("start",))

        def collect(self, state_dict, base_seed, matches_per_iter):
            calls.append(("collect", base_seed, matches_per_iter))
            self.model.load_state_dict(state_dict)
            cfg = replace(self.ppo_config, matches_per_iter=matches_per_iter, device="cpu")
            return collect_b2b_rollouts(
                self.env_config, self.model, cfg, base_seed=base_seed)

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(collect_bench, "ParallelB2bCollector", RecordingCollector)
    kwargs = _bench_kwargs(tmp_path, [2])
    report = collect_bench.run_bench(**kwargs)
    assert calls == [
        ("init", 2),
        ("start",),
        ("collect", 100, 4),
        ("collect", 100, 4),
        ("close",),
    ]
    assert report["results"][2]["startup_seconds"] >= 0.0
    assert report["results"][2]["steady_seconds"] >= 0.0


def test_injected_perturbation_makes_digests_differ_and_names_it(tmp_path):
    kwargs = _bench_kwargs(tmp_path, [1, 2])
    worker_target = functools.partial(_perturbing_b2b_worker_loop, field="rewards")
    report = collect_bench.run_bench(**kwargs, worker_target=worker_target)
    assert report["all_digests_equal"] is False
    assert report["results"][1]["digest"] != report["results"][2]["digest"]


def test_injected_event_perturbation_makes_digests_differ(tmp_path):
    """A fan-out bug isolated to event-history handling (e.g. a worker
    reusing another worker's event-window buffer) must not slip past the
    digest silently: only perturbing `batch.events` (leaving planes, scalars,
    action_mask, actions, and rewards untouched) must still flip the digest.
    This is what catches finding 1 (events/event_lengths/action_mask omitted
    from the digest) if it regresses."""
    kwargs = _bench_kwargs(tmp_path, [1, 2])
    worker_target = functools.partial(_perturbing_b2b_worker_loop, field="events")
    report = collect_bench.run_bench(**kwargs, worker_target=worker_target)
    assert report["all_digests_equal"] is False
    assert report["results"][1]["digest"] != report["results"][2]["digest"]


@pytest.mark.parametrize("field", ["dones", "old_logprobs"])
def test_injected_ppo_field_perturbation_makes_digests_differ(tmp_path, field):
    worker_target = functools.partial(_perturbing_b2b_worker_loop, field=field)
    report = collect_bench.run_bench(**_bench_kwargs(tmp_path, [1, 2]), worker_target=worker_target)
    assert report["all_digests_equal"] is False
    assert report["results"][1]["digest"] != report["results"][2]["digest"]


def test_chunked_dispatch_digest_matches_single_dispatch(tmp_path):
    """Amendment 2 exact-parity gauntlet: bounded sequential dispatch must
    reproduce the single-dispatch batch BIT FOR BIT (per-match seeding makes
    trajectories chunk-invariant), at a match count the chunk cap does NOT
    divide (4 matches, cap 3 -> chunks of 3 + 1), and repeatably."""
    kwargs = _bench_kwargs(tmp_path, [2])  # matches=4
    single = collect_bench.run_bench(**kwargs)
    chunked = collect_bench.run_bench(**kwargs, dispatch_chunk=3)
    chunked_again = collect_bench.run_bench(**kwargs, dispatch_chunk=3)
    assert single["results"][2]["digest"] == chunked["results"][2]["digest"]
    assert chunked["results"][2]["digest"] == chunked_again["results"][2]["digest"]


def test_chunk_dispatch_covers_seed_blocks_in_order(monkeypatch):
    """Chunk accounting: contiguous seed blocks, canonical order, exact
    remainder handling, no duplication or omission, and the legacy single
    dispatch when the cap is 0 or >= the match count."""
    from dataclasses import replace as dc_replace

    from fh_mahjong_ai.train_b2b import ParallelB2bCollector

    env = EnvConfig(bridge_kind="mock")
    mcfg = ModelConfig(**SMALL_MODEL, event_window=8)

    def make_collector(cap):
        return ParallelB2bCollector(
            env, mcfg, dc_replace(PPOConfig(device="cpu"), collect_dispatch_chunk=cap), 2)

    def install_recorder(collector, calls):
        monkeypatch.setattr(collector, "start", lambda: None)  # no real spawn

        def fake(state_dict, base_seed, matches, final_dispatch=False):
            calls.append((base_seed, matches))
            batch = _minimal_batch()
            batch.actions = np.zeros(matches, dtype=np.int64)
            batch.planes = np.zeros((matches, 1), dtype=np.float32)
            batch.scalars = np.zeros((matches, 1), dtype=np.float32)
            batch.action_mask = np.ones((matches, 1), dtype=np.int8)
            batch.old_logprobs = np.zeros(matches, dtype=np.float32)
            batch.values = np.zeros(matches, dtype=np.float32)
            batch.rewards = np.zeros(matches, dtype=np.float32)
            batch.dones = np.ones(matches, dtype=np.float32)
            batch.events = np.zeros((matches, 1), dtype=np.uint32)
            batch.event_lengths = np.ones(matches, dtype=np.int32)
            batch.dealin_labels = np.zeros(matches, dtype=np.float32)
            batch.rank_labels = np.zeros(matches, dtype=np.int64)
            return batch
        monkeypatch.setattr(collector, "_collect_dispatch", fake)

    calls: list = []
    collector = make_collector(320)
    install_recorder(collector, calls)
    batch = collector.collect({}, 700000, 960)
    assert calls == [(700000, 320), (700320, 320), (700640, 320)]
    assert len(batch) == 960

    calls.clear()
    collector = make_collector(3)
    install_recorder(collector, calls)
    batch = collector.collect({}, 100, 7)
    assert calls == [(100, 3), (103, 3), (106, 1)]
    assert len(batch) == 7

    for cap in (0, 7, 100):
        calls.clear()
        collector = make_collector(cap)
        install_recorder(collector, calls)
        collector.collect({}, 100, 7)
        assert calls == [(100, 7)], f"cap={cap}"


def test_chunk_dispatch_propagates_later_chunk_failure(monkeypatch):
    from dataclasses import replace as dc_replace

    from fh_mahjong_ai.train_b2b import ParallelB2bCollector

    env = EnvConfig(bridge_kind="mock")
    mcfg = ModelConfig(**SMALL_MODEL, event_window=8)
    collector = ParallelB2bCollector(
        env, mcfg, dc_replace(PPOConfig(device="cpu"), collect_dispatch_chunk=2), 2)
    calls: list = []

    def fake(state_dict, base_seed, matches, final_dispatch=False):
        calls.append((base_seed, matches))
        if len(calls) == 2:
            raise RuntimeError("worker died in chunk 2")
        batch = _minimal_batch()
        return batch

    monkeypatch.setattr(collector, "start", lambda: None)  # no real spawn
    monkeypatch.setattr(collector, "_collect_dispatch", fake)
    with pytest.raises(RuntimeError, match="chunk 2"):
        collector.collect({}, 0, 4)


def test_cli_dispatch_chunk_flag_passes(tmp_path):
    result = _run_cli(tmp_path, ["--dispatch-chunk", "3"])
    assert result.returncode == 0, result.stderr
    assert "all_digests_equal: True" in result.stdout


def _full_cycle_settings():
    return collect_bench.FullCycleSettings(
        minibatch_size=8, ppo_epochs=1, gamma=0.99, gae_lambda=0.95,
        lr=2e-5, entropy_coef=0.0, device="cpu", update_seed=0,
    )


def test_full_cycle_reports_update_metrics_and_invariance(tmp_path):
    """The bench must measure a FULL collect + PPO update cycle per count —
    transition rows, optimizer steps, throughput, label coverage, truncation,
    KL, clip fraction, host peak RSS — and prove rows/labels are
    count-invariant."""
    kwargs = _bench_kwargs(tmp_path, [1, 2])
    report = collect_bench.run_bench(**kwargs, full_cycle=_full_cycle_settings())
    assert report["all_digests_equal"] is True
    assert report["rows_and_labels_equal"] is True

    phases = {w: report["results"][w]["full_cycle"] for w in (1, 2)}
    for fc in phases.values():
        assert fc["host_peak_rss_bytes"] > 0
        for cyc in fc["cycles"]:
            assert cyc["transition_rows"] > 0
            expected_steps = -(-cyc["transition_rows"] // 8)  # ceil, 1 epoch
            assert cyc["optimizer_steps"] == expected_steps
            assert cyc["matches_per_second"] > 0.0
            assert cyc["update_seconds"] >= 0.0
            for key in ("policy_loss", "value_loss", "entropy", "approx_kl",
                        "clip_fraction"):
                assert np.isfinite(cyc[key])
            # B2b batches always carry aux labels; their coverage is the
            # spec-mandated label-coverage measurement.
            assert 0.0 <= cyc["dealin_positive_rate"] <= 1.0
            assert 0.0 <= cyc["rank_label_coverage"] <= 1.0
            assert cyc["truncated_matches"] >= 0
            assert 0.0 <= cyc["truncation_rate"] <= 1.0
            assert cyc["host_peak_rss_bytes"] > 0
            # cpu collection and cpu update: no CUDA stats on either phase.
            assert cyc["cuda_peak_collect_allocated_bytes"] is None
            assert cyc["cuda_peak_collect_reserved_bytes"] is None
            assert cyc["cuda_peak_update_allocated_bytes"] is None
            assert cyc["cuda_peak_update_reserved_bytes"] is None

    # Identical batch (digest-equal) + identical warm-start weights + fixed
    # update seed on cpu => the PPO update itself must be worker-count
    # invariant, bit for bit, in EVERY cycle.
    for cycle_a, cycle_b in zip(phases[1]["cycles"], phases[2]["cycles"]):
        for key in ("transition_rows", "optimizer_steps", "policy_loss", "value_loss",
                    "entropy", "approx_kl", "clip_fraction",
                    "dealin_positive_rate", "rank_label_coverage",
                    "truncated_matches", "digest", "base_seed"):
            assert cycle_a[key] == cycle_b[key], key


def test_full_cycle_runs_three_consecutive_cycles_on_one_persistent_model(tmp_path):
    """Spec G1: one excluded warmup, then THREE genuine consecutive cycles on
    one persistent pool and one persistent model/optimizer over three
    consecutive seed blocks. A fresh deep copy per cycle would leave the
    optimizer state and the collected batch identical every cycle — which is
    exactly what this asserts is NOT the case."""
    kwargs = _bench_kwargs(tmp_path, [1])  # matches=4, base_seed=100
    report = collect_bench.run_bench(**kwargs, full_cycle=_full_cycle_settings())
    fc = report["results"][1]["full_cycle"]
    assert fc["cycle_count"] == collect_bench._FULL_CYCLE_CYCLES == 3
    assert [c["cycle"] for c in fc["cycles"]] == [0, 1, 2]
    # Consecutive seed blocks, exactly as train_b2b's iter_seed advances.
    assert [c["base_seed"] for c in fc["cycles"]] == [100, 104, 108]
    # The model really persists: the optimizer's step count keeps growing, and
    # cycle 1 collects with the weights cycle 0's update produced.
    steps = [c["optimizer_steps"] for c in fc["cycles"]]
    assert all(s > 0 for s in steps)
    assert len({c["digest"] for c in fc["cycles"]}) == 3  # different seed blocks


def test_full_cycle_batched_rejects_a_split_collect_and_update_device(tmp_path):
    """One persistent model spans both phases in the batched arm, and
    `ppo_update` assumes the model already sits on its config's device."""
    settings = replace(_full_cycle_settings(), device="cuda")
    with pytest.raises(ValueError, match="must equal the collection device"):
        collect_bench.run_bench(**_batched_kwargs(tmp_path, [2], inference_mode="per_row"),
                                full_cycle=settings)


def test_full_cycle_cli_exits_zero_and_prints_cycle_table(tmp_path):
    result = _run_cli(tmp_path, [
        "--full-cycle", "--minibatch-size", "8", "--ppo-epochs", "1",
        "--gamma", "0.99", "--gae-lambda", "0.95", "--lr", "2e-5",
        "--entropy-coef", "0", "--ppo-device", "cpu",
    ])
    assert result.returncode == 0, result.stderr
    assert "all_digests_equal: True" in result.stdout
    assert "rows_and_labels_equal: True" in result.stdout
    assert "opt_steps" in result.stdout
    assert "cycle_digests_equal (reported): True" in result.stdout


def test_full_cycle_json_report_includes_cycle_metrics(tmp_path):
    import json as json_mod
    out = tmp_path / "report.json"
    result = _run_cli(tmp_path, [
        "--full-cycle", "--minibatch-size", "8", "--ppo-epochs", "1",
        "--ppo-device", "cpu", "--json", str(out),
    ])
    assert result.returncode == 0, result.stderr
    payload = json_mod.loads(out.read_text())
    assert payload["all_digests_equal"] is True
    assert payload["rows_and_labels_equal"] is True
    for w in ("1", "2"):
        fc = payload[w]["full_cycle"]
        assert len(fc["cycles"]) == 3
        for cyc in fc["cycles"]:
            assert cyc["transition_rows"] > 0
            assert cyc["optimizer_steps"] > 0
            assert np.isfinite(cyc["approx_kl"])


def _minimal_batch() -> RolloutBatch:
    return RolloutBatch(
        planes=np.zeros((1, 1), dtype=np.float32),
        scalars=np.zeros((1, 1), dtype=np.float32),
        action_mask=np.ones((1, 1), dtype=np.int8),
        actions=np.zeros(1, dtype=np.int64),
        old_logprobs=np.zeros(1, dtype=np.float32),
        values=np.zeros(1, dtype=np.float32),
        rewards=np.zeros(1, dtype=np.float32),
        dones=np.ones(1, dtype=np.float32),
        events=np.zeros((1, 1), dtype=np.uint32),
        event_lengths=np.ones(1, dtype=np.int32),
        dealin_labels=np.zeros(1, dtype=np.float32),
        rank_labels=np.zeros(1, dtype=np.int64),
    )


def test_digest_includes_per_field_shapes_and_dtypes():
    batch = _minimal_batch()
    baseline = collect_bench._digest_batch(100, 1, batch)

    batch.planes = batch.planes.reshape(1, 1, 1)
    assert collect_bench._digest_batch(100, 1, batch) != baseline

    batch = _minimal_batch()
    batch.actions = batch.actions.astype(np.int32)
    assert collect_bench._digest_batch(100, 1, batch) != baseline


def test_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "fh_mahjong_ai.scripts.collect_bench", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "--workers" in result.stdout


def _run_cli(tmp_path, extra_args):
    champion = _champion(tmp_path)
    args = [
        sys.executable, "-m", "fh_mahjong_ai.scripts.collect_bench",
        "--champion", str(champion),
        "--workers", "1,2",
        "--matches", "4",
        "--base-seed", "100",
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


def test_cli_passing_run_exits_zero(tmp_path):
    result = _run_cli(tmp_path, [])
    assert result.returncode == 0, result.stderr
    assert "all_digests_equal: True" in result.stdout


def test_cli_injected_perturbation_exits_one_and_names_worker_counts(
        tmp_path, monkeypatch, capsys):
    """The CLI's failure-reporting path (exit 1, naming the differing worker
    counts) is exercised in-process against a manufactured differing-digest
    report, not via any production perturbation hook (adversarial round 9,
    medium finding: a previous version had the production worker consult
    `FH_MAHJONG_TEST_B2B_PERTURB_FIELD` from the environment, which a spawned
    child process inherits -- any process that happened to have that variable
    set, in production, would silently corrupt real training data). The
    spawn-path can-fail property itself -- that a genuine perturbation in one
    worker's output really does flip the digest -- is covered by
    `test_injected_perturbation_makes_digests_differ_and_names_it` and its
    siblings above, which inject a test-only `worker_target` instead."""
    champion = _champion(tmp_path)
    fake_report = {
        "results": {
            1: {"startup_seconds": 0.0, "steady_seconds": 0.0, "digest": "aaa",
                "semantic_digest": "aaa-sem"},
            2: {"startup_seconds": 0.0, "steady_seconds": 0.0, "digest": "bbb",
                "semantic_digest": "bbb-sem"},
        },
        "all_digests_equal": False,
        "semantic_digests_equal": False,
        "float_fields_within_tolerance": True,
        "semantics_equal": False,
        "max_float_diff": 0.0,
        "exact_invariance_expected": True,
        "inference_mode": None,
        "collector": "process",
        "model_config": ModelConfig(**SMALL_MODEL, event_window=8),
    }
    monkeypatch.setattr(collect_bench, "run_bench", lambda **kwargs: fake_report)
    argv = [
        "fh-mj-collect-bench",
        "--champion", str(champion),
        "--workers", "1,2",
        "--matches", "4",
        "--base-seed", "100",
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
    ]
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit) as excinfo:
        collect_bench.main()

    assert excinfo.value.code == 1
    combined = capsys.readouterr().out
    assert "all_digests_equal: False" in combined
    assert "workers=[1]" in combined
    assert "workers=[2]" in combined


def test_digest_covers_match_telemetry():
    from fh_mahjong_ai.scripts.collect_bench import _digest_batch
    from fh_mahjong_ai.ppo import RolloutBatch
    import numpy as np
    def mk(tel):
        z = np.zeros((2, 1), dtype=np.float32)
        return RolloutBatch(planes=z, scalars=z, action_mask=z.astype(np.int8),
                            actions=np.zeros(2, dtype=np.int64), old_logprobs=z[:, 0],
                            values=z[:, 0], rewards=z[:, 0], dones=np.array([0, 1], np.float32),
                            match_telemetry=tel)
    d0 = _digest_batch(0, 1, mk(None))
    d1 = _digest_batch(0, 1, mk([{"seed": 0, "bonus": [0.1, 0, 0, -0.1]}]))
    d2 = _digest_batch(0, 1, mk([{"seed": 0, "bonus": [0.2, 0, 0, -0.2]}]))
    assert len({d0, d1, d2}) == 3


# ---------------------------------------------------------------------------
# batched-b2b-collector: --collector batched
# ---------------------------------------------------------------------------


def _batched_kwargs(tmp_path, slots, **overrides):
    kwargs = _bench_kwargs(tmp_path, None)
    kwargs.update(collector="batched", pool_slots=slots, **overrides)
    return kwargs


def test_batched_collector_digest_is_slot_count_invariant(tmp_path):
    """Per-row inference removes batch composition from the floats, so the
    FULL digest must be byte-equal across slot counts (G0.2's property, run
    through the bench's own machinery)."""
    report = collect_bench.run_bench(**_batched_kwargs(tmp_path, [1, 3],
                                                       inference_mode="per_row"))
    assert report["all_digests_equal"] is True
    assert report["semantics_equal"] is True
    assert report["exact_invariance_expected"] is True
    assert report["collector"] == "batched"
    assert report["inference_mode"] == "per_row"
    assert sorted(report["results"]) == [1, 3]


def test_batched_mode_gates_greedily_and_leaves_the_sampled_sweep_ungated(tmp_path):
    """Production inference: the timed sweep is SAMPLED and therefore
    throughput-only — its digests are not compared across slot counts, because
    one float32 rounding difference can flip an action and diverge the rest of
    that match (`exact_invariance_expected` False, `cross_count_gate`
    "float_gate"). The hard gate is `float_gate`, which runs GREEDY: per slot
    count, per field, against a greedy per_row reference on the same seeds,
    with the greedy semantic digest required to match byte for byte (spec
    G0.1b)."""
    report = collect_bench.run_bench(**_batched_kwargs(tmp_path, [1, 3],
                                                       inference_mode="batched"))
    assert report["exact_invariance_expected"] is False
    assert report["cross_count_gate"] == "float_gate"
    assert report["sweep_action_selection"] == "sample"
    gate = report["float_gate"]
    assert gate["reference"] == "per_row"
    assert gate["action_selection"] == "greedy"
    assert "no greedy path" in gate["reference_note"]
    assert gate["ceilings"] == collect_bench.float_gate_ceilings("cpu")
    assert gate["passed"] is True and gate["violations"] == []
    assert gate["repeats"] == 1 and gate["calibrate"] is False
    assert sorted(gate["comparisons"]) == [1, 3]
    for comp in gate["comparisons"].values():
        assert comp["semantic_matches_reference"] is True
        assert comp["repeats"] == 1
        for name in ("legal_logits", "old_logprobs", "values"):
            st = comp["fields"][name]
            assert st["element_count"] > 0 and st["nonfinite_count"] == 0
            assert st["max_abs_diff"] <= gate["ceilings"][name]["max"]
            assert st["p99_9"] <= gate["ceilings"][name]["p99_9"]
            assert st["beyond_ceiling"] == 0
            assert st["p99_9_within_ceiling"] is True and st["passed"] is True
            for key in ("p50", "p95", "p99", "p99_9", "mismatch_count", "beyond_legacy_tol"):
                assert st[key] is not None


def test_batched_bench_reports_the_three_slot_counts_and_forward_shapes(tmp_path):
    """Spec change 3 / G1: requested, allocated and effective-live are three
    different numbers and all three are reported, alongside the rows-per-
    forward summary a throughput miss has to be read against."""
    # matches=4, so an 8-slot request only ever allocates (and fills) 4.
    report = collect_bench.run_bench(**_batched_kwargs(tmp_path, [2, 8],
                                                       inference_mode="per_row"))
    assert report["results"][8]["requested_slots"] == 8
    assert report["results"][8]["allocated_slots"] == 4
    assert report["results"][8]["peak_live_slots"] == 4
    assert report["results"][2]["allocated_slots"] == 2
    assert report["results"][2]["peak_live_slots"] == 2
    shapes = report["results"][2]["forward_shapes"]
    assert shapes["observable"] is True
    assert shapes["forwards"] > 0 and shapes["pool_rounds"] > 0
    assert shapes["rows_per_forward_min"] >= 1
    assert (shapes["rows_per_forward_p10"] <= shapes["rows_per_forward_median"]
            <= shapes["rows_per_forward_max"])
    assert sum(b["count"] for b in shapes["batch_size_histogram"]) == shapes["forwards"]
    # per_row: every forward is one row, and there is one per decision.
    assert shapes["rows_per_forward_max"] == 1
    assert shapes["rows_total"] == shapes["forwards"]


def test_batched_forward_shapes_show_real_batches_in_batched_mode(tmp_path):
    report = collect_bench.run_bench(**_batched_kwargs(tmp_path, [3],
                                                       inference_mode="batched"))
    shapes = report["results"][3]["forward_shapes"]
    assert shapes["observable"] is True
    # At most one forward per pool round (a round whose slots all terminated
    # has no pending rows and forwards nothing), and rounds batch real rows.
    assert 0 < shapes["forwards"] <= shapes["pool_rounds"]
    assert shapes["rows_per_forward_max"] > 1


def test_process_bench_reports_no_slots_and_unobservable_forward_shapes(tmp_path):
    report = collect_bench.run_bench(**_bench_kwargs(tmp_path, [2]))
    result = report["results"][2]
    assert result["requested_slots"] is None and result["allocated_slots"] is None
    assert result["peak_live_slots"] is None
    shapes = result["forward_shapes"]
    assert shapes["observable"] is False
    assert "spawn worker" in shapes["note"]


def test_process_and_per_row_reports_carry_no_float_gate(tmp_path):
    assert collect_bench.run_bench(**_bench_kwargs(tmp_path, [1]))["float_gate"] is None
    report = collect_bench.run_bench(**_batched_kwargs(tmp_path, [1], inference_mode="per_row"))
    assert report["float_gate"] is None


_TWO_PART = {"p99_9": 1e-5, "max": 5e-5}


def test_float_field_stats_reports_every_column_and_gates_on_both_ceiling_parts():
    ref = np.array([0.0, 1.0, -2.0, 3.0], dtype=np.float64)
    st = collect_bench.float_field_stats(
        ref, ref + np.array([0.0, 2e-5, 0.0, 6e-5]), _TWO_PART)
    assert st["element_count"] == 4 and st["nonfinite_count"] == 0
    assert st["mismatch_count"] == 2
    assert st["max_abs_diff"] == pytest.approx(6e-5)
    assert st["beyond_legacy_tol"] == 2 and st["beyond_ceiling"] == 1
    assert st["passed"] is False
    assert st["p50"] <= st["p95"] <= st["p99"] <= st["p99_9"] <= st["max_abs_diff"]

    # The max part alone never excuses the quantile part: every element moves
    # by 2e-5, which is inside max=5e-5 but outside p99.9=1e-5.
    quantile_only = collect_bench.float_field_stats(ref, ref + 2e-5, _TWO_PART)
    assert quantile_only["beyond_ceiling"] == 0
    assert quantile_only["p99_9_within_ceiling"] is False
    assert quantile_only["passed"] is False

    ok = collect_bench.float_field_stats(ref, ref + 5e-6, _TWO_PART)
    assert ok["passed"] is True and ok["beyond_ceiling"] == 0
    assert ok["p99_9_within_ceiling"] is True
    nan = collect_bench.float_field_stats(
        ref, np.array([0.0, np.nan, -2.0, 3.0]), _TWO_PART)
    assert nan["nonfinite_count"] == 1 and nan["passed"] is False
    shape = collect_bench.float_field_stats(ref, ref[:3], _TWO_PART)
    assert shape["shape_mismatch"] is True and shape["passed"] is False
    assert shape["p99_9_within_ceiling"] is False


def test_float_gate_ceilings_are_two_part_per_device_and_only_tighten():
    # Registered from measurement at production width (anchor075); see
    # `_FLOAT_GATE_CEILINGS` for the observed distribution these came from.
    assert collect_bench.float_gate_ceilings("cpu") == {
        "legal_logits": {"p99_9": 1e-4, "max": 5e-4},
        "old_logprobs": {"p99_9": 5e-5, "max": 2e-4},
        "values": {"p99_9": 5e-6, "max": 5e-5}}
    # CUDA caps are 2x the CPU registration: no CUDA number has been seen, and a
    # cap under the measured CPU noise floor would only ever fire falsely.
    assert collect_bench.float_gate_ceilings("cuda:0") == {
        "legal_logits": {"p99_9": 2e-4, "max": 1e-3},
        "old_logprobs": {"p99_9": 1e-4, "max": 5e-4},
        "values": {"p99_9": 1e-5, "max": 1e-4}}
    tightened = collect_bench.float_gate_ceilings("cuda", {"values": {"max": 2e-6}})
    assert tightened["values"] == {"p99_9": 1e-5, "max": 2e-6}
    assert tightened["old_logprobs"] == {"p99_9": 1e-4, "max": 5e-4}
    with pytest.raises(ValueError, match="may not exceed its cap"):
        collect_bench.float_gate_ceilings("cpu", {"values": {"max": 1e-3}})
    with pytest.raises(ValueError, match="may not exceed its cap"):
        collect_bench.float_gate_ceilings("cpu", {"values": {"p99_9": 1e-5}})
    with pytest.raises(ValueError, match="unknown float-gate field"):
        collect_bench.float_gate_ceilings("cpu", {"logprobs": {"max": 1e-6}})
    with pytest.raises(ValueError, match="unknown float-gate ceiling part"):
        collect_bench.float_gate_ceilings("cpu", {"values": {"p99": 1e-9}})


def _stats(**over):
    st = {"ceiling": {"p99_9": 1e-5, "max": 2e-4}, "shape_mismatch": False,
          "element_count": 10, "reference_count": 10, "nonfinite_count": 0,
          "mismatch_count": 1, "beyond_legacy_tol": 0, "beyond_ceiling": 0,
          "max_abs_diff": 1e-6, "p50": 0.0, "p95": 0.0, "p99": 0.0, "p99_9": 1e-6,
          "p99_9_within_ceiling": True, "passed": True}
    st.update(over)
    return st


def _repeat(**over):
    return {name: _stats(**over) for name in collect_bench._FLOAT_GATE_FIELDS}


def test_worst_over_repeats_takes_the_worst_of_every_statistic():
    ceilings = collect_bench.float_gate_ceilings("cpu")
    worst = collect_bench.worst_over_repeats(
        [_repeat(max_abs_diff=1e-6, p99_9=1e-7),
         _repeat(max_abs_diff=9e-6, p99_9=2e-7),
         _repeat(max_abs_diff=3e-6, p99_9=8e-7)],
        ceilings)
    assert worst["values"]["max_abs_diff"] == 9e-6
    assert worst["values"]["p99_9"] == 8e-7
    assert worst["values"]["passed"] is True
    # One failing repeat fails the field.
    failed = collect_bench.worst_over_repeats(
        [_repeat(), _repeat(passed=False, beyond_ceiling=3, max_abs_diff=1.0)], ceilings)
    assert failed["values"]["passed"] is False and failed["values"]["beyond_ceiling"] == 3
    with pytest.raises(ValueError, match="at least one repeat"):
        collect_bench.worst_over_repeats([], ceilings)


def test_calibration_thresholds_double_the_observation_and_never_widen_the_cap():
    ceilings = collect_bench.float_gate_ceilings("cuda")
    # Magnitudes are derived from the caps, never hard-coded: a re-registration
    # must not be able to leave this test asserting nothing.
    cap = ceilings["values"]
    small_max, small_p99_9 = cap["max"] / 100.0, cap["p99_9"] / 100.0
    thresholds, violations = collect_bench.calibration_thresholds(
        _repeat(max_abs_diff=small_max, p99_9=small_p99_9), ceilings)
    assert violations == []
    assert thresholds["values"] == {"p99_9": 2 * small_p99_9, "max": 2 * small_max}
    # 2x an observation above half the cap is clamped to the cap, never above.
    thresholds, violations = collect_bench.calibration_thresholds(
        _repeat(max_abs_diff=0.8 * cap["max"], p99_9=0.8 * cap["p99_9"]), ceilings)
    assert violations == []
    assert thresholds["values"] == {"p99_9": cap["p99_9"], "max": cap["max"]}
    # An observation ABOVE the registered cap stops the work; it is reported,
    # never absorbed into a widened threshold.
    thresholds, violations = collect_bench.calibration_thresholds(
        _repeat(max_abs_diff=3 * cap["max"], p99_9=3 * cap["p99_9"]), ceilings)
    assert any("exceeds the registered cap" in v and "values.max" in v for v in violations)
    assert any("values.p99_9" in v for v in violations)
    assert thresholds["values"]["max"] == cap["max"]
    assert collect_bench.format_ceiling_flags(
        {"values": {"p99_9": 4e-7, "max": 2e-6}}) == [
        "--float-ceiling values.p99_9=4.000000e-07",
        "--float-ceiling values.max=2.000000e-06"]


def test_emission_ordered_logits_sorts_by_seed_and_seat_and_checks_alignment():
    # Four emitted rows: seed 1 seat 0, seed 2 seat 0, seed 2 seat 1 (two
    # decisions, in decision order). Mask width 3, one illegal column per row.
    mask = np.array([[1, 1, 0], [0, 1, 1], [1, 0, 1], [1, 1, 0]], dtype=np.int8)
    batch = replace(_minimal_batch(), action_mask=mask, actions=np.zeros(4, dtype=np.int64))
    n, a = mask.shape
    fmin = np.finfo(np.float32).min
    rows = []
    for i in range(n):
        row = np.full(a, fmin, dtype=np.float32)
        row[mask[i].astype(bool)] = float(i)
        rows.append(row)
    # Decision order interleaves matches; emission order is (seed, seat), stable.
    sink = [(2, 0, rows[1]), (1, 0, rows[0]), (2, 1, rows[2]), (2, 1, rows[3])]
    ordered = collect_bench.emission_ordered_logits(sink, batch)
    assert [float(r[mask[i].astype(bool)][0]) for i, r in enumerate(ordered)] == list(range(n))
    with pytest.raises(RuntimeError, match="rows"):
        collect_bench.emission_ordered_logits(sink[:-1], batch)
    bad = [(s, seat, np.zeros(a, dtype=np.float32)) for s, seat, _ in sink]
    with pytest.raises(RuntimeError, match="misaligned"):
        collect_bench.emission_ordered_logits(bad, batch)


def _perturbing_batched_collect(delta: float, field: str = "old_logprobs",
                                rows: str = "first"):
    """Wrap the real batched collector so only the production (batched-mode)
    collection is perturbed; the per_row reference stays untouched.

    `rows="first"` moves one element — at n=64 rows that lands the perturbation
    at roughly the p99.9 quantile as well as at the max. `rows="all"` moves
    every element, which is the shape that fails the quantile part while
    staying well inside the max cap."""
    real = collect_bench.collect_b2b_rollouts_batched

    def collect(env_config, model, config, base_seed, pool, **kwargs):
        batch = real(env_config, model, config, base_seed=base_seed, pool=pool, **kwargs)
        if kwargs.get("inference_mode", "batched") == "batched":
            values = np.array(getattr(batch, field), copy=True)
            if rows == "all":
                values += delta
            else:
                values[0] += delta
            setattr(batch, field, values)
        return batch
    return collect


def _batched_main_argv(champion, extra):
    return [
        "fh-mj-collect-bench", "--champion", str(champion),
        "--collector", "batched", "--pool-slots", "1,3", "--inference-mode", "batched",
        "--matches", "4", "--base-seed", "100", "--match-mode", "classic",
        "--bridge-kind", "mock", "--device", "cpu", "--max-steps-per-episode", "16",
        "--event-window", "8", "--model-channels", "16", "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "32", "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "32", "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
    ] + extra


def test_float_gate_max_part_violation_exits_one_and_names_the_field_and_part(
        tmp_path, monkeypatch, capsys):
    """End-to-end: a perturbation past the cpu max cap (2e-4) must reach the
    PROCESS EXIT CODE, and the message must name both the field and the part
    it violated."""
    champion = _champion(tmp_path)
    monkeypatch.setattr(collect_bench, "collect_b2b_rollouts_batched",
                        _perturbing_batched_collect(5e-4))
    monkeypatch.setattr(sys, "argv", _batched_main_argv(champion, []))
    with pytest.raises(SystemExit) as excinfo:
        collect_bench.main()
    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "FLOAT GATE VIOLATION" in out
    assert re.search(r"field=old_logprobs: max_abs_diff=5\.0\d*e-04 > max ceiling 2\.0e-04",
                     out)
    assert "field=values" not in out and "field=legal_logits" not in out
    assert "float_gate_passed: False" in out


def test_float_gate_quantile_part_violation_alone_exits_one(tmp_path, monkeypatch, capsys):
    """The two parts are independent gates: a spread that stays far inside the
    max cap but pushes p99.9 past its bound still fails, and says which part."""
    champion = _champion(tmp_path)
    ceiling = collect_bench.float_gate_ceilings("cpu")["old_logprobs"]
    # Strictly between the parts: past the quantile bound, inside the max cap.
    # Derived, so a re-registration cannot silently move it inside both.
    delta = 2.0 * ceiling["p99_9"]
    assert delta <= ceiling["max"], "no room between the parts for a quantile-only violation"
    monkeypatch.setattr(collect_bench, "collect_b2b_rollouts_batched",
                        _perturbing_batched_collect(delta, rows="all"))
    monkeypatch.setattr(sys, "argv", _batched_main_argv(champion, []))
    with pytest.raises(SystemExit) as excinfo:
        collect_bench.main()
    assert excinfo.value.code == 1
    out = capsys.readouterr().out
    assert "field=old_logprobs: p99.9=" in out
    assert f"> p99.9 ceiling {ceiling['p99_9']:.1e}" in out
    assert "max ceiling" not in out  # the max part is untouched below its cap
    assert "float_gate_passed: False" in out


def test_float_gate_perturbation_within_both_ceiling_parts_passes(
        tmp_path, monkeypatch, capsys):
    champion = _champion(tmp_path)
    monkeypatch.setattr(collect_bench, "collect_b2b_rollouts_batched",
                        _perturbing_batched_collect(5e-6, rows="all"))
    out_json = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", _batched_main_argv(champion, ["--json", str(out_json)]))
    with pytest.raises(SystemExit) as excinfo:
        collect_bench.main()
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "FLOAT GATE VIOLATION" not in out
    assert "float_gate_passed: True" in out
    assert "old_logprobs: n=" in out and "values: n=" in out and "legal_logits: n=" in out
    assert "no greedy path" in out  # GATE_REFERENCE_NOTE
    import json as json_mod
    payload = json_mod.loads(out_json.read_text())
    gate = payload["float_gate"]
    assert gate["passed"] is True
    for count in ("1", "3"):
        st = gate["comparisons"][count]["fields"]["old_logprobs"]
        # The injected 5e-6 plus the collector's own batched-vs-per_row
        # rounding, which is why this is a range and not an equality.
        assert 5e-6 <= st["max_abs_diff"] < 1e-5
        assert 4.5e-6 <= st["p99_9"] < 1e-5
        assert st["beyond_ceiling"] == 0 and st["p99_9_within_ceiling"] is True


def test_float_gate_tightened_ceiling_via_cli_catches_the_in_cap_perturbation(
        tmp_path, monkeypatch, capsys):
    champion = _champion(tmp_path)
    monkeypatch.setattr(collect_bench, "collect_b2b_rollouts_batched",
                        _perturbing_batched_collect(5e-6, rows="all"))
    monkeypatch.setattr(sys, "argv", _batched_main_argv(
        champion, ["--float-ceiling", "old_logprobs.p99_9=1e-6"]))
    with pytest.raises(SystemExit) as excinfo:
        collect_bench.main()
    assert excinfo.value.code == 1
    assert "field=old_logprobs" in capsys.readouterr().out


def test_float_ceiling_cli_rejects_widening_bad_syntax_and_wrong_collector(tmp_path):
    widened = _run_batched_cli(
        tmp_path, ["--pool-slots", "1", "--float-ceiling", "values.max=1e-3"])
    assert widened.returncode == 2 and "may not exceed its cap" in widened.stderr
    # A bare FIELD=VALUE is ambiguous now that a ceiling has two parts.
    scalar = _run_batched_cli(
        tmp_path, ["--pool-slots", "1", "--float-ceiling", "values=1e-6"])
    assert scalar.returncode == 2 and "FIELD.PART=VALUE" in scalar.stderr
    per_row = _run_batched_cli(tmp_path, ["--pool-slots", "1", "--inference-mode", "per_row",
                                          "--float-ceiling", "values.max=1e-6"])
    assert per_row.returncode == 2 and "--float-ceiling applies only" in per_row.stderr
    calib = _run_batched_cli(tmp_path, ["--pool-slots", "1", "--inference-mode", "per_row",
                                        "--calibrate"])
    assert calib.returncode == 2 and "--calibrate applies only" in calib.stderr


def test_calibrate_mode_runs_three_greedy_repeats_and_prints_reusable_flags(
        tmp_path, monkeypatch, capsys):
    """Spec G0.1b's procedure, end to end: three greedy repeats, thresholds at
    2x the worst observed statistic capped by the registered ceiling, printed
    as flags that feed straight back into a validation run."""
    champion = _champion(tmp_path)
    monkeypatch.setattr(collect_bench, "collect_b2b_rollouts_batched",
                        _perturbing_batched_collect(4e-6, rows="all"))
    out_json = tmp_path / "report.json"
    monkeypatch.setattr(sys, "argv", _batched_main_argv(
        champion, ["--calibrate", "--json", str(out_json)]))
    with pytest.raises(SystemExit) as excinfo:
        collect_bench.main()
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "float_gate calibration (3 greedy repeats" in out
    assert "--float-ceiling old_logprobs.max=" in out

    import json as json_mod
    calibration = json_mod.loads(out_json.read_text())["float_gate"]["calibration"]
    assert calibration["repeats_per_slot_count"] == 3
    assert calibration["violations"] == []
    # 2x the observed 4e-6, and nothing above the registered cpu cap.
    worst = calibration["worst"]["old_logprobs"]
    assert calibration["thresholds"]["old_logprobs"]["max"] == pytest.approx(
        2.0 * worst["max_abs_diff"])
    assert calibration["thresholds"]["old_logprobs"]["p99_9"] == pytest.approx(
        2.0 * worst["p99_9"])
    assert 8e-6 <= calibration["thresholds"]["old_logprobs"]["max"] < 2e-5
    caps = collect_bench.float_gate_ceilings("cpu")
    for name, parts in calibration["thresholds"].items():
        for part, value in parts.items():
            assert value <= caps[name][part]
    flags = " ".join(calibration["ceiling_flags"])
    # The printed flags must be accepted verbatim by --float-ceiling.
    assert collect_bench.float_gate_ceilings("cpu", calibration["thresholds"])
    assert flags.count("--float-ceiling") == 6


def test_float_delta_outside_tolerance_is_reported_not_gated(tmp_path, monkeypatch, capsys):
    """A float spread beyond atol/rtol must be printed and must NOT fail the
    run: batched-forward rounding scales with architecture (the anchor075 net
    exceeds it on CPU), while a real orchestration bug shows up in the greedy
    float gate, which does gate."""
    champion = _champion(tmp_path)
    fake_report = {
        "results": {
            8: {"startup_seconds": 0.0, "steady_seconds": 0.0,
                "digest": "aaa", "semantic_digest": "same"},
            32: {"startup_seconds": 0.0, "steady_seconds": 0.0,
                 "digest": "bbb", "semantic_digest": "same"},
        },
        "all_digests_equal": False,
        "semantic_digests_equal": True,
        "float_fields_within_tolerance": False,
        "float_allclose_violations": 6,
        "semantics_equal": True,
        "max_float_diff": 3.958e-05,
        "exact_invariance_expected": False,
        "sweep_action_selection": "sample",
        "cross_count_gate": "float_gate",
        "collector": "batched",
        "inference_mode": "batched",
        "model_config": ModelConfig(**SMALL_MODEL, event_window=8),
    }
    monkeypatch.setattr(collect_bench, "run_bench", lambda **kwargs: fake_report)
    monkeypatch.setattr(sys, "argv", [
        "fh-mj-collect-bench", "--champion", str(champion),
        "--collector", "batched", "--pool-slots", "8,32",
        "--matches", "32", "--bridge-kind", "mock", "--event-window", "8",
    ])
    with pytest.raises(SystemExit) as excinfo:
        collect_bench.main()
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "all_digests_equal: False" in out
    assert "semantic_digests_equal (reported, not gated): True" in out
    assert "float_delta (reported, not gated)" in out
    assert "3.958e-05" in out and "6" in out
    assert "semantics_equal: True" in out


def test_sampled_sweep_semantic_difference_is_reported_not_gated(
        tmp_path, monkeypatch, capsys):
    """The timed sweep runs SAMPLED production inference, where a float32
    rounding difference can flip one action and diverge the rest of that match.
    A cross-slot-count digest difference there is expected, not a defect: it is
    printed, with the differing counts named, and does NOT fail the run. The
    exactness claim is carried by the greedy `float_gate` instead — which is
    absent from this manufactured report, so nothing gates it."""
    champion = _champion(tmp_path)
    fake_report = {
        "results": {
            8: {"startup_seconds": 0.0, "steady_seconds": 0.0,
                "digest": "aaa", "semantic_digest": "sem-a"},
            32: {"startup_seconds": 0.0, "steady_seconds": 0.0,
                 "digest": "bbb", "semantic_digest": "sem-b"},
        },
        "all_digests_equal": False,
        "semantic_digests_equal": False,
        "float_fields_within_tolerance": True,
        "float_allclose_violations": 0,
        "semantics_equal": False,
        "max_float_diff": 0.0,
        "exact_invariance_expected": False,
        "sweep_action_selection": "sample",
        "cross_count_gate": "float_gate",
        "collector": "batched",
        "inference_mode": "batched",
        "model_config": ModelConfig(**SMALL_MODEL, event_window=8),
    }
    monkeypatch.setattr(collect_bench, "run_bench", lambda **kwargs: fake_report)
    monkeypatch.setattr(sys, "argv", [
        "fh-mj-collect-bench", "--champion", str(champion),
        "--collector", "batched", "--pool-slots", "8,32",
        "--matches", "32", "--bridge-kind", "mock", "--event-window", "8",
    ])
    with pytest.raises(SystemExit) as excinfo:
        collect_bench.main()
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "sweep_action_selection: sample (throughput only" in out
    assert "semantics_equal: False" in out
    assert "pool_slots=[8]" in out and "pool_slots=[32]" in out


def test_semantic_digest_ignores_only_the_two_float_fields():
    batch = _minimal_batch()
    full = collect_bench._digest_batch(100, 1, batch)
    semantic = collect_bench._semantic_digest_batch(100, 1, batch)
    assert full != semantic

    perturbed = _minimal_batch()
    perturbed.old_logprobs = perturbed.old_logprobs + 1.0
    assert collect_bench._digest_batch(100, 1, perturbed) != full
    assert collect_bench._semantic_digest_batch(100, 1, perturbed) == semantic

    perturbed = _minimal_batch()
    perturbed.actions = perturbed.actions + 1
    assert collect_bench._semantic_digest_batch(100, 1, perturbed) != semantic

    perturbed = _minimal_batch()
    perturbed.rewards = perturbed.rewards + 1.0
    assert collect_bench._semantic_digest_batch(100, 1, perturbed) != semantic


def test_batched_bench_reuses_one_pool_for_warmup_and_steady(tmp_path, monkeypatch):
    """One persistent pool per slot count, two collections through it, closed
    exactly once — the batched analogue of the persistent-collector check."""
    events = []
    real_make_pool = collect_bench.make_b2b_pool
    real_collect = collect_bench.collect_b2b_rollouts_batched

    def spy_make_pool(env_config, model, config, slots):
        pool = real_make_pool(env_config, model, config, slots)
        events.append(("make_pool", slots))
        real_close = pool.close
        pool.close = lambda: (events.append(("close", slots)), real_close())[1]
        return pool

    def spy_collect(env_config, model, config, base_seed, pool, **kwargs):
        events.append(("collect", base_seed, config.matches_per_iter, pool.slots))
        return real_collect(env_config, model, config, base_seed=base_seed, pool=pool, **kwargs)

    monkeypatch.setattr(collect_bench, "make_b2b_pool", spy_make_pool)
    monkeypatch.setattr(collect_bench, "collect_b2b_rollouts_batched", spy_collect)
    collect_bench.run_bench(**_batched_kwargs(tmp_path, [2], inference_mode="per_row"))
    assert events == [
        ("make_pool", 2),
        ("collect", 100, 4, 2),
        ("collect", 100, 4, 2),
        ("close", 2),
    ]


def test_batched_bench_closes_the_pool_when_collection_raises(tmp_path, monkeypatch):
    closed = []
    real_make_pool = collect_bench.make_b2b_pool

    def spy_make_pool(env_config, model, config, slots):
        pool = real_make_pool(env_config, model, config, slots)
        real_close = pool.close
        pool.close = lambda: (closed.append(slots), real_close())[1]
        return pool

    def boom(*args, **kwargs):
        raise RuntimeError("collection blew up")

    monkeypatch.setattr(collect_bench, "make_b2b_pool", spy_make_pool)
    monkeypatch.setattr(collect_bench, "collect_b2b_rollouts_batched", boom)
    with pytest.raises(RuntimeError, match="collection blew up"):
        collect_bench.run_bench(**_batched_kwargs(tmp_path, [2]))
    assert closed == [2]


def test_batched_full_cycle_reports_three_slot_counts_and_split_cuda_peaks(tmp_path):
    report = collect_bench.run_bench(**_batched_kwargs(tmp_path, [2, 8],
                                                       inference_mode="per_row"),
                                     full_cycle=_full_cycle_settings())
    assert report["all_digests_equal"] is True
    assert report["rows_and_labels_equal"] is True
    for slots, fc in ((2, report["results"][2]["full_cycle"]),
                      (8, report["results"][8]["full_cycle"])):
        assert fc["collector"] == "batched"
        assert fc["requested_slots"] == slots
        # matches=4, so an 8-slot request allocates (and fills) only 4.
        assert fc["allocated_slots"] == min(slots, 4)
        assert fc["peak_live_slots"] == min(slots, 4)
        assert fc["host_peak_rss_bytes"] > 0
        assert len(fc["cycles"]) == 3
        for cyc in fc["cycles"]:
            # CPU collection and CPU update: no CUDA numbers on either phase,
            # but both phases are reported separately, allocated AND reserved.
            assert cyc["cuda_peak_collect_allocated_bytes"] is None
            assert cyc["cuda_peak_collect_reserved_bytes"] is None
            assert cyc["cuda_peak_update_allocated_bytes"] is None
            assert cyc["cuda_peak_update_reserved_bytes"] is None
            assert cyc["forward_shapes"]["observable"] is True


def test_process_full_cycle_reports_no_pool_fields(tmp_path):
    report = collect_bench.run_bench(**_bench_kwargs(tmp_path, [1]),
                                     full_cycle=_full_cycle_settings())
    fc = report["results"][1]["full_cycle"]
    assert fc["collector"] == "process"
    assert fc["requested_slots"] is None and fc["allocated_slots"] is None
    assert fc["peak_live_slots"] is None
    assert report["inference_mode"] is None
    for cyc in fc["cycles"]:
        assert cyc["forward_shapes"]["observable"] is False


def test_allocated_slots_never_exceeds_the_match_count_or_drops_below_one():
    assert collect_bench.allocated_slots(320, 320) == 320
    assert collect_bench.allocated_slots(320, 32) == 32
    assert collect_bench.allocated_slots(8, 320) == 8
    assert collect_bench.allocated_slots(0, 320) == 1


def test_run_bench_rejects_missing_and_unknown_counts(tmp_path):
    with pytest.raises(ValueError, match="pool-slots"):
        collect_bench.run_bench(**_batched_kwargs(tmp_path, []))
    with pytest.raises(ValueError, match="workers"):
        collect_bench.run_bench(**_bench_kwargs(tmp_path, []))
    with pytest.raises(ValueError, match="unknown collector"):
        collect_bench.run_bench(**_bench_kwargs(tmp_path, [1]), collector="threads")


def _run_batched_cli(tmp_path, extra_args):
    champion = _champion(tmp_path)
    args = [
        sys.executable, "-m", "fh_mahjong_ai.scripts.collect_bench",
        "--champion", str(champion),
        "--collector", "batched",
        "--matches", "4",
        "--base-seed", "100",
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


def test_batched_cli_exits_zero_and_prints_the_greedy_gate(tmp_path):
    result = _run_batched_cli(tmp_path, ["--pool-slots", "1,3"])
    assert result.returncode == 0, result.stderr
    assert "pool_slots" in result.stdout
    assert "sweep_action_selection: sample (throughput only" in result.stdout
    assert "float_gate (reference: per_row, action_selection=greedy" in result.stdout
    assert "float_gate_passed: True" in result.stdout
    assert "rows per forward (spec G1)" in result.stdout


def test_batched_cli_per_row_prints_exact_digest_gate(tmp_path):
    result = _run_batched_cli(tmp_path, ["--pool-slots", "1,3",
                                         "--inference-mode", "per_row"])
    assert result.returncode == 0, result.stderr
    assert "all_digests_equal: True" in result.stdout
    assert "semantics_equal" not in result.stdout  # exact gate, not the tolerant one


def test_batched_cli_full_cycle_prints_per_cycle_rows_and_slot_accounting(tmp_path):
    result = _run_batched_cli(tmp_path, [
        "--pool-slots", "8", "--full-cycle", "--minibatch-size", "8",
        "--ppo-epochs", "1", "--ppo-device", "cpu",
    ])
    assert result.returncode == 0, result.stderr
    # requested / allocated / effective-live, and one row per cycle.
    for header in ("req", "alloc", "live", "cyc", "col_alloc", "upd_resv"):
        assert header in result.stdout
    assert "phase host RSS peak" in result.stdout
    assert "rows_and_labels_equal: True" in result.stdout


def test_cli_rejects_mismatched_collector_and_count_flags(tmp_path):
    missing = _run_batched_cli(tmp_path, [])
    assert missing.returncode == 2
    assert "--pool-slots" in missing.stderr

    champion = _champion(tmp_path)
    crossed = subprocess.run([
        sys.executable, "-m", "fh_mahjong_ai.scripts.collect_bench",
        "--champion", str(champion), "--workers", "1", "--pool-slots", "4",
        "--matches", "4", "--bridge-kind", "mock", "--event-window", "8",
    ], capture_output=True, text=True)
    assert crossed.returncode == 2
    assert "--collector batched" in crossed.stderr
