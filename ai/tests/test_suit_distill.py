"""Suit distillation (PPOConfig.suit_distill_coef): spec worklog/specs/20261002-suit-distill-lap.md."""

import os

import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.ppo import PPOConfig

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
