import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from fh_mahjong_ai.hand_stats import hand_record
from fh_mahjong_ai.scripts import benchmark as benchmark_cli
from fh_mahjong_ai.scripts.evaluate import CHONGCI_DEFAULT_MAX_STEPS


def _win(seat=0, amount=20):
    return hand_record(
        {"is_draw": False, "winner_seat": seat, "win_type_name": "ACTION_TSUMO",
         "discarder_seat": -1, "payouts": [{"seat": seat, "amount": amount}]},
        learning_seat=seat,
    )


def _deal_in(seat=0, amount=-10):
    return hand_record(
        {"is_draw": False, "winner_seat": (seat + 1) % 4, "win_type_name": "ACTION_RON",
         "discarder_seat": seat, "payouts": [{"seat": seat, "amount": amount}]},
        learning_seat=seat,
    )


def _seat_report(seat, matches, placements=None):
    from fh_mahjong_ai.hand_stats import summarize_hand_stats
    return {
        "seat": seat,
        "episodes": len(matches),
        "hand_stats": summarize_hand_stats(matches),
        "per_match_hand_records": matches,
        "mean_placement": 2.5,
        "truncation_rate": 0.0,
        "round_outcome_counts": {},
        "per_episode_placements": (
            placements if placements is not None else [1.0] * len(matches)
        ),
    }


class MergeSeatReportsTest(unittest.TestCase):
    def test_overall_pools_all_seats_matches(self) -> None:
        reports = {
            0: _seat_report(0, [[_win(0)], [_deal_in(0)]]),
            1: _seat_report(1, [[_win(1)], [_win(1)]]),
            2: _seat_report(2, [[_deal_in(2)], [_deal_in(2)]]),
            3: _seat_report(3, [[_win(3)], [_deal_in(3)]]),
        }
        merged = benchmark_cli.merge_seat_reports(reports, bootstrap_iters=50, bootstrap_seed=3)
        self.assertEqual(merged["overall"]["hand_stats"]["matches"], 8)
        self.assertEqual(merged["overall"]["hand_stats"]["hands_played"], 8)
        self.assertAlmostEqual(merged["overall"]["hand_stats"]["win_rate"], 4 / 8)
        self.assertAlmostEqual(merged["overall"]["hand_stats"]["deal_in_rate"], 4 / 8)
        self.assertIn("ci95", merged["overall"])
        self.assertIsNotNone(merged["overall"]["ci95"]["win_rate"])
        self.assertEqual(set(merged["per_seat"].keys()), {0, 1, 2, 3})
        self.assertAlmostEqual(merged["per_seat"][1]["hand_stats"]["win_rate"], 1.0)

    def test_placement_rates_map_values_to_ranks_with_tie_bucket(self) -> None:
        # Canonical GRP placement values: 1st=1, 2nd=1/3, 3rd=-1/3, 4th=-1.
        # A tie produces an averaged value (e.g. 1st/2nd tie -> 2/3) that maps
        # to no rank and must land in the "tied" bucket, not be mislabeled.
        reports = {
            0: _seat_report(0, [[_win(0)], [_win(0)]], placements=[1.0, 1.0 / 3.0]),
            1: _seat_report(1, [[_win(1)], [_win(1)]], placements=[-1.0 / 3.0, -1.0]),
            2: _seat_report(2, [[_win(2)], [_win(2)]], placements=[1.0, 2.0 / 3.0]),
            3: _seat_report(3, [[_win(3)], [_win(3)]], placements=[1.0, 1.0]),
        }
        merged = benchmark_cli.merge_seat_reports(reports, bootstrap_iters=50, bootstrap_seed=3)
        overall = merged["overall"]["placement_rates"]
        self.assertAlmostEqual(overall["1st"], 4 / 8)
        self.assertAlmostEqual(overall["2nd"], 1 / 8)
        self.assertAlmostEqual(overall["3rd"], 1 / 8)
        self.assertAlmostEqual(overall["4th"], 1 / 8)
        self.assertAlmostEqual(overall["tied"], 1 / 8)
        self.assertEqual(merged["per_seat"][3]["placement_rates"]["1st"], 1.0)
        self.assertEqual(merged["per_seat"][1]["placement_rates"]["1st"], 0.0)

    def test_table_renders_core_four_and_seats(self) -> None:
        reports = {s: _seat_report(s, [[_win(s)], [_deal_in(s)]]) for s in range(4)}
        merged = benchmark_cli.merge_seat_reports(reports, bootstrap_iters=50, bootstrap_seed=3)
        table = benchmark_cli.format_stat_table(merged)
        self.assertIn("win rate", table)
        self.assertIn("deal-in rate", table)
        self.assertIn("overall", table)
        self.assertIn("seat 0", table)
        self.assertIn("seat 3", table)
        self.assertIn("placement:", table)
        self.assertIn("1st", table)
        self.assertIn("4th", table)


class MainTest(unittest.TestCase):
    def test_main_runs_four_seats_and_writes_json(self) -> None:
        matches_by_seat = {s: [[_win(s)], [_deal_in(s)]] for s in range(4)}
        calls = []

        def fake_eval(**kwargs):
            calls.append(kwargs)
            return _seat_report(kwargs["learning_seat"], matches_by_seat[kwargs["learning_seat"]])

        fake_model = mock.Mock()
        fake_model.model_config.event_window = 32
        fake_model.wants_events = True
        fake_policy = mock.Mock(model=fake_model)

        with TemporaryDirectory() as tmp:
            ckpt = Path(tmp) / "champion.pt"
            ckpt.write_bytes(b"fake")
            with mock.patch.object(
                benchmark_cli.CheckpointPolicy, "from_checkpoint", return_value=fake_policy,
            ) as load, mock.patch.object(
                benchmark_cli, "evaluate_policy_online", side_effect=fake_eval,
            ), mock.patch.object(
                benchmark_cli, "TorchGreedyPolicy", return_value=mock.Mock(),
            ):
                benchmark_cli.main([
                    "--checkpoint", str(ckpt),
                    "--episodes-per-seat", "2",
                    "--seed-base", "100",
                    "--bootstrap-iters", "50",
                ])

            load.assert_called_once()
            self.assertEqual([c["learning_seat"] for c in calls], [0, 1, 2, 3])
            # Disjoint seed ranges: 2 episodes/seat from base 100.
            self.assertEqual(calls[0]["seeds"], [100, 101])
            self.assertEqual(calls[1]["seeds"], [102, 103])
            self.assertEqual(calls[3]["seeds"], [106, 107])
            # Event window flows from checkpoint metadata, chongci is default.
            self.assertTrue(all(c["event_history_window"] == 32 for c in calls))
            self.assertTrue(all(c["match_mode"] == "chongci" for c in calls))
            # Chongci needs a step budget that reaches MATCH_END: without the
            # resolver, EnvConfig's 256-step default truncates every match
            # mid-run (observed live: truncation_rate 1.0 across 400 matches).
            self.assertTrue(all(
                c["max_steps_per_episode"] == CHONGCI_DEFAULT_MAX_STEPS for c in calls
            ))

            out = Path(str(ckpt) + ".benchmark.json")
            self.assertTrue(out.exists())
            payload = json.loads(out.read_text())
            self.assertEqual(payload["checkpoint"], str(ckpt))
            self.assertEqual(payload["episodes_per_seat"], 2)
            self.assertIn("overall", payload)
            self.assertIn("per_seat", payload)
            self.assertIn("ci95", payload["overall"])


if __name__ == "__main__":
    unittest.main()
