"""Suit distillation (PPOConfig.suit_distill_coef): spec worklog/specs/20261002-suit-distill-lap.md."""

import os
from dataclasses import replace

import numpy as np
import pytest
import torch

from conftest import SMALL_MODEL, small_model_config
from fh_mahjong_ai.batched_b2b import (
    _ARRAY_ROW_DTYPES, _TEACHER_ROW_DTYPE, _ArrayRowSink, collect_b2b_rollouts_batched, make_b2b_pool,
)
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig, RolloutBatch, masked_distill_kl, ppo_update
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


def test_teacher_log_probs_is_a_distribution_over_the_legal_actions():
    # A mean of log-probabilities is a geometric mean: its probabilities sum to less than 1,
    # and a "KL" against it can go negative. The teacher is that mean renormalized.
    rng = np.random.default_rng(1)
    views = np.log(rng.dirichlet(np.ones(5), size=6))  # six views' log-policies over 5 actions
    averaged = np.concatenate([views.mean(axis=0), [-np.inf]])[None]
    assert np.exp(averaged[0, :5]).sum() < 1
    teacher = teacher_log_probs(averaged)
    assert np.isclose(np.exp(teacher[0, :5].astype(np.float64)).sum(), 1.0, atol=1e-6)
    assert np.allclose(teacher[0, :5] - averaged[0, :5], teacher[0, 0] - averaged[0, 0], atol=1e-6)
    assert teacher[0, 5] == np.finfo(np.float32).min


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


MATCHES, SEED = 4, 3100


def _collect(distill_coef=1.0, suit_augment=False, groups=1, max_steps=4000,
             action_selection="greedy", inference_mode="per_row"):
    env = EnvConfig(bridge_kind="go", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=max_steps, chongci_max_hands=4)
    torch.manual_seed(0)
    model = PolicyValueNet(EnvConfig(bridge_kind="go"),
                           ModelConfig(**SMALL_MODEL, event_window=8, privileged_critic=True,
                                       aux_heads=True)).eval()
    cfg = PPOConfig(device="cpu", matches_per_iter=MATCHES, max_steps_per_episode=max_steps,
                    match_mode="chongci", collector="batched", suit_augment=suit_augment,
                    suit_distill_coef=distill_coef, pool_pipeline_groups=groups)
    pool = make_b2b_pool(env, model, cfg, 3)
    try:
        batch = collect_b2b_rollouts_batched(env, model, cfg, base_seed=SEED, pool=pool,
                                             inference_mode=inference_mode,
                                             action_selection=action_selection)
    finally:
        pool.close()
    return batch, model


@requires_go_lib
@pytest.mark.parametrize("suit_augment", [False, True])
def test_teacher_is_the_suit_averaged_policy_of_each_stored_row(suit_augment):
    batch, model = _collect(suit_augment=suit_augment)
    assert batch.teacher_logprobs.shape == batch.action_mask.shape
    assert batch.teacher_logprobs.dtype == np.float32
    for i in range(len(batch)):
        total, _ = suit_averaged_log_probs(model, batch.planes[i:i + 1], batch.scalars[i:i + 1],
                                           batch.action_mask[i:i + 1], batch.events[i:i + 1],
                                           batch.event_lengths[i:i + 1])
        assert np.array_equal(teacher_log_probs(total)[0], batch.teacher_logprobs[i]), i
    assert (batch.teacher_logprobs[batch.action_mask == 0] == np.finfo(np.float32).min).all()
    legal_mass = np.where(batch.action_mask > 0,
                          np.exp(batch.teacher_logprobs.astype(np.float64)), 0.0).sum(axis=1)
    assert np.allclose(legal_mass, 1.0, atol=1e-5)


@requires_go_lib
def test_coefficient_zero_collects_no_teacher():
    batch, _ = _collect(distill_coef=0.0)
    assert batch.teacher_logprobs is None


@requires_go_lib
@pytest.mark.parametrize("selection, mode", [("greedy", "per_row"), ("sample", "batched")])
def test_distilled_collection_is_deterministic(selection, mode):
    first, _ = _collect(suit_augment=True, action_selection=selection, inference_mode=mode)
    second, _ = _collect(suit_augment=True, action_selection=selection, inference_mode=mode)
    assert first.teacher_logprobs is not None
    assert _digest_batch(SEED, MATCHES, first) == _digest_batch(SEED, MATCHES, second)


@requires_go_lib
def test_teacher_rows_stay_aligned_under_pipelining_and_truncation():
    one, _ = _collect(max_steps=120)
    two, _ = _collect(max_steps=120, groups=2)
    assert one.truncated_matches > 0
    assert len(one.teacher_logprobs) == len(one) and len(two.teacher_logprobs) == len(two)
    assert _digest_batch(SEED, MATCHES, one) == _digest_batch(SEED, MATCHES, two)


def _update_batch(n=32, seed=0):
    """A no-event, no-aux net and a batch whose old_logprobs are that net's own."""
    torch.manual_seed(seed)
    model = PolicyValueNet(EnvConfig(), small_model_config())
    env = EnvConfig()
    rng = np.random.default_rng(seed)
    planes = rng.random((n, *env.plane_shape), dtype=np.float32)
    scalars = rng.random((n, env.scalar_features), dtype=np.float32)
    mask = (rng.random((n, env.action_space_size)) < 0.2).astype(np.int8)
    mask[:, 5] = 1
    with torch.no_grad():
        logits, values = model(torch.from_numpy(planes), torch.from_numpy(scalars),
                               torch.from_numpy(mask))
    logp = torch.log_softmax(logits, dim=-1)
    actions = np.array([rng.choice(np.flatnonzero(row)) for row in mask], dtype=np.int64)
    batch = RolloutBatch(planes=planes, scalars=scalars, action_mask=mask, actions=actions,
                         old_logprobs=logp[torch.arange(n), torch.from_numpy(actions)].numpy(),
                         values=values.reshape(-1).numpy(), rewards=np.zeros(n, np.float32),
                         dones=np.ones(n, np.float32))
    return model, batch, logp.numpy()


def _uniform_teacher(mask):
    legal = mask > 0
    teacher = np.full(mask.shape, np.finfo(np.float32).min, np.float32)
    teacher[legal] = np.repeat(-np.log(legal.sum(axis=1)), legal.sum(axis=1)).astype(np.float32)
    return teacher


def _run(model, batch, coef=1.0, lr=0.0, transfer=False):
    n = len(batch)
    config = PPOConfig(device="cpu", collector="batched", suit_distill_coef=coef, ppo_epochs=1,
                       minibatch_size=n, entropy_coef=0.0, minibatch_device_transfer=transfer)
    optimizer = torch.optim.SGD(model.parameters(), lr=lr)
    return ppo_update(model, optimizer, batch, np.zeros(n, np.float32), np.zeros(n, np.float32),
                      config)


def test_masked_distill_kl_matches_the_definition_and_has_finite_gradients():
    mask = torch.tensor([[1, 1, 0, 1], [0, 1, 1, 0]], dtype=torch.int8)
    logits = torch.randn(2, 4).masked_fill(mask == 0, torch.finfo(torch.float32).min)
    logits.requires_grad_(True)
    teacher = torch.tensor([[-1.0, -1.5, torch.finfo(torch.float32).min, -0.9],
                            [torch.finfo(torch.float32).min, -0.2, -1.7,
                             torch.finfo(torch.float32).min]])
    kl = masked_distill_kl(logits, teacher, mask)
    log_pi = torch.log_softmax(logits.detach(), dim=-1)
    for r in range(2):
        legal = mask[r] > 0
        want = (teacher[r][legal].exp() * (teacher[r][legal] - log_pi[r][legal])).sum()
        assert torch.allclose(kl[r], want, atol=1e-6)
    kl.sum().backward()
    assert torch.isfinite(logits.grad).all()


@pytest.mark.parametrize("transfer", [False, True])
def test_kl_is_zero_when_the_teacher_is_the_policy(transfer):
    model, batch, logp = _update_batch()
    teacher = np.where(batch.action_mask > 0, logp, np.finfo(np.float32).min).astype(np.float32)
    metrics = _run(model, replace(batch, teacher_logprobs=teacher), transfer=transfer)
    assert abs(metrics["distill_kl"]) < 1e-6


@pytest.mark.parametrize("transfer", [False, True])
def test_kl_is_positive_otherwise_and_a_step_lowers_it(transfer):
    model, batch, _ = _update_batch()
    batch = replace(batch, teacher_logprobs=_uniform_teacher(batch.action_mask))
    first = _run(model, batch, coef=10.0, lr=0.5, transfer=transfer)["distill_kl"]
    second = _run(model, batch, coef=10.0, lr=0.5, transfer=transfer)["distill_kl"]
    assert first > 0
    assert second < first


def test_a_distilling_update_refuses_a_batch_without_teacher_rows():
    model, batch, _ = _update_batch()
    with pytest.raises(ValueError, match="teacher_logprobs"):
        _run(model, batch)


def test_coefficient_zero_reports_no_distill_metric():
    model, batch, _ = _update_batch()
    assert "distill_kl" not in _run(model, batch, coef=0.0)
