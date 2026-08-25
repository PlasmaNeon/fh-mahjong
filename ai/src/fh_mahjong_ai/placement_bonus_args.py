"""Shared CLI surface for the placement-reshape terminal bonus (train_b2b,
collect_bench, placement_calibrate) so every tool builds the identical
PPOConfig fields."""
from __future__ import annotations
import argparse


def add_placement_bonus_args(parser: argparse.ArgumentParser) -> None:
    g = parser.add_argument_group("placement bonus (spec 2026-08-21)")
    g.add_argument("--placement-bonus-values", type=float, nargs=4, default=None,
                   metavar="V", help="utility for ranks 1..4; omit to disable the bonus")
    g.add_argument("--placement-bonus-lambda", type=float, default=0.0,
                   help="frozen lambda from fh-mj-placement-calibrate (requires --placement-bonus-values)")
    g.add_argument("--placement-bonus-calibration-digest", type=str, default="",
                   help="digest of the Stage-0 calibration collection that produced lambda")


def placement_bonus_kwargs(args: argparse.Namespace) -> dict:
    values = args.placement_bonus_values
    lam = float(args.placement_bonus_lambda)
    if values is None and (lam != 0.0 or args.placement_bonus_calibration_digest):
        raise SystemExit("--placement-bonus-lambda/--placement-bonus-calibration-digest require --placement-bonus-values")
    values_tuple = tuple(float(v) for v in values) if values is not None else None
    if values_tuple is not None and abs(sum(values_tuple) / 4) > 1e-6:
        raise SystemExit(
            "--placement-bonus-values must be mean-centered (mean ~= 0): the training "
            "bonus applies these values with mean-centered, semantics-free scaling, and a "
            "non-centered vector would create a provenance mismatch between the config echo "
            "and the effective reward")
    return {
        "placement_bonus_values": values_tuple,
        "placement_bonus_lambda": lam,
        "placement_bonus_calibration_digest": str(args.placement_bonus_calibration_digest),
    }
