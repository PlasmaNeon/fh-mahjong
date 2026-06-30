import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.storage import save_checkpoint


def _mcfg():
    return ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)


def test_extract_deployable_student_exact_equivalence(tmp_path):
    from fh_mahjong_ai.oracle import build_oracle_model, extract_deployable_student
    mcfg = _mcfg()
    # a 51ch oracle warm-started from a random 39ch anchor (just need a 51ch net)
    anchor = tmp_path / "anchor.pt"
    save_checkpoint(anchor, PolicyValueNet(EnvConfig(), mcfg))
    oracle = build_oracle_model(EnvConfig(oracle_observation=True), mcfg, anchor, device="cpu")
    # perturb the oracle's input-conv oracle channels so they are nonzero (training would)
    with torch.no_grad():
        oracle.plane_stem[0].weight[:, 39:] = torch.randn_like(oracle.plane_stem[0].weight[:, 39:])

    student = extract_deployable_student(oracle, EnvConfig(), mcfg).eval()
    oracle.eval()

    # student input conv == oracle input conv first 39 channels
    assert torch.allclose(student.plane_stem[0].weight, oracle.plane_stem[0].weight[:, :39])

    # student(39ch obs) logits == oracle(same obs zero-padded to 51ch) logits
    rng = np.random.default_rng(0)
    p39 = rng.standard_normal((1, 39, 42, 1)).astype(np.float32)
    p51 = np.concatenate([p39, np.zeros((1, 12, 42, 1), np.float32)], axis=1)
    sc = rng.standard_normal((1, 58)).astype(np.float32)
    mask = np.ones((1, 204), np.int8)
    with torch.no_grad():
        ls, _ = student(torch.from_numpy(p39), torch.from_numpy(sc), torch.from_numpy(mask))
        lo, _ = oracle(torch.from_numpy(p51), torch.from_numpy(sc), torch.from_numpy(mask))
    assert torch.allclose(ls, lo, atol=1e-5)


def test_feature_dropout_schedule():
    from fh_mahjong_ai.oracle import feature_dropout_schedule
    T = 50
    vals = [feature_dropout_schedule(i, T) for i in range(1, T + 1)]
    assert vals[0] == 0.0                      # first iter: full perfect info
    assert vals[-1] == 1.0                     # last iter: fully masked
    assert all(0.0 <= v <= 1.0 for v in vals)  # probability
    assert all(b >= a - 1e-9 for a, b in zip(vals, vals[1:]))  # monotone nondecreasing
    # the first 20% hold at 0, the final 20% hold at 1
    assert feature_dropout_schedule(10, T) == 0.0   # iter 10 / 50 = 0.2 boundary still 0
    assert feature_dropout_schedule(45, T) == 1.0   # within the final-20% hold
