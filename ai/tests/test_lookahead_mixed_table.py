"""Mixed look-ahead tables: a v0 net at a table that encodes v>0 observations.

The env encodes one observation for every seat. A v0 net there is handed the observation's first
`observation_plane_channels(False, 0)` channels — its native v0 observation (oracle off) — so
neither its logits nor its privileged critic read the look-ahead block.
"""

import json
import os

import numpy as np
import pytest
import torch

from conftest import SMALL_MODEL
from fh_mahjong_ai.config import EnvConfig, ModelConfig, adapter_plane_channels
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.policies import PlaneTrimPolicy, TorchGreedyPolicy

requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library")
B2B = dict(**SMALL_MODEL, event_window=8, privileged_critic=True, aux_heads=True)
KW = dict(match_mode="chongci", chongci_max_hands=3, max_steps_per_episode=4000)


def _net(seed: int, version: int) -> PolicyValueNet:
    torch.manual_seed(seed)
    return PolicyValueNet(EnvConfig(lookahead_version=version),
                          ModelConfig(**B2B, lookahead_version=version)).eval()


def test_adapter_plane_channels():
    assert adapter_plane_channels(1, 1, False) is None
    assert adapter_plane_channels(0, 0, False) is None
    assert adapter_plane_channels(0, 1, False) == 39
    with pytest.raises(ValueError, match="lookahead_version"):
        adapter_plane_channels(1, 0, False)  # a v1 net cannot be fed a v0 observation
    with pytest.raises(ValueError, match="oracle"):
        adapter_plane_channels(0, 1, True)   # the oracle block would sit after the look-ahead block


def _tensors(obs, window):
    planes = torch.from_numpy(np.asarray(obs.planes, dtype=np.float32))[None]
    scalars = torch.from_numpy(np.asarray(obs.scalars, dtype=np.float32))[None]
    mask = torch.from_numpy(np.asarray(obs.action_mask, dtype=np.int8))[None]
    events = np.asarray(obs.event_history, dtype=np.int64)[-window:]
    ev = torch.zeros(1, window, dtype=torch.int64)
    ev[0, :len(events)] = torch.from_numpy(events)
    return planes, scalars, mask, ev, torch.tensor([len(events)])


@requires_go_lib
def test_v0_net_sees_its_native_observation_at_a_v1_table():
    # Lockstep: the same v0 net plays every seat of a v0 env and of a v1 env from the same seed.
    from fh_mahjong_ai.env import MahjongEnv
    from fh_mahjong_ai.bridge import build_bridge
    net = _net(3, 0)
    native_policy = TorchGreedyPolicy(net)
    adapted_policy = PlaneTrimPolicy(TorchGreedyPolicy(net), adapter_plane_channels(0, 1, False))
    envs = []
    for version in (0, 1):
        cfg = EnvConfig(learning_seats=(0, 1, 2, 3), auto_play_heuristics=False, event_history_window=8,
                        match_mode="chongci", chongci_max_hands=2, lookahead_version=version)
        envs.append(MahjongEnv(cfg, build_bridge(cfg)))
    try:
        decisions = value_differs = 0
        for seed in (41, 415):
            obs0, obs1 = envs[0].reset(seed=seed), envs[1].reset(seed=seed)
            while obs0.legal_actions and decisions < 400:
                assert np.asarray(obs1.planes).shape[0] == 52
                assert np.array_equal(np.asarray(obs1.planes)[:39], obs0.planes)
                assert np.array_equal(obs1.scalars, obs0.scalars)
                assert np.array_equal(obs1.action_mask, obs0.action_mask)
                assert np.array_equal(obs1.event_history, obs0.event_history)
                native, adapted = native_policy.choose(obs0), adapted_policy.choose(obs1)
                assert adapted.action_id == native.action_id
                with torch.inference_mode():
                    p0, s, m, ev, ln = _tensors(obs0, 8)
                    p1 = _tensors(obs1, 8)[0]
                    logits0, value0 = net(p0, s, m, events=ev, event_lengths=ln)
                    trimmed = _tensors(adapted_policy.trim(obs1), 8)[0]
                    logits1, value1 = net(trimmed, s, m, events=ev, event_lengths=ln)
                    _, raw_value = net(p1, s, m, events=ev, event_lengths=ln)
                assert torch.equal(logits1, logits0) and torch.equal(value1, value0)
                value_differs += int(not torch.equal(raw_value, value0))
                step0, step1 = envs[0].step(native.action_id), envs[1].step(adapted.action_id)
                assert np.array_equal(step0.rewards, step1.rewards)
                if step0.terminated or step0.truncated:
                    break
                obs0, obs1 = step0.observation, step1.observation
                decisions += 1
        assert decisions > 50
        # Untrimmed, the privileged critic reads look-ahead planes as oracle input.
        assert value_differs > 0
    finally:
        for env in envs:
            env.close()


@requires_go_lib
def test_mixed_table_per_row_batched_matches_the_sequential_adapter():
    from fh_mahjong_ai.batched_eval import evaluate_seats_batched
    from fh_mahjong_ai.evaluate import evaluate_policy_online
    cand, opp = _net(1, 1), _net(2, 0)
    seat_seeds = {0: [41, 42], 1: [43], 2: [415], 3: [616]}
    run = evaluate_seats_batched(cand, seat_seeds, event_history_window=8, lookahead_version=1,
                                 slots=3, inference_mode="per_row", opponent_model=opp, **KW)
    for seat, seeds in seat_seeds.items():
        sequential = evaluate_policy_online(
            policy=TorchGreedyPolicy(cand), episodes=len(seeds), seeds=seeds, learning_seat=seat,
            event_history_window=8, lookahead_version=1,
            opponent_policy=PlaneTrimPolicy(TorchGreedyPolicy(opp), 39), **KW)
        assert json.dumps(run["seat_reports"][seat], sort_keys=True, default=str) == \
            json.dumps(sequential, sort_keys=True, default=str)


def test_mixed_table_refuses_every_other_mismatch():
    from fh_mahjong_ai.batched_eval import evaluate_seats_batched
    with pytest.raises(ValueError, match="lookahead_version"):
        # The candidate must match the table; only a v0 opponent is adapted.
        evaluate_seats_batched(_net(1, 0), {0: [1]}, event_history_window=8, lookahead_version=1,
                               opponent_model=_net(2, 0))
    with pytest.raises(ValueError, match="lookahead_version"):
        evaluate_seats_batched(_net(1, 0), {0: [1]}, event_history_window=8, lookahead_version=0,
                               opponent_model=_net(2, 1))
    with pytest.raises(ValueError, match="oracle"):
        evaluate_seats_batched(_net(1, 1), {0: [1]}, event_history_window=8, lookahead_version=1,
                               oracle_observation=True, opponent_model=_net(2, 0))


def test_plane_trim_policy_trims_only_the_planes():
    seen = []

    class Recorder:
        def choose(self, observation):
            seen.append(observation)
            return "choice"

    from fh_mahjong_ai.types import Observation
    obs = Observation(seat=2, planes=np.arange(52 * 42, dtype=np.float32).reshape(52, 42, 1),
                      scalars=np.ones(58, dtype=np.float32), action_mask=np.ones(204, dtype=np.int8))
    assert PlaneTrimPolicy(Recorder(), 39).choose(obs) == "choice"
    assert seen[0].planes.shape == (39, 42, 1)
    assert np.array_equal(seen[0].planes, obs.planes[:39])
    assert seen[0].seat == 2 and seen[0].scalars is obs.scalars
    assert seen[0].action_mask is obs.action_mask and seen[0].event_history is obs.event_history


ADAPTER = {"lookahead_version": 0, "table_lookahead_version": 1, "plane_channels": 39}
SMALL_FLAGS = ["--model-channels", "16", "--model-residual-blocks", "1",
               "--model-plane-feature-dim", "32", "--model-scalar-hidden-dim", "16",
               "--model-trunk-hidden-dim", "32", "--model-value-hidden-dim", "16",
               "--model-q-hidden-dim", "16"]


def _save(tmp_path, name: str, seed: int, version: int):
    from fh_mahjong_ai.storage import model_config_metadata, save_checkpoint
    net = _net(seed, version)
    path = tmp_path / name
    save_checkpoint(path, net, metadata={"model_config": model_config_metadata(net.model_config)})
    return path


def _canon(payload: dict) -> str:
    payload = dict(payload)
    payload.pop("evaluator", None)
    payload.pop("evaluator_timing", None)
    return json.dumps(payload, sort_keys=True, default=str)


def test_load_opponent_policy_adapts_a_v0_opponent_and_records_it(tmp_path):
    from fh_mahjong_ai.scripts.evaluate import load_opponent_policy
    v0, v1 = _save(tmp_path, "v0.pt", 2, 0), _save(tmp_path, "v1.pt", 1, 1)
    policy, record = load_opponent_policy(v0, "cpu", 8, lookahead_version=1)
    assert isinstance(policy, PlaneTrimPolicy) and policy.channels == 39
    assert record["lookahead_adapter"] == ADAPTER
    same, same_record = load_opponent_policy(v0, "cpu", 8, lookahead_version=0)
    assert isinstance(same, TorchGreedyPolicy) and "lookahead_adapter" not in same_record
    with pytest.raises(ValueError, match="lookahead_version"):
        load_opponent_policy(v1, "cpu", 8, lookahead_version=0)


@requires_go_lib
def test_benchmark_cli_mixed_table_batched_reproduces_the_sequential_payload(tmp_path):
    from fh_mahjong_ai.scripts import benchmark as benchmark_cli
    cand, opp = _save(tmp_path, "cand.pt", 1, 1), _save(tmp_path, "opp.pt", 2, 0)
    base = ["--checkpoint", str(cand), "--opponent-checkpoint", str(opp), "--episodes-per-seat", "2",
            "--seed-base", "41", "--chongci-max-hands", "3", "--bootstrap-iters", "10"]
    payloads = {}
    for name, extra in (("sequential", []),
                        ("batched", ["--batched-eval-slots", "3", "--batched-eval-inference", "per_row"])):
        out = tmp_path / f"{name}.json"
        benchmark_cli.main(base + extra + ["--out", str(out)])
        payloads[name] = json.loads(out.read_text())
    assert payloads["batched"]["opponents"]["lookahead_adapter"] == ADAPTER
    assert payloads["batched"]["lookahead_version"] == 1
    assert _canon(payloads["batched"]) == _canon(payloads["sequential"])


@requires_go_lib
def test_evaluate_cli_runs_a_v1_candidate_against_a_v0_opponent(tmp_path, monkeypatch):
    from fh_mahjong_ai.scripts import evaluate as evaluate_cli
    cand, opp = _save(tmp_path, "cand.pt", 1, 1), _save(tmp_path, "opp.pt", 2, 0)
    out = tmp_path / "report.json"
    monkeypatch.setattr("sys.argv", [
        "fh-mj-evaluate", "--checkpoint", str(cand), "--online-episodes", "1", "--seed-window", "41:1",
        "--duplicate-seats", "--opponent-checkpoint", str(opp), "--batched-eval-slots", "4",
        "--match-mode", "chongci", "--chongci-max-hands", "2", "--event-history-window", "8",
        "--model-event-window", "8", "--model-privileged-critic", "--model-aux-heads", *SMALL_FLAGS,
        "--report-output", str(out)])
    evaluate_cli.main()
    online = json.loads(out.read_text())["online"]
    assert online["opponents"]["lookahead_adapter"] == ADAPTER
    assert online["lookahead_version"] == 1
