import unittest

from fh_mahjong_ai.hand_stats import (
    bootstrap_hand_stats_ci,
    hand_record,
    summarize_hand_stats,
)


def _outcome(is_draw=False, winner=-1, discarder=-1, win_type="ACTION_TSUMO", payouts=()):
    return {
        "is_draw": is_draw,
        "winner_seat": winner,
        "win_type_name": win_type,
        "discarder_seat": discarder,
        "total_score": sum(abs(p["amount"]) for p in payouts),
        "payouts": list(payouts),
    }


class HandRecordTest(unittest.TestCase):
    def test_tsumo_win_for_learning_seat(self) -> None:
        rec = hand_record(
            _outcome(winner=0, win_type="ACTION_TSUMO",
                     payouts=[{"seat": 0, "amount": 24}, {"seat": 1, "amount": -8},
                              {"seat": 2, "amount": -8}, {"seat": 3, "amount": -8}]),
            learning_seat=0,
        )
        self.assertTrue(rec["win"])
        self.assertFalse(rec["deal_in"])
        self.assertFalse(rec["is_draw"])
        self.assertEqual(rec["payout"], 24)

    def test_deal_in_requires_ron_by_learning_seat_discard(self) -> None:
        rec = hand_record(
            _outcome(winner=2, discarder=0, win_type="ACTION_RON",
                     payouts=[{"seat": 2, "amount": 16}, {"seat": 0, "amount": -16}]),
            learning_seat=0,
        )
        self.assertTrue(rec["deal_in"])
        self.assertFalse(rec["win"])
        self.assertEqual(rec["payout"], -16)

    def test_other_seat_ron_is_not_deal_in(self) -> None:
        rec = hand_record(
            _outcome(winner=2, discarder=1, win_type="ACTION_RON",
                     payouts=[{"seat": 2, "amount": 16}, {"seat": 1, "amount": -16}]),
            learning_seat=0,
        )
        self.assertFalse(rec["deal_in"])
        self.assertFalse(rec["win"])
        self.assertEqual(rec["payout"], 0)  # seat 0 not in payouts

    def test_learning_seat_ron_win_is_win_not_deal_in(self) -> None:
        rec = hand_record(
            _outcome(winner=0, discarder=3, win_type="ACTION_RON",
                     payouts=[{"seat": 0, "amount": 16}, {"seat": 3, "amount": -16}]),
            learning_seat=0,
        )
        self.assertTrue(rec["win"])
        self.assertFalse(rec["deal_in"])

    def test_draw_hand(self) -> None:
        rec = hand_record(_outcome(is_draw=True), learning_seat=0)
        self.assertTrue(rec["is_draw"])
        self.assertFalse(rec["win"])
        self.assertFalse(rec["deal_in"])


class SummarizeHandStatsTest(unittest.TestCase):
    def _match(self):
        # One match: tsumo win (+24), deal-in (-16), draw.
        return [
            hand_record(_outcome(winner=0, win_type="ACTION_TSUMO",
                                 payouts=[{"seat": 0, "amount": 24}]), 0),
            hand_record(_outcome(winner=1, discarder=0, win_type="ACTION_RON",
                                 payouts=[{"seat": 1, "amount": 16},
                                          {"seat": 0, "amount": -16}]), 0),
            hand_record(_outcome(is_draw=True), 0),
        ]

    def test_summary_counts_and_rates(self) -> None:
        stats = summarize_hand_stats([self._match(), self._match()], unknown_hands=1)
        self.assertEqual(stats["matches"], 2)
        self.assertEqual(stats["hands_played"], 6)
        self.assertEqual(stats["unknown_hands"], 1)
        self.assertEqual(stats["wins"], 2)
        self.assertEqual(stats["deal_ins"], 2)
        self.assertEqual(stats["draws"], 2)
        self.assertAlmostEqual(stats["win_rate"], 2 / 6)
        self.assertAlmostEqual(stats["deal_in_rate"], 2 / 6)
        self.assertAlmostEqual(stats["draw_rate"], 2 / 6)
        self.assertAlmostEqual(stats["avg_win_value"], 24.0)
        self.assertAlmostEqual(stats["avg_deal_in_loss"], 16.0)
        self.assertAlmostEqual(stats["hands_per_match"], 3.0)

    def test_empty_input(self) -> None:
        stats = summarize_hand_stats([])
        self.assertEqual(stats["matches"], 0)
        self.assertEqual(stats["hands_played"], 0)
        self.assertEqual(stats["win_rate"], 0.0)
        self.assertIsNone(stats["avg_win_value"])
        self.assertIsNone(stats["avg_deal_in_loss"])

    def test_no_wins_yields_none_avg_win_value(self) -> None:
        match = [hand_record(_outcome(is_draw=True), 0)]
        stats = summarize_hand_stats([match])
        self.assertIsNone(stats["avg_win_value"])
        self.assertIsNone(stats["avg_deal_in_loss"])


class BootstrapCITest(unittest.TestCase):
    def test_ci_brackets_point_estimate_and_is_deterministic(self) -> None:
        win = hand_record(_outcome(winner=0, win_type="ACTION_TSUMO",
                                   payouts=[{"seat": 0, "amount": 20}]), 0)
        loss = hand_record(_outcome(winner=1, discarder=0, win_type="ACTION_RON",
                                    payouts=[{"seat": 0, "amount": -10}]), 0)
        matches = [[win, loss], [win, win], [loss, loss], [win, loss], [win, win]]
        cis_a = bootstrap_hand_stats_ci(matches, iters=200, seed=7)
        cis_b = bootstrap_hand_stats_ci(matches, iters=200, seed=7)
        self.assertEqual(cis_a, cis_b)  # deterministic under a fixed seed
        point = summarize_hand_stats(matches)["win_rate"]
        lo, hi = cis_a["win_rate"]
        self.assertLessEqual(lo, point)
        self.assertGreaterEqual(hi, point)
        self.assertLessEqual(0.0, lo)
        self.assertLessEqual(hi, 1.0)

    def test_degenerate_all_same_outcome(self) -> None:
        win = hand_record(_outcome(winner=0, win_type="ACTION_TSUMO",
                                   payouts=[{"seat": 0, "amount": 20}]), 0)
        cis = bootstrap_hand_stats_ci([[win], [win], [win]], iters=100, seed=1)
        self.assertEqual(cis["win_rate"], [1.0, 1.0])
        self.assertIsNone(cis["avg_deal_in_loss"])  # no deal-ins ever

    def test_fewer_than_two_matches_returns_none(self) -> None:
        win = hand_record(_outcome(winner=0, win_type="ACTION_TSUMO",
                                   payouts=[{"seat": 0, "amount": 20}]), 0)
        cis = bootstrap_hand_stats_ci([[win]], iters=100, seed=1)
        self.assertIsNone(cis["win_rate"])


if __name__ == "__main__":
    unittest.main()
