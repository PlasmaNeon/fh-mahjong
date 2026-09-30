"""CLI for the mortal-scale-scratch bench checkpoint (Amendment 2 §5).

`fh-mj-collect-bench` has no `--scratch`/`--init-from-bc`: its `--champion`
path warm-starts through `build_b2b_model`, which loads a BC checkpoint of
this architecture verbatim and therefore keeps `trunk.0`'s event columns at
BC's untrained random values. Those columns multiply a brand-new event GRU's
nonzero output, so a raw `--champion bc-big/best.pt` bench plays a different
policy from the lap it is meant to size: different actions, different
trajectory lengths, different row counts, and therefore a different memory
envelope. Amendment 2 §5 rejects that bench.

This command writes the net the lap itself would construct at step zero --
`build_scratch_model(..., bc_checkpoint=...)` for the BC-loaded prefixes with
the event columns zeroed -- gated by the same `verify_bc_transfer` step-zero
equality proof the lap runs, and carries the gate record plus the BC digest in
the checkpoint's own metadata. Benching `--champion` against THAT file
measures the big arm's real initialization.

It is a bench artifact only: `--init-from-bc` inside `fh-mj-train-b2b` remains
the lap's construction path, and nothing here writes a training checkpoint.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model_config_args import add_model_config_args, model_config_from_args
from fh_mahjong_ai.storage import model_config_metadata, save_checkpoint
from fh_mahjong_ai.train_b2b import _b2b_model_env_config, build_scratch_model, verify_bc_transfer


def export_scratch_init(bc: Path, out: Path, model_config: ModelConfig, device: str = "cpu") -> dict:
    """Build the step-zero scratch net from `bc`, gate it, and write it to `out`.

    Returns the `verify_bc_transfer` record, which is also stored under
    `metadata["init"]["transfer_gate"]`. The gate raises on any deviation, so a
    file at `out` is by construction one whose legal-action logits,
    probabilities and greedy actions equal the BC checkpoint's and whose loaded
    tensors are byte-identical to it.

    The model env config is derived exactly as `train_b2b` derives it -- 39
    policy channels via `_b2b_model_env_config`, whose 51ch source config the
    privileged critic's `planes[:, 39:51]` slice depends on -- so the exported
    architecture is the lap's, not a separately-guessed one.
    """
    bc, out = Path(bc), Path(out)
    env39 = _b2b_model_env_config(
        EnvConfig(oracle_observation=True, event_history_window=model_config.event_window)
    )
    model = build_scratch_model(env39, model_config, device, bc_checkpoint=bc)
    record = verify_bc_transfer(model, bc, env39)
    save_checkpoint(
        out,
        model,
        metadata={
            "model_config": model_config_metadata(model_config),
            # Same shape as the `init` block every `iter_*.pt` of a
            # `--scratch --init-from-bc` lap carries, so the bench artifact is
            # auditable by the same reader.
            "init": {
                "kind": "scratch",
                # From `build_scratch_model`, which hashed the exact bytes it
                # loaded the weights from -- not a second read of the path.
                "bc_checkpoint_sha256": model.init_from_bc_sha256,
                "bc_checkpoint_path": str(bc),
                "transfer_gate": record,
            },
            # This file is a bench input, never a lap checkpoint: it has no
            # optimizer state, no run_id and no history behind it.
            "purpose": "bench-init",
        },
    )
    return record


def main() -> None:
    p = argparse.ArgumentParser(
        description="Export the step-zero --scratch --init-from-bc net as a bench checkpoint"
    )
    p.add_argument("--bc", type=Path, required=True,
                   help="BC-stage checkpoint (fh-mj-train-bc best.pt) to transfer from")
    p.add_argument("--out", type=Path, required=True,
                   help="destination checkpoint; pass this to fh-mj-collect-bench --champion")
    p.add_argument("--event-window", type=int, default=128,
                   help="model event window; this is fh-mj-train-b2b's own --event-window, "
                        "NOT --model-event-window (which this command ignores, exactly as "
                        "fh-mj-train-b2b does)")
    p.add_argument("--privileged-critic", dest="privileged_critic", action="store_true", default=True,
                   help="privileged-info critic branch (default: on)")
    p.add_argument("--no-privileged-critic", dest="privileged_critic", action="store_false")
    p.add_argument("--aux-heads", dest="aux_heads", action="store_true", default=True,
                   help="belief/deal-in/rank auxiliary heads (default: on)")
    p.add_argument("--no-aux-heads", dest="aux_heads", action="store_false")
    p.add_argument("--device", type=str, default="cpu")
    add_model_config_args(p)
    args = p.parse_args()
    # Same one-construction pattern as scripts/train_b2b.py: the effective
    # window is threaded into `model_config_from_args` so no intermediate
    # ModelConfig with event_window=0 is ever built, and only the two plain
    # bools are `replace`d afterward.
    model_config = replace(model_config_from_args(args, event_window=args.event_window),
                           privileged_critic=args.privileged_critic, aux_heads=args.aux_heads)
    record = export_scratch_init(args.bc, args.out, model_config, device=args.device)
    # stdout is the record and nothing else, so a runbook step can pipe it
    # straight into the status file.
    print(json.dumps(record, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
