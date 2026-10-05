"""fh-mj-search-diagnostic: does belief-weighted search beat the suit-averaged policy's choice?

worklog/specs/20261005-search-teacher-diagnostic.md. Writes records.jsonl (one contested state per line) and
summary.json (12 rules, primary go/no-go)."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from fh_mahjong_ai.bridge import CtypesGoBridge
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.search_diagnostic import DiagnosticConfig, Forward, run_diagnostic, summarize
from fh_mahjong_ai.serving import CheckpointPolicy


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--bridge-lib", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--states", type=int, default=4000)
    p.add_argument("--seed-base", type=int, default=910000)
    p.add_argument("--candidates", type=int, default=3)
    p.add_argument("--worlds", type=int, default=32)
    p.add_argument("--pool-worlds", type=int, default=256)
    p.add_argument("--contested-min", type=float, default=0.10)
    p.add_argument("--keep-every", type=int, default=5)
    p.add_argument("--chongci-max-hands", type=int, default=50)
    p.add_argument("--device", default="cuda")
    args = p.parse_args()
    model = CheckpointPolicy.from_checkpoint(args.checkpoint, device=args.device).model
    if not (model.model_config.privileged_critic and model.model_config.aux_heads):
        p.error("the diagnostic needs a checkpoint with a privileged critic and aux (belief) heads")
    cfg = replace(DiagnosticConfig(), candidates=args.candidates, worlds=args.worlds,
                  pool_worlds=args.pool_worlds, contested_min=args.contested_min, keep_every=args.keep_every)
    env = EnvConfig(bridge_kind="go", bridge_library_path=args.bridge_lib, learning_seats=(0, 1, 2, 3),
                    auto_play_heuristics=False, match_mode="chongci", chongci_max_hands=args.chongci_max_hands,
                    max_steps_per_episode=4000, event_history_window=int(model.model_config.event_window))
    args.out.mkdir(parents=True, exist_ok=True)
    records = []
    with (args.out / "records.jsonl").open("w") as fh, CtypesGoBridge(env) as bridge:
        def sink(record: dict) -> None:
            records.append(record)
            fh.write(json.dumps(record) + "\n")
            fh.flush()
            if len(records) % 100 == 0:
                print(f"[search-diagnostic] {len(records)}/{args.states} states", flush=True)
        run_diagnostic(bridge, Forward(model, args.device), cfg, args.states, args.seed_base, sink)
    summary = summarize(records)
    summary["config"] = {**vars(args), "checkpoint": str(args.checkpoint), "bridge_lib": str(args.bridge_lib),
                         "out": str(args.out)}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ("states", "games", "primary", "go", "other_qualifying")}))
    for name, rule in summary["rules"].items():
        print(f"{name:18s} mean {rule['mean_delta']:+.4f} ± {rule['ci_half_width']:.4f}  "
              f"override {rule['override_rate']:.3f}  hindsight-best {rule['hindsight_best_rate']:.3f}")


if __name__ == "__main__":
    main()
