from __future__ import annotations

from pathlib import Path

import pytest

from fh_mahjong_ai.selfplay_loop import (
    GateOutcome,
    GateThresholds,
    confirm_promote,
    gate_decision,
    screen_pass,
)


def _report(mean, ci95, large_loss, positive):
    return {
        "mean_reward": mean,
        "mean_reward_ci95": ci95,
        "large_loss_rate": large_loss,
        "positive_reward_rate": positive,
    }


def test_screen_pass_allows_candidate_within_margin():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand = _report(-0.03, 0.05, 0.2, 0.45)
    assert screen_pass(cand, best, GateThresholds()) is True


def test_screen_pass_rejects_candidate_below_margin():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand = _report(-0.2, 0.05, 0.2, 0.45)
    assert screen_pass(cand, best, GateThresholds()) is False


def test_confirm_promote_requires_ci_separation():
    best = _report(0.0, 0.05, 0.2, 0.45)
    # candidate mean higher but CI overlaps best mean -> not promoted
    overlap = _report(0.04, 0.06, 0.2, 0.45)
    assert confirm_promote(overlap, best, GateThresholds()) is False
    # candidate CI-separated above best -> promoted
    separated = _report(0.2, 0.05, 0.2, 0.45)
    assert confirm_promote(separated, best, GateThresholds()) is True


def test_confirm_promote_rejects_large_loss_regression():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand = _report(0.3, 0.05, 0.25, 0.45)  # CI-separated but worse tail risk
    assert confirm_promote(cand, best, GateThresholds()) is False


def test_confirm_promote_rejects_positive_rate_drop():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand = _report(0.3, 0.05, 0.2, 0.40)  # positive drop 0.05 > positive_eps 0.02
    assert confirm_promote(cand, best, GateThresholds()) is False


def test_gate_decision_rejects_on_screen_without_confirm():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand_screen = _report(-0.5, 0.05, 0.2, 0.45)
    called = {"confirm": False}

    def confirm_evaluator():
        called["confirm"] = True
        return cand_screen, best

    outcome, cc, bc = gate_decision(cand_screen, best, GateThresholds(), confirm_evaluator)
    assert outcome is GateOutcome.REJECTED_SCREEN
    assert called["confirm"] is False
    assert cc is None and bc is None


def test_gate_decision_promotes_on_confirm():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand_screen = _report(0.1, 0.05, 0.2, 0.45)
    cand_confirm = _report(0.2, 0.05, 0.2, 0.45)
    best_confirm = _report(0.0, 0.05, 0.2, 0.45)

    outcome, cc, bc = gate_decision(
        cand_screen, best, GateThresholds(), lambda: (cand_confirm, best_confirm)
    )
    assert outcome is GateOutcome.PROMOTED
    assert cc == cand_confirm and bc == best_confirm


def test_gate_decision_rejects_on_confirm():
    best = _report(0.0, 0.05, 0.2, 0.45)
    cand_screen = _report(0.1, 0.05, 0.2, 0.45)
    cand_confirm = _report(0.02, 0.06, 0.2, 0.45)  # CI overlaps
    best_confirm = _report(0.0, 0.05, 0.2, 0.45)

    outcome, _, _ = gate_decision(
        cand_screen, best, GateThresholds(), lambda: (cand_confirm, best_confirm)
    )
    assert outcome is GateOutcome.REJECTED_CONFIRM
