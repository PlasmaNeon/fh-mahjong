"""Collector parity gates for the batched-b2b-collector work (spec G0).

`test_process_collector_golden_digest` pins `collect_b2b_rollouts` output
(every RolloutBatch field + match_telemetry) to hashes recorded from `main`
before any refactor. If it fails, the process collector's output changed —
that is a bug, never a reason to update the constants.
"""

from __future__ import annotations

import hashlib
import json

import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.scripts.collect_bench import _digest_batch
from fh_mahjong_ai.train_b2b import collect_b2b_rollouts

from conftest import SMALL_MODEL

GOLDEN_MATCHES = 3
GOLDEN_BASE_SEED = 4242
GOLDEN_MAX_STEPS = 20000
GOLDEN_BATCH_DIGEST = "b422b1d389f56b4a30ed5dac5789075555ce6174cb9f24dc412b55e478f7c1e0"
GOLDEN_TELEMETRY_SHA256 = "a757d5ec33e5c3f2c512c7d96fdb1b094c4cfd0537babfa8ddcadd1e3136dbd9"


def _golden_env_and_model():
    env = EnvConfig(bridge_kind="go", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=GOLDEN_MAX_STEPS)
    torch.manual_seed(0)
    model = PolicyValueNet(EnvConfig(bridge_kind="go"),
                           ModelConfig(**SMALL_MODEL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    return env, model


def golden_digests(batch) -> tuple[str, str]:
    tel = hashlib.sha256(json.dumps(batch.match_telemetry, sort_keys=True).encode()).hexdigest()
    return _digest_batch(GOLDEN_BASE_SEED, GOLDEN_MATCHES, batch), tel


def test_process_collector_golden_digest():
    env, model = _golden_env_and_model()
    cfg = PPOConfig(device="cpu", matches_per_iter=GOLDEN_MATCHES,
                    max_steps_per_episode=GOLDEN_MAX_STEPS, match_mode="chongci")
    batch = collect_b2b_rollouts(env, model, cfg, base_seed=GOLDEN_BASE_SEED)
    assert golden_digests(batch) == (GOLDEN_BATCH_DIGEST, GOLDEN_TELEMETRY_SHA256)
