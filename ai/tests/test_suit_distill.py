"""Suit distillation (PPOConfig.suit_distill_coef): spec worklog/specs/20261002-suit-distill-lap.md."""

import os
from dataclasses import replace

import numpy as np
import pytest
import torch

from conftest import small_model_config
from fh_mahjong_ai.batched_b2b import _ARRAY_ROW_DTYPES, _TEACHER_ROW_DTYPE, _ArrayRowSink
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig, RolloutBatch
from fh_mahjong_ai.scripts.collect_bench import _digest_batch, _semantic_digest_batch
from fh_mahjong_ai.suit_symmetry import (
    SUIT_PERMUTATIONS, average_view_log_probs, permute_rows, stack_views, suit_averaged_log_probs,
    teacher_log_probs, unpermute_action_values,
)

requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library"
)


def test_config_validates_the_coefficient():
    with pytest.raises(ValueError, match="suit_distill_coef"):
        PPOConfig(collector="process", suit_distill_coef=1.0)
    with pytest.raises(ValueError, match=">= 0"):
        PPOConfig(collector="batched", suit_distill_coef=-0.5)
    assert PPOConfig(collector="batched", suit_distill_coef=1.0).suit_distill_coef == 1.0
    assert PPOConfig().suit_distill_coef == 0.0


def test_cli_requires_the_batched_collector(monkeypatch, capsys, tmp_path):
    from fh_mahjong_ai.scripts import train_b2b as cli
    champion = tmp_path / "champion.pt"
    champion.write_bytes(b"")
    monkeypatch.setattr("sys.argv", ["fh-mj-train-b2b", "--suit-distill-coef", "1.0",
                                     "--champion", str(champion), "--checkpoint-dir", str(tmp_path),
                                     "--collector", "process"])
    with pytest.raises(SystemExit):
        cli.main()
    assert "--suit-distill-coef requires --collector batched" in capsys.readouterr().err


def test_resume_rejects_a_changed_coefficient_and_reads_legacy_states_as_off():
    from fh_mahjong_ai import train_state
    env = EnvConfig(bridge_kind="mock")

    def echo(coef):
        config = PPOConfig(device="cpu", collector="batched", suit_distill_coef=coef)
        return train_state._train_b2b_config_echo(config, ModelConfig(), env)

    train_state._validate_resume_config_echo(echo(1.0), echo(1.0))
    with pytest.raises(ValueError, match="suit_distill_coef"):
        train_state._validate_resume_config_echo(echo(1.0), echo(0.0))
    legacy = echo(0.0)
    del legacy["ppo_config"]["suit_distill_coef"]
    train_state._validate_resume_config_echo(echo(0.0), legacy)
    with pytest.raises(ValueError, match="suit_distill_coef"):
        train_state._validate_resume_config_echo(echo(1.0), legacy)


def _random_rows(n=7, window=8, seed=4):
    env = EnvConfig()
    rng = np.random.default_rng(seed)
    planes = rng.random((n, *env.plane_shape), dtype=np.float32)
    scalars = rng.random((n, env.scalar_features), dtype=np.float32)
    masks = (rng.random((n, env.action_space_size)) < 0.25).astype(np.int8)
    masks[:, 5] = 1
    events = rng.integers(0, 1 << 15, size=(n, window), dtype=np.uint32)
    lengths = rng.integers(0, window + 1, size=n).astype(np.int64)
    return planes, scalars, masks, events, lengths


def test_suit_averaged_log_probs_keeps_its_arithmetic():
    torch.manual_seed(3)
    model = PolicyValueNet(EnvConfig(), small_model_config(event_window=8)).eval()
    planes, scalars, masks, events, lengths = _random_rows()
    total, value = suit_averaged_log_probs(model, planes, scalars, masks, events, lengths)
    # The arithmetic as it stood before the helpers were factored out.
    n = planes.shape[0]
    views = [permute_rows(planes, scalars, masks, events, perm) for perm in SUIT_PERMUTATIONS]
    p, s, m, e = (np.concatenate(parts) for parts in zip(*views))
    with torch.inference_mode():
        logits, values = model(torch.from_numpy(p), torch.from_numpy(s), torch.from_numpy(m),
                               events=torch.from_numpy(e.astype(np.int64)),
                               event_lengths=torch.from_numpy(np.tile(lengths, 6)))
    logp = torch.log_softmax(logits.double(), dim=1).numpy()
    want = np.zeros((n, masks.shape[1]))
    for k, perm in enumerate(SUIT_PERMUTATIONS):
        want += unpermute_action_values(logp[k * n:(k + 1) * n], perm)
    want /= 6
    want[masks == 0] = -np.inf
    assert np.array_equal(total, want)
    assert np.array_equal(value, values.reshape(6, n).double().mean(dim=0).numpy())


def test_stack_views_is_view_major():
    planes, scalars, masks, events, _ = _random_rows(n=3)
    p, s, m, e = stack_views(planes, scalars, masks, events)
    assert p.shape[0] == 18
    assert np.array_equal(p[:3], planes) and np.array_equal(m[:3], masks)  # view 0 is identity
    second = permute_rows(planes, scalars, masks, events, SUIT_PERMUTATIONS[1])
    assert np.array_equal(p[3:6], second[0]) and np.array_equal(e[3:6], second[3])


def test_teacher_log_probs_is_float32_with_finite_masked_entries():
    averaged = np.array([[-0.5, -np.inf, -1.25]])
    teacher = teacher_log_probs(averaged)
    assert teacher.dtype == np.float32
    assert teacher[0, 1] == np.finfo(np.float32).min
    assert teacher[0, 0] == np.float32(-0.5) and teacher[0, 2] == np.float32(-1.25)


def test_average_view_log_probs_of_identical_views_is_the_view():
    masks = np.array([[1, 0, 1, 1] + [0] * 200], dtype=np.int8)
    logits = torch.randn(6, 204)
    logits[:] = logits[0]  # every view the same, and the actions untouched by these maps
    total = average_view_log_probs(logits, masks, symmetries=SUIT_PERMUTATIONS[:1] * 6)
    want = torch.log_softmax(logits[0].double(), dim=0).numpy()
    assert np.allclose(total[0, [0, 2, 3]], want[[0, 2, 3]])
    assert np.isneginf(total[0, 1])


def _tiny_batch(n=3):
    z = np.zeros((n, 2), np.float32)
    return RolloutBatch(planes=z, scalars=z, action_mask=z.astype(np.int8),
                        actions=np.zeros(n, np.int64), old_logprobs=np.zeros(n, np.float32),
                        values=np.zeros(n, np.float32), rewards=np.zeros(n, np.float32),
                        dones=np.ones(n, np.float32))


def test_digest_covers_the_teacher_only_when_present():
    batch = _tiny_batch()
    assert batch.teacher_logprobs is None
    zeros = replace(batch, teacher_logprobs=np.zeros((3, 204), np.float32))
    ones = replace(batch, teacher_logprobs=np.ones((3, 204), np.float32))
    assert _digest_batch(1, 1, zeros) != _digest_batch(1, 1, batch)
    assert _digest_batch(1, 1, zeros) != _digest_batch(1, 1, ones)
    # A batched forward rounds the teacher by batch composition, like old_logprobs.
    assert _semantic_digest_batch(1, 1, zeros) == _semantic_digest_batch(1, 1, ones)


def test_row_sink_carries_teacher_rows_and_refuses_a_short_teacher():
    sink = _ArrayRowSink(capacity=10, dtypes={**_ARRAY_ROW_DTYPES, **_TEACHER_ROW_DTYPE})
    rows = {"planes": [np.zeros((2, 3), np.float32)] * 2, "scalars": [np.zeros(4, np.float32)] * 2,
            "masks": [np.zeros(5, np.int8)] * 2, "events": [np.zeros(1, np.uint32)] * 2,
            "actions": [0, 1], "teacher": [np.full(5, -1.0, np.float32)] * 2}
    sink.write(rows)
    assert sink.arrays()["teacher"].shape == (2, 5)
    assert sink.arrays()["teacher"].dtype == np.float32
    with pytest.raises(RuntimeError, match="teacher"):
        sink.write({**rows, "teacher": rows["teacher"][:1]})
