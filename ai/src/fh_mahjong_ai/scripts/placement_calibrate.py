"""fh-mj-placement-calibrate: Stage-0 lambda calibration + return-scale gates
for the placement-reshape experiment (spec 2026-08-21, Amendment 1 item 2).

Collects the registered calibration matches from the champion with the bonus
OFF, computes lambda = k*sigma_R/sigma_V from the match telemetry, then on the
IDENTICAL batch compares raw vs bonus-shaped GAE returns against the anchor's
own value predictions. Never adjusts lambda; prints/records pass/fail only.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
from ..config import EnvConfig
from ..model_config_args import add_model_config_args, model_config_from_args
from ..ppo import PPOConfig, compute_gae
from ..placement_bonus import (PLACEMENT_RESHAPE_VALUES, apply_terminal_bonus, calibrate_lambda,
                               return_scale_gates, CALIBRATION_MATCHES)
from ..train_b2b import ParallelB2bCollector, _b2b_model_env_config
from .collect_bench import _build_model, _digest_batch


def run_calibration(env_config: EnvConfig, model_config, champion: Path, *, output: Path,
                    matches: int, require_matches: int, base_seed: int, num_workers: int,
                    collect_dispatch_chunk: int, k: float, gamma: float, gae_lambda: float,
                    device: str) -> dict:
    model, model_config = _build_model(env_config, model_config, champion, 0, device)
    cfg = PPOConfig(device=device, matches_per_iter=matches, match_mode=env_config.match_mode,
                    max_steps_per_episode=env_config.max_steps_per_episode, num_workers=num_workers,
                    collect_dispatch_chunk=collect_dispatch_chunk, gamma=gamma,
                    gae_lambda=gae_lambda)   # bonus OFF: values=None
    collector = ParallelB2bCollector(env_config, model_config, cfg, num_workers)
    try:
        state = {k_: v.detach().cpu() for k_, v in model.state_dict().items()}
        batch = collector.collect(state, base_seed, matches)
    finally:
        collector.close()
    if int(batch.truncated_matches) != 0:
        raise SystemExit(f"calibration collection truncated {batch.truncated_matches} match(es) — fail closed")
    digest = _digest_batch(base_seed, matches, batch)
    calib = calibrate_lambda(batch.match_telemetry, PLACEMENT_RESHAPE_VALUES, k=k,
                             require_matches=require_matches)
    shaped_rewards = apply_terminal_bonus(batch.rewards, batch.dones, batch.match_telemetry,
                                          PLACEMENT_RESHAPE_VALUES, calib["lambda"])
    _, raw_ret = compute_gae(batch.rewards, batch.values, batch.dones, gamma, gae_lambda)
    _, shp_ret = compute_gae(shaped_rewards, batch.values, batch.dones, gamma, gae_lambda)
    gates = return_scale_gates(raw_ret, shp_ret, batch.values)
    bonus = np.asarray([t["utilities"] for t in batch.match_telemetry]) * calib["lambda"]
    report = {
        "values": list(PLACEMENT_RESHAPE_VALUES), "calibration": calib, "gates": gates,
        "collection_digest": digest, "base_seed": base_seed, "matches": matches,
        "gamma": gamma, "gae_lambda": gae_lambda, "champion": str(champion),
        "bonus_mean": float(bonus.mean()), "bonus_rms": float(np.sqrt(np.mean(bonus**2))),
        "bonus_abs_p99": float(np.percentile(np.abs(bonus), 99)),
        "fourth_place_bonus_over_sigma_R": float(calib["lambda"] * PLACEMENT_RESHAPE_VALUES[3] / calib["sigma_R"]),
    }
    output.write_text(json.dumps(report, indent=2, sort_keys=True))
    return report


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--champion", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--matches", type=int, default=CALIBRATION_MATCHES)
    p.add_argument("--require-matches", type=int, default=CALIBRATION_MATCHES)
    p.add_argument("--base-seed", type=int, default=720000)
    p.add_argument("--num-workers", type=int, default=1)
    p.add_argument("--collect-dispatch-chunk", type=int, default=0)
    p.add_argument("--k", type=float, default=0.5)
    p.add_argument("--gamma", type=float, default=0.99)
    p.add_argument("--gae-lambda", type=float, default=0.95)
    p.add_argument("--match-mode", choices=("classic", "chongci"), default="chongci")
    p.add_argument("--bridge-kind", choices=("go", "mock"), default="go")
    p.add_argument("--bridge-lib", type=str, default=None)
    p.add_argument("--device", type=str, default="cpu")
    p.add_argument("--event-window", type=int, default=128)
    p.add_argument("--max-steps-per-episode", type=int, default=4000)
    add_model_config_args(p)
    args = p.parse_args(argv)
    env_config = EnvConfig(bridge_kind=args.bridge_kind, bridge_library_path=args.bridge_lib,
                           match_mode=args.match_mode, max_steps_per_episode=args.max_steps_per_episode,
                           event_history_window=args.event_window, oracle_observation=True)
    model_config = model_config_from_args(args, event_window=args.event_window)
    report = run_calibration(env_config, model_config, args.champion, output=args.output,
                             matches=args.matches, require_matches=args.require_matches,
                             base_seed=args.base_seed, num_workers=args.num_workers,
                             collect_dispatch_chunk=args.collect_dispatch_chunk, k=args.k,
                             gamma=args.gamma, gae_lambda=args.gae_lambda, device=args.device)
    gates = report["gates"]
    print(json.dumps({k: report[k] for k in ("calibration", "gates")}, indent=2))
    if not gates["all_pass"]:
        raise SystemExit("return-scale gates FAILED — return to consultation; do not lower lambda")


if __name__ == "__main__":
    main()
