"""Oracle-guiding helpers (Phase 1): build a perfect-information policy
warm-started from the 39-channel anchor."""
from __future__ import annotations

from pathlib import Path

import torch

from .config import EnvConfig, ModelConfig
from .model import PolicyValueNet
from .storage import load_compatible_checkpoint


def build_oracle_model(env_config: EnvConfig, model_config: ModelConfig,
                       anchor_checkpoint: Path, device: str = "cpu") -> PolicyValueNet:
    """Build a 51-channel oracle `PolicyValueNet` warm-started from the 39-channel
    anchor. Every layer except the first plane conv is loaded by shape
    (`load_compatible_checkpoint` skips the 39->51 conv); the input conv is then
    initialized so the oracle equals the anchor when the 12 oracle channels are 0:
    the anchor's weights occupy the first 39 input channels and the new 12 are
    zeroed."""
    oracle = PolicyValueNet(env_config, model_config).to(device)
    # Load all same-shape tensors (skips plane_stem.0.weight: [C,39,3,3] vs [C,51,3,3]).
    load_compatible_checkpoint(Path(anchor_checkpoint), oracle)
    # Read the anchor's input conv weight directly from the checkpoint.
    payload = torch.load(Path(anchor_checkpoint), map_location="cpu")
    anchor_w = payload["model"]["plane_stem.0.weight"]  # [C, 39, 3, 3]
    base = anchor_w.shape[1]  # 39
    with torch.no_grad():
        w = oracle.plane_stem[0].weight
        w.zero_()
        w[:, :base].copy_(anchor_w.to(w.device))
    oracle.eval()
    return oracle
