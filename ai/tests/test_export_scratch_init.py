"""mortal-scale-scratch Amendment 2 §5: the digest-pinned bench checkpoint.

`fh-mj-export-scratch-init` writes exactly what `fh-mj-train-b2b --scratch
--init-from-bc` would construct at step zero -- BC weights under
`SCRATCH_BC_PREFIXES`, `trunk.0`'s event columns zeroed, and the step-zero
transfer gate's record in the metadata -- so `fh-mj-collect-bench --champion`
benches the big arm's actual initialization instead of a net whose untrained
event columns still carry BC's random values.
"""
from __future__ import annotations

import json
import sys

import pytest
import torch

from conftest import SMALL_MODEL
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet, infer_model_config
from fh_mahjong_ai.scripts import export_scratch_init as export_scratch_init_mod
from fh_mahjong_ai.scripts.export_scratch_init import export_scratch_init
from fh_mahjong_ai.storage import model_config_metadata, save_checkpoint


def _bc_checkpoint(path, cfg, env_config):
    save_checkpoint(path, PolicyValueNet(env_config, cfg),
                    metadata={"model_config": model_config_metadata(cfg)})
    return path


def test_export_scratch_init_writes_gated_checkpoint(tmp_path):
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    env39 = EnvConfig(bridge_kind="mock")
    bc = tmp_path / "best.pt"
    save_checkpoint(bc, PolicyValueNet(env39, cfg), metadata={"model_config": model_config_metadata(cfg)})
    out = tmp_path / "init.pt"
    record = export_scratch_init(bc, out, cfg, device="cpu")
    payload = torch.load(out, map_location="cpu")
    assert payload["metadata"]["init"]["kind"] == "scratch"
    assert payload["metadata"]["init"]["transfer_gate"]["greedy_match_rate"] == 1.0
    assert payload["metadata"]["init"]["bc_checkpoint_sha256"] == record["bc_checkpoint_sha256"]
    assert payload["metadata"]["purpose"] == "bench-init"
    assert infer_model_config(payload["model"], payload["metadata"]) == cfg
    ev_dim = PolicyValueNet(env39, cfg).event_encoder.output_dim
    assert torch.count_nonzero(payload["model"]["trunk.0.weight"][:, -ev_dim:]) == 0


def test_export_scratch_init_rejects_a_bc_checkpoint_of_another_architecture(tmp_path):
    """A BC checkpoint whose trunk does not match the requested config is a hard
    error from the load, and nothing is written: a bench checkpoint that is not
    the BC policy would silently bench a different net."""
    env39 = EnvConfig(bridge_kind="mock")
    bc_cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    _bc_checkpoint(tmp_path / "best.pt", bc_cfg, env39)
    wider = ModelConfig(**dict(SMALL_MODEL, residual_blocks=2), kernel_width=1, event_window=8,
                        privileged_critic=True, aux_heads=True)
    out = tmp_path / "init.pt"
    with pytest.raises(RuntimeError, match="init-from-bc"):
        export_scratch_init(tmp_path / "best.pt", out, wider, device="cpu")
    assert not out.exists()


def test_collect_bench_champion_path_preserves_the_exported_init(tmp_path):
    """`fh-mj-collect-bench --champion <exported>` must bench the exported net
    itself. `build_b2b_model` loads every tensor same-shape and then re-copies
    the two surgical tensors at full width, so the bench model is byte-identical
    to the export -- while the same path over the RAW BC checkpoint (Amendment 2
    §5's rejected bench) keeps BC's untrained, nonzero event columns."""
    from fh_mahjong_ai.train_b2b import _b2b_model_env_config, build_b2b_model

    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    env39 = _b2b_model_env_config(EnvConfig(oracle_observation=True, event_history_window=8))
    bc = _bc_checkpoint(tmp_path / "best.pt", cfg, env39)
    out = tmp_path / "init.pt"
    export_scratch_init(bc, out, cfg, device="cpu")

    exported = torch.load(out, map_location="cpu")["model"]
    benched = build_b2b_model(env39, cfg, out).state_dict()
    assert [key for key in exported if not torch.equal(exported[key].cpu(), benched[key].cpu())] == []

    ev_dim = PolicyValueNet(env39, cfg).event_encoder.output_dim
    raw = build_b2b_model(env39, cfg, bc).state_dict()
    assert torch.count_nonzero(raw["trunk.0.weight"][:, -ev_dim:]) > 0


def test_cli_writes_the_checkpoint_and_prints_the_transfer_record(tmp_path, monkeypatch, capsys):
    env39 = EnvConfig(bridge_kind="mock")
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, event_window=8, privileged_critic=True, aux_heads=True)
    bc = _bc_checkpoint(tmp_path / "best.pt", cfg, env39)
    out = tmp_path / "big-init.pt"
    monkeypatch.setattr(sys, "argv", [
        "fh-mj-export-scratch-init",
        "--bc", str(bc),
        "--out", str(out),
        "--event-window", "8",
        "--model-channels", "16",
        "--model-residual-blocks", "1",
        "--model-kernel-width", "1",
        "--model-plane-feature-dim", "32",
        "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "32",
        "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16",
        "--device", "cpu",
    ])
    export_scratch_init_mod.main()
    printed = json.loads(capsys.readouterr().out)
    payload = torch.load(out, map_location="cpu")
    assert printed["greedy_match_rate"] == 1.0
    assert payload["metadata"]["init"]["transfer_gate"] == printed
    assert payload["metadata"]["init"]["bc_checkpoint_path"] == str(bc)
    # The CLI's --event-window is the model's event window (train_b2b's own
    # flag name), and --privileged-critic/--aux-heads default on, so the
    # exported architecture is the one the lap will build.
    assert infer_model_config(payload["model"], payload["metadata"]) == cfg
