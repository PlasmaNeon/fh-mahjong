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


# The 39-channel mock-bridge environment B2b anchors are built against. Using
# the mock bridge means no Go shared library is loaded, so an anchor checkpoint
# builds and loads in milliseconds. EnvConfig is a plain mutable dataclass and
# this instance is shared suite-wide, so never mutate it — build your own with
# EnvConfig(bridge_kind="mock") if a test needs to change a field.
MOCK_ENV = EnvConfig(bridge_kind="mock")


def b2b_model_config(**overrides) -> ModelConfig:
    """The B2b event-model shape: the small architecture plus an event window,
    a privileged critic, and the auxiliary heads. Overrides win."""
    fields = dict(event_window=8, privileged_critic=True, aux_heads=True)
    fields.update(overrides)
    return small_model_config(**fields)


def save_b2b_anchor(tmp_path: Path, model_config: ModelConfig, *,
                    with_model_config_metadata: bool = True,
                    model_config_metadata_override: dict | None = None) -> Path:
    """Write a B2b anchor checkpoint, optionally with a missing or doctored
    ``metadata["model_config"]`` block so loaders can be tested against it."""
    from fh_mahjong_ai.model import PolicyValueNet
    from fh_mahjong_ai.storage import model_config_metadata, save_checkpoint as _save

    model = PolicyValueNet(MOCK_ENV, model_config)
    metadata = {}
    if with_model_config_metadata:
        metadata["model_config"] = model_config_metadata_override or model_config_metadata(model_config)
    path = tmp_path / "anchor.pt"
    _save(path, model, metadata=metadata)
    return path


def save_champion39(tmp_path: Path) -> tuple[EnvConfig, Path]:
    """A freshly-initialised 39-channel champion checkpoint plus the env it was
    built against — the warm-start a B2b run branches from."""
    from fh_mahjong_ai.model import PolicyValueNet
    from fh_mahjong_ai.storage import save_checkpoint as _save

    env39 = EnvConfig(bridge_kind="mock")   # a fresh instance: callers may mutate it
    model = PolicyValueNet(env39, small_model_config())
    path = tmp_path / "champion.pt"
    _save(path, model)
    return env39, path


def b2b_run_configs(tmp_path: Path, *, iterations: int, lr: float = 2e-5):
    """The (env, model_config, champion_path, ppo_config) tuple a short B2b
    training run needs: mock bridge, 16-step episodes, two matches an
    iteration. Small enough to run in a test, real enough to exercise the loop.
    """
    from fh_mahjong_ai.ppo import PPOConfig

    _, champion_path = save_champion39(tmp_path)
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    model_config = b2b_model_config()
    config = PPOConfig(device="cpu", iterations=iterations, matches_per_iter=2, lr=lr,
                       max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                       num_workers=1, match_mode="classic")
    return env, model_config, champion_path, config
