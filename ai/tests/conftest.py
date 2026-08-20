"""Shared fixtures for the ai test suite.

pytest imports this automatically for every test in the directory, so the
constants and helpers here can be imported by name from any test module:

    from conftest import SMALL_MODEL, small_model_config

Before this existed, 68 test files each rebuilt their own tiny model config and
synthetic observations; a change to ModelConfig's fields meant editing all of
them.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from fh_mahjong_ai.config import EnvConfig, ModelConfig

# A deliberately tiny architecture: big enough to exercise every code path,
# small enough that a test builds one in milliseconds on CPU. Keep the values in
# sync with what the trainers accept, NOT with any production checkpoint.
SMALL_MODEL = dict(
    channels=16,
    residual_blocks=1,
    plane_feature_dim=32,
    scalar_hidden_dim=16,
    trunk_hidden_dim=32,
    value_hidden_dim=16,
    q_hidden_dim=16,
)

# An even smaller variant used where only shapes matter.
TINY_MODEL = dict(channels=8, residual_blocks=1, plane_feature_dim=16)

# The default 39-channel environment the policy path is defined against.
DEFAULT_ENV = EnvConfig()


def small_model_config(**overrides) -> ModelConfig:
    """A ModelConfig on the tiny architecture, with per-test overrides.

    ``small_model_config(event_window=8)`` is the B2b event-model shape.
    """
    return ModelConfig(**dict(SMALL_MODEL, **overrides))


def tiny_model_config(**overrides) -> ModelConfig:
    return ModelConfig(**dict(TINY_MODEL, **overrides))


def make_observation(
    seed: int = 0,
    env_config: EnvConfig | None = None,
    *,
    legal_actions: int = 4,
) -> dict:
    """A synthetic observation shaped from ``env_config`` rather than hardcoded.

    Deriving the shapes from EnvConfig is the point: a future change to the
    plane or scalar counts updates every test at once instead of leaving a
    scatter of stale literals behind.
    """
    cfg = env_config or DEFAULT_ENV
    rng = np.random.default_rng(seed)
    mask = np.zeros(cfg.action_space_size, dtype=np.int8)
    mask[:legal_actions] = 1
    return {
        "planes": rng.random(cfg.plane_shape, dtype=np.float32),
        "scalars": rng.random(cfg.scalar_features, dtype=np.float32),
        "action_mask": mask,
    }


def save_checkpoint(
    tmp_path: Path,
    model_config: ModelConfig,
    *,
    step: int = 1,
    name: str = "model.pt",
    env_config: EnvConfig | None = None,
) -> Path:
    """Write a checkpoint for a freshly-initialised net of the given shape."""
    from fh_mahjong_ai.model import PolicyValueNet
    from fh_mahjong_ai.storage import save_checkpoint as _save

    cfg = env_config or DEFAULT_ENV
    model = PolicyValueNet(cfg, model_config)
    path = tmp_path / name
    _save(path, model, cfg, model_config, step=step)
    return path
