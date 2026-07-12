"""Evaluate a trained checkpoint against baselines."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.evaluate import (
    compute_action_agreement_from_batches,
    evaluate_duplicate_seats,
    evaluate_duplicate_seats_policy,
    evaluate_online,
)
from fh_mahjong_ai.mlflow_tracking import DEFAULT_EXPERIMENT_NAME, log_artifact, log_metrics, log_params, start_run
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args, model_config_params
from fh_mahjong_ai.storage import iter_observation_action_batches, load_checkpoint


# A full chongci match (up to 50 hands) needs far more decisions than the
# classic EnvConfig default of 256, so an unset cap silently truncates every
# match. Default chongci to the PPO training budget (train_ppo.py) instead.
CHONGCI_DEFAULT_MAX_STEPS = 4000


def write_evaluation_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_max_steps_per_episode(match_mode: str, max_steps_per_episode: int | None) -> int | None:
    """Pick the bridge decision cap when ``--max-steps-per-episode`` is unset.

    An explicit value always wins. When unset, classic mode keeps falling
    through to ``EnvConfig``'s 256-step default, while chongci gets a budget
    large enough to reach ``PHASE_MATCH_END`` so matches terminate (with real
    standings) instead of being truncated at the step limit.
    """
    if max_steps_per_episode is not None:
        return max_steps_per_episode
    if match_mode == "chongci":
        return CHONGCI_DEFAULT_MAX_STEPS
    return None


def parse_seed_windows(values: list[str], episodes: int, start_seed: int) -> list[int]:
    if not values:
        return list(range(start_seed, start_seed + episodes))
    seeds: list[int] = []
    for value in values:
        if ":" in value:
            start_text, count_text = value.split(":", 1)
            start = int(start_text)
            count = int(count_text)
        else:
            start = int(value)
            count = episodes
        seeds.extend(range(start, start + count))
    return seeds


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a trained model")
    parser.add_argument("--checkpoint", type=Path, required=True, help="Path to .pt checkpoint")
    parser.add_argument("--data", type=Path, default=None, help="JSONL data for offline eval")
    parser.add_argument("--online-episodes", type=int, default=0, help="Number of online episodes (0 = skip)")
    parser.add_argument("--start-seed", type=int, default=1000, help="Starting seed for online eval")
    parser.add_argument(
        "--seed-window",
        action="append",
        default=[],
        help="Start seed or start:count. Repeat for non-contiguous online eval windows.",
    )
    parser.add_argument("--duplicate-seats", action="store_true", help="Rotate the agent through all four seats")
    parser.add_argument("--bridge-lib", type=Path, default=None, help="Path to c-shared library")
    parser.add_argument("--match-mode", choices=("classic", "chongci"), default="classic", help="Simulator match mode")
    parser.add_argument("--chongci-starting-score", type=int, default=2000, help="Chongci starting score")
    parser.add_argument("--chongci-bust-threshold", type=int, default=0, help="Chongci bust threshold")
    parser.add_argument("--chongci-max-hands", type=int, default=50, help="Chongci hand cap")
    parser.add_argument(
        "--max-steps-per-episode",
        type=int,
        default=None,
        help="Bridge decision cap per online episode; default 256 (classic) or 4000 (chongci)",
    )
    parser.add_argument(
        "--large-loss-threshold",
        type=float,
        default=None,
        help="Reward threshold for large-loss reporting; defaults by match mode",
    )
    parser.add_argument("--device", type=str, default="cpu", help="Device")
    parser.add_argument("--offline-batch-size", type=int, default=4096, help="Batch size for offline action-agreement inference")
    parser.add_argument("--report-output", type=Path, default=None)
    parser.add_argument("--oracle", action="store_true", help="perfect-information oracle eval (51ch observation)")
    parser.add_argument("--from-oracle", action="store_true", help="checkpoint is a 51ch oracle/self-play net; extract the deployable 39ch student and eval non-oracle")
    parser.add_argument("--sample-temperature", type=float, default=0.0,
                        help="evaluate with the SERVING sampler (CheckpointPolicy) at this softmax "
                             "temperature instead of greedy argmax; 0 = greedy (unchanged). "
                             "Requires --duplicate-seats")
    parser.add_argument("--sample-top-k", type=int, default=0,
                        help="restrict sampling to the top-k legal actions (0 = no cap)")
    parser.add_argument("--sample-action-family", type=str, default="all",
                        help="only sample when every legal action is in this family "
                             "(e.g. 'discard'); mixed decisions stay greedy")
    parser.add_argument("--sample-seed", type=int, default=1,
                        help="base RNG seed for the sampler (per-seat seeds derive from it)")
    parser.add_argument("--search", action="store_true",
                        help="run test-time determinized champion-rollout search (SearchPolicy) instead "
                             "of plain greedy evaluation. Requires --duplicate-seats")
    parser.add_argument("--search-determinizations", type=int, default=16,
                        help="rollout clones per candidate root action")
    parser.add_argument("--search-max-candidates", type=int, default=4,
                        help="max root candidate actions considered by prior rank")
    parser.add_argument("--search-prior-mass", type=float, default=0.95,
                        help="cumulative prior-mass cutoff for candidate selection")
    parser.add_argument("--search-max-rollout-decisions", type=int, default=512,
                        help="rollout decision cap before bootstrapping with the value head")
    parser.add_argument("--search-seed", type=int, default=1,
                        help="base RNG seed for the search pool (per-seat seeds derive from it)")
    parser.add_argument("--mlflow", action="store_true", help="Log inference/evaluation params, metrics, and artifacts to MLflow")
    parser.add_argument("--mlflow-tracking-uri", type=str, default=None)
    parser.add_argument("--mlflow-experiment", type=str, default=DEFAULT_EXPERIMENT_NAME)
    parser.add_argument("--mlflow-run-name", type=str, default=None)
    add_model_config_args(parser)
    args = parser.parse_args()

    # Computed early (used by validation below) rather than in its original spot
    # after resolve_max_steps_per_episode: --from-oracle overrides --oracle so a
    # 39ch student never runs against a 51ch env.
    eval_oracle = args.oracle and not args.from_oracle

    if not math.isfinite(args.sample_temperature) or args.sample_temperature < 0.0:
        parser.error("--sample-temperature must be a finite value >= 0")
    if args.sample_top_k < 0:
        parser.error("--sample-top-k must be >= 0")
    if args.sample_temperature == 0.0 and (args.sample_top_k > 0 or args.sample_action_family != "all"):
        parser.error("--sample-top-k / --sample-action-family have no effect without --sample-temperature > 0")
    if args.sample_temperature > 0.0:
        if not args.duplicate_seats:
            parser.error("--sample-temperature requires --duplicate-seats (the paired gate path)")
        from fh_mahjong_ai.action_catalog import action_family as _action_family
        known_families = {"all", "", "*"} | {
            _action_family(a) for a in range(EnvConfig().action_space_size)
        }
        if args.sample_action_family not in known_families:
            parser.error(f"--sample-action-family {args.sample_action_family!r} is not a known "
                         f"action family (choose from {sorted(known_families - {'', '*'})})")

    _search_numeric_flags = (
        "search_determinizations", "search_max_candidates", "search_prior_mass",
        "search_max_rollout_decisions", "search_seed",
    )
    if not args.search:
        for _flag_name in _search_numeric_flags:
            if getattr(args, _flag_name) != parser.get_default(_flag_name):
                parser.error(f"--{_flag_name.replace('_', '-')} requires --search")
    else:
        if not args.duplicate_seats:
            parser.error("--search requires --duplicate-seats (the paired gate path)")
        if args.search_determinizations < 1:
            parser.error("--search-determinizations must be >= 1")
        if args.search_max_candidates < 1:
            parser.error("--search-max-candidates must be >= 1")
        if not (0.0 < args.search_prior_mass <= 1.0):
            parser.error("--search-prior-mass must be in (0, 1]")
        if args.search_max_rollout_decisions < 1:
            parser.error("--search-max-rollout-decisions must be >= 1")
        if args.sample_temperature > 0.0:
            parser.error("--search is incompatible with --sample-temperature > 0 "
                         "(choose one decision-time policy)")
        if eval_oracle:
            parser.error("--search cannot run against an oracle observation env "
                         "(--oracle without --from-oracle); the search pool rejects oracle envs")

    max_steps_per_episode = resolve_max_steps_per_episode(args.match_mode, args.max_steps_per_episode)

    model_config = model_config_from_args(args)
    if args.from_oracle:
        from fh_mahjong_ai.oracle import extract_deployable_student
        oracle_net = PolicyValueNet(EnvConfig(oracle_observation=True), model_config)
        step = load_checkpoint(args.checkpoint, oracle_net)
        model = extract_deployable_student(oracle_net, EnvConfig(), model_config)
    else:
        model = PolicyValueNet(EnvConfig(oracle_observation=args.oracle), model_config)
        step = load_checkpoint(args.checkpoint, model)
    model.to(args.device)
    print(f"Loaded checkpoint from epoch {step}")

    final_report: dict[str, Any] = {
        "schema_version": 1,
        "checkpoint": str(args.checkpoint),
        "checkpoint_step": step,
        "data": str(args.data) if args.data else None,
        "device": args.device,
        "match_mode": args.match_mode,
        "model_config": model_config_params(model_config),
        "chongci_config": {
            "starting_score": args.chongci_starting_score,
            "bust_threshold": args.chongci_bust_threshold,
            "max_hands": args.chongci_max_hands,
        }
        if args.match_mode == "chongci"
        else None,
        "offline": None,
        "online": None,
    }
    if args.sample_temperature > 0.0:
        # Only present when sampling is active, so the default (greedy) report
        # stays byte-identical to pre-sampling output.
        final_report["sampling"] = {
            "temperature": args.sample_temperature,
            "top_k": args.sample_top_k,
            "action_family": args.sample_action_family,
            "seed": args.sample_seed,
        }
    if args.search:
        # Only present when search is active, so the default (greedy) report
        # stays byte-identical to pre-search output. fallback_count is filled
        # in after the online eval runs (0 until then, e.g. --online-episodes 0).
        final_report["search"] = {
            "num_determinizations": args.search_determinizations,
            "max_candidates": args.search_max_candidates,
            "prior_mass_cutoff": args.search_prior_mass,
            "max_rollout_decisions": args.search_max_rollout_decisions,
            "seed": args.search_seed,
            "fallback_count": 0,
        }

    with start_run(
        enabled=args.mlflow,
        experiment_name=args.mlflow_experiment,
        tracking_uri=args.mlflow_tracking_uri,
        run_name=args.mlflow_run_name,
        tags={"stage": "inference_evaluation"},
    ) as mlflow_run:
        if mlflow_run is not None:
            log_params(
                {
                    "checkpoint": args.checkpoint,
                    "checkpoint_step": step,
                    "data": args.data,
                    "device": args.device,
                    "offline_batch_size": args.offline_batch_size,
                    "online_episodes": args.online_episodes,
                    "start_seed": args.start_seed,
                    "duplicate_seats": args.duplicate_seats,
                    "bridge_library_path": args.bridge_lib,
                    "match_mode": args.match_mode,
                    "chongci_starting_score": args.chongci_starting_score,
                    "chongci_bust_threshold": args.chongci_bust_threshold,
                    "chongci_max_hands": args.chongci_max_hands,
                    "max_steps_per_episode": max_steps_per_episode,
                    "large_loss_threshold": args.large_loss_threshold,
                    **model_config_params(model_config),
                }
            )

        if args.data is not None:
            print(f"\n--- Offline Evaluation (action agreement) ---")
            offline_report = compute_action_agreement_from_batches(
                model,
                iter_observation_action_batches(args.data, args.offline_batch_size),
                device=args.device,
            )
            final_report["offline"] = offline_report
            print(f"  Transitions:     {offline_report['total_transitions']}")
            print(f"  Agreement:       {offline_report['agreement_rate']:.2%}")
            print(f"  Top-3 Agreement: {offline_report['top3_agreement_rate']:.2%}")
            print("  Action Families:")
            for family, family_report in offline_report["family_agreement"].items():
                print(
                    f"    {family}: n={family_report['total']} "
                    f"top1={family_report['agreement_rate']:.2%} "
                    f"top3={family_report['top3_agreement_rate']:.2%}"
                )
            if mlflow_run is not None:
                log_metrics({"offline": offline_report})

        if args.online_episodes > 0:
            print(f"\n--- Online Evaluation ({args.online_episodes} episodes) ---")
            seeds = parse_seed_windows(args.seed_window, args.online_episodes, args.start_seed)
            if args.duplicate_seats and args.search:
                # Deploy-realistic eval: route decisions through determinized
                # champion-rollout search (SearchPolicy) so the sweep measures
                # what the search-augmented policy would ship.
                from fh_mahjong_ai.search import SearchConfig, SearchPolicy
                from fh_mahjong_ai.searchpool import GoSearchPool
                from fh_mahjong_ai.serving import CheckpointPolicy

                search_policies: list[SearchPolicy] = []

                def search_policy_factory(seat: int, bridge: Any) -> SearchPolicy:
                    # Fresh per-seat checkpoint policy, exactly as the sampling
                    # path builds them, but greedy (no sampling kwargs) since
                    # SearchPolicy needs a deterministic prior + value head.
                    checkpoint_policy = CheckpointPolicy(
                        model=model,
                        checkpoint_path=args.checkpoint,
                        checkpoint_step=step,
                        device=args.device,
                    )

                    def pool_factory(num_clones: int, seed: int, max_rollout_decisions: int,
                                      _bridge=bridge) -> GoSearchPool:
                        # Closes over THIS seat's live bridge -- the pool clones
                        # the current decision point of the env this policy is
                        # actually choosing for, not a shared/incidental bridge.
                        return GoSearchPool(_bridge, num_clones, seed, max_rollout_decisions)

                    search_policy = SearchPolicy(
                        checkpoint_policy=checkpoint_policy,
                        pool_factory=pool_factory,
                        config=SearchConfig(
                            num_determinizations=args.search_determinizations,
                            max_candidates=args.search_max_candidates,
                            prior_mass_cutoff=args.search_prior_mass,
                            max_rollout_decisions=args.search_max_rollout_decisions,
                            seed=args.search_seed * 4 + seat,
                        ),
                    )
                    search_policies.append(search_policy)
                    return search_policy

                online_report = evaluate_duplicate_seats_policy(
                    policy_factory=search_policy_factory,
                    seeds=seeds,
                    bridge_kind="go",
                    bridge_library_path=args.bridge_lib,
                    large_loss_threshold=args.large_loss_threshold,
                    match_mode=args.match_mode,
                    chongci_starting_score=args.chongci_starting_score,
                    chongci_bust_threshold=args.chongci_bust_threshold,
                    chongci_max_hands=args.chongci_max_hands,
                    max_steps_per_episode=max_steps_per_episode,
                    oracle_observation=eval_oracle,
                )
                final_report["search"]["fallback_count"] = sum(p.fallback_count for p in search_policies)
            elif args.duplicate_seats and args.sample_temperature > 0.0:
                # Deploy-realistic eval: route decisions through the SERVING
                # sampler so the sweep measures exactly what production ships.
                from fh_mahjong_ai.policies import SampledServingPolicy
                from fh_mahjong_ai.serving import CheckpointPolicy

                def sampled_policy_factory(seat: int) -> SampledServingPolicy:
                    # Fresh per-seat policy: seeded sampler RNG restarts per seat
                    # rotation, so reports are reproducible under --sample-seed.
                    return SampledServingPolicy(CheckpointPolicy(
                        model=model,
                        checkpoint_path=args.checkpoint,
                        checkpoint_step=step,
                        device=args.device,
                        sample_temperature=args.sample_temperature,
                        sample_top_k=args.sample_top_k,
                        sample_action_family=args.sample_action_family,
                        seed=args.sample_seed * 4 + seat,
                    ))

                online_report = evaluate_duplicate_seats_policy(
                    policy_factory=sampled_policy_factory,
                    seeds=seeds,
                    bridge_kind="go",
                    bridge_library_path=args.bridge_lib,
                    large_loss_threshold=args.large_loss_threshold,
                    match_mode=args.match_mode,
                    chongci_starting_score=args.chongci_starting_score,
                    chongci_bust_threshold=args.chongci_bust_threshold,
                    chongci_max_hands=args.chongci_max_hands,
                    max_steps_per_episode=max_steps_per_episode,
                    oracle_observation=eval_oracle,
                )
            elif args.duplicate_seats:
                online_report = evaluate_duplicate_seats(
                    model=model,
                    seeds=seeds,
                    bridge_kind="go",
                    bridge_library_path=args.bridge_lib,
                    device=args.device,
                    large_loss_threshold=args.large_loss_threshold,
                    match_mode=args.match_mode,
                    chongci_starting_score=args.chongci_starting_score,
                    chongci_bust_threshold=args.chongci_bust_threshold,
                    chongci_max_hands=args.chongci_max_hands,
                    max_steps_per_episode=max_steps_per_episode,
                    oracle_observation=eval_oracle,
                )
            else:
                online_report = evaluate_online(
                    model=model,
                    episodes=args.online_episodes,
                    seeds=seeds,
                    bridge_kind="go",
                    bridge_library_path=args.bridge_lib,
                    device=args.device,
                    large_loss_threshold=args.large_loss_threshold,
                    match_mode=args.match_mode,
                    chongci_starting_score=args.chongci_starting_score,
                    chongci_bust_threshold=args.chongci_bust_threshold,
                    chongci_max_hands=args.chongci_max_hands,
                    max_steps_per_episode=max_steps_per_episode,
                    oracle_observation=eval_oracle,
                )
            final_report["online"] = online_report
            print(f"  Match Mode:  {online_report['match_mode']}")
            print(f"  Episodes:    {online_report['episodes']}")
            print(f"  Avg Reward:  {online_report['avg_reward']}")
            print(
                f"  Reward > 0:  {online_report['positive_reward_count']} "
                f"({online_report['positive_reward_rate']:.2%})"
            )
            if args.match_mode == "classic":
                print(f"  Wins:        {online_report['win_count']}")
                print(f"  Win Rate:    {online_report['win_rate']:.2%}")
            else:
                print("  Win Rate:    reward-positive compatibility metric; use Reward > 0 for Chongci")
            print(f"  Large Loss:  {online_report['large_loss_rate']:.2%}")
            if online_report.get("round_outcome_rates"):
                print("  Round Outcomes:")
                for name, rate in online_report["round_outcome_rates"].items():
                    count = online_report.get("round_outcome_counts", {}).get(name, 0)
                    print(f"    {name}: n={count} rate={rate:.2%}")
            if mlflow_run is not None:
                log_metrics({"online": online_report})

        if args.report_output is not None:
            write_evaluation_report(args.report_output, final_report)
            print(f"Report saved to {args.report_output}")

        if mlflow_run is not None:
            log_artifact(args.checkpoint, artifact_path="checkpoints")
            log_artifact(args.report_output, artifact_path="reports")
            print(f"MLflow run: {mlflow_run.info.run_id}")

    print("\nDone.")


if __name__ == "__main__":
    main()
