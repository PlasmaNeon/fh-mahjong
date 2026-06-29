import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import save_checkpoint
from fh_mahjong_ai.oracle import build_oracle_model


def _mcfg():
    return ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)


def test_oracle_warmstart_matches_anchor_when_oracle_channels_zero(tmp_path):
    mcfg = _mcfg()
    anchor_env = EnvConfig()  # 39ch
    anchor = PolicyValueNet(anchor_env, mcfg).eval()
    ckpt = tmp_path / "anchor.pt"
    save_checkpoint(ckpt, anchor)

    oracle_env = EnvConfig(oracle_observation=True)  # 51ch
    oracle = build_oracle_model(oracle_env, mcfg, ckpt, device="cpu").eval()

    # input conv: first 39 channels copied from anchor, last 12 zeroed
    aw = anchor.plane_stem[0].weight.detach()
    ow = oracle.plane_stem[0].weight.detach()
    assert torch.allclose(ow[:, :39], aw)
    assert torch.count_nonzero(ow[:, 39:]) == 0

    # same observation, oracle channels zeroed -> identical policy logits
    rng = np.random.default_rng(0)
    planes39 = rng.standard_normal((1, 39, 42, 1)).astype(np.float32)
    planes51 = np.concatenate([planes39, np.zeros((1, 12, 42, 1), np.float32)], axis=1)
    scalars = rng.standard_normal((1, 58)).astype(np.float32)
    mask = np.ones((1, 204), np.int8)
    with torch.no_grad():
        la, _ = anchor(torch.from_numpy(planes39), torch.from_numpy(scalars), torch.from_numpy(mask))
        lo, _ = oracle(torch.from_numpy(planes51), torch.from_numpy(scalars), torch.from_numpy(mask))
    assert torch.allclose(la, lo, atol=1e-5)
