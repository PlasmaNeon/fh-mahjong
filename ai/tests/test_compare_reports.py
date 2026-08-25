import json

import numpy as np
import pytest

from fh_mahjong_ai.evaluate import _t_critical_975
from fh_mahjong_ai.scripts.compare_reports import _format_text, main, paired_comparison


# The evaluation-config fields real duplicate-seat reports persist; the
# strict comparability gate requires all of them in both reports.
FULL_CONFIG = {
    "match_mode": "chongci",
    "chongci_config": {"starting_score": 2000, "bust_threshold": 0, "max_hands": 50},
    "seats": [0, 1, 2, 3],
    "max_steps_per_episode": 4000,
    "oracle_observation": False,
    "event_history_window": 0,
    "large_loss_threshold": -800.0,
    "bridge_lib_sha256": "a" * 64,
}


def make_report(seeds, per_seed_means, large_loss_rate=0.05, with_field=True):
    """Realistic duplicate-seat report (full persisted config). with_field=False
    mimics an OLD report that predates per_seed_mean_placements
    (reconstruction fallback)."""
    report = {
        "seeds": list(seeds),
        "mean_placement": float(np.mean(per_seed_means)) if len(seeds) else 0.0,
        "large_loss_rate": large_loss_rate,
        "seat_reports": [
            {"per_episode_placements": [float(m) for m in per_seed_means]}
            for _ in range(4)
        ],
        **FULL_CONFIG,
    }
    if with_field:
        report["per_seed_mean_placements"] = [float(m) for m in per_seed_means]
    return report


def test_identical_reports_zero_delta():
    seeds = list(range(910000, 910010))
    means = list(np.linspace(-1, 1, 10))
    result = paired_comparison(make_report(seeds, means), make_report(seeds, means))
    assert result["num_seeds"] == 10
    assert result["mean_delta"] == pytest.approx(0.0)
    assert result["per_seed_deltas"] == pytest.approx([0.0] * 10)
    assert result["significant"] is False


def test_constant_shift_detected():
    seeds = list(range(910000, 910200))
    rng = np.random.default_rng(2)
    base = rng.normal(scale=0.1, size=200)
    # Shift with small per-seed jitter: paired deltas have std ~0.01, so the
    # paired CI95 is ~0.0014 — while an UNPAIRED computation over the two
    # base-noise-dominated samples gives ~0.019. The 0.01 bound therefore
    # fails any implementation that is not genuinely paired per seed.
    jitter = rng.normal(scale=0.01, size=200)
    result = paired_comparison(
        make_report(seeds, list(base + 0.5 + jitter)),
        make_report(seeds, list(base)),
    )
    assert result["mean_delta"] == pytest.approx(0.5, abs=5e-3)
    assert result["delta_ci95_clustered"] < 0.01
    assert result["significant"] is True


def test_seed_mismatch_refused():
    a = make_report([1, 2, 3], [0.0, 0.0, 0.0])
    b = make_report([1, 2, 4], [0.0, 0.0, 0.0])
    with pytest.raises(ValueError, match="seed"):
        paired_comparison(a, b)
    with pytest.raises(ValueError, match="seed"):
        paired_comparison(make_report([], []), make_report([], []))


def test_old_report_reconstruction_fallback():
    seeds = list(range(5))
    means = [0.1, -0.2, 0.3, 0.0, -0.1]
    old = make_report(seeds, means, with_field=False)
    assert "per_seed_mean_placements" not in old
    result = paired_comparison(old, make_report(seeds, means))
    assert result["mean_delta"] == pytest.approx(0.0)


def test_cli_json_mode(tmp_path, capsys):
    seeds = list(range(910000, 910020))
    means = list(np.linspace(-0.5, 0.5, 20))
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_a.write_text(json.dumps(make_report(seeds, [m + 0.1 for m in means])))
    path_b.write_text(json.dumps(make_report(seeds, means)))

    main([str(path_a), str(path_b), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["num_seeds"] == 20
    assert payload["mean_delta"] == pytest.approx(0.1, abs=1e-6)


def test_cli_text_mode(tmp_path, capsys):
    seeds = [1, 2, 3, 4]
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_a.write_text(json.dumps(make_report(seeds, [0.5, 0.5, 0.5, 0.5])))
    path_b.write_text(json.dumps(make_report(seeds, [0.0, 0.0, 0.0, 0.0])))

    main([str(path_a), str(path_b)])
    out = capsys.readouterr().out
    assert "mean delta" in out
    assert "0.5" in out


def test_wrapped_evaluate_report_unwrapped(tmp_path, capsys):
    # fh-mj-evaluate --report-output nests the duplicate-seat report under
    # "online"; the CLI must accept that exact serialized shape.
    seeds = list(range(910000, 910008))
    means = [0.1, -0.2, 0.3, 0.0, -0.1, 0.2, -0.3, 0.1]
    wrapped_a = {"checkpoint": "a.pt", "online": make_report(seeds, [m + 0.2 for m in means]), "offline": None}
    wrapped_b = {"checkpoint": "b.pt", "online": make_report(seeds, means), "offline": None}

    result = paired_comparison(wrapped_a, wrapped_b)
    assert result["mean_delta"] == pytest.approx(0.2, abs=1e-9)

    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_a.write_text(json.dumps(wrapped_a))
    path_b.write_text(json.dumps(wrapped_b))
    main([str(path_a), str(path_b), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["mean_delta"] == pytest.approx(0.2, abs=1e-9)


def test_incompatible_configs_refused():
    seeds = [1, 2, 3]
    means = [0.0, 0.1, -0.1]
    a = make_report(seeds, means)
    b = make_report(seeds, means)
    a["match_mode"] = "chongci"
    b["match_mode"] = "classic"
    with pytest.raises(ValueError, match="not comparable.*match_mode"):
        paired_comparison(a, b)

    a = make_report(seeds, means)
    b = make_report(seeds, means)
    a["chongci_config"] = {"starting_score": 2000, "bust_threshold": 0, "max_hands": 50}
    b["chongci_config"] = {"starting_score": 2000, "bust_threshold": 0, "max_hands": 40}
    with pytest.raises(ValueError, match="not comparable.*chongci_config"):
        paired_comparison(a, b)

    a = make_report(seeds, means)
    b = make_report(seeds, means)
    a["seats"] = [0, 1, 2, 3]
    b["seats"] = [0, 1]
    with pytest.raises(ValueError, match="not comparable.*seats"):
        paired_comparison(a, b)


def test_missing_config_fails_closed_with_legacy_opt_in():
    # A gate verdict requires the full evaluation config in BOTH reports:
    # a legacy report missing a persisted setting is refused by default and
    # only comparable via the explicit opt-in, which marks the result legacy.
    seeds = [1, 2, 3]
    means = [0.0, 0.1, -0.1]
    a = make_report(seeds, means)
    legacy = make_report(seeds, means)
    del legacy["max_steps_per_episode"]
    with pytest.raises(ValueError, match="max_steps_per_episode missing from report B"):
        paired_comparison(a, legacy)

    result = paired_comparison(a, legacy, allow_missing_config=True)
    assert result["num_seeds"] == 3
    assert result["config_check"] == "legacy"
    assert paired_comparison(a, make_report(seeds, means))["config_check"] == "strict"


def test_duplicate_seeds_refused():
    # Repeated wall seeds are identical simulations, not independent
    # clusters — counting them would shrink the CI.
    seeds = [1, 2, 2, 3]
    means = [0.0, 0.1, 0.1, -0.1]
    with pytest.raises(ValueError, match="duplicate wall seed"):
        paired_comparison(make_report(seeds, means), make_report(seeds, means))


def test_cli_allow_missing_config_flag(tmp_path, capsys):
    seeds = [1, 2, 3, 4]
    means = [0.1, 0.2, -0.1, 0.0]
    a = make_report(seeds, means)
    legacy = make_report(seeds, means)
    del legacy["oracle_observation"]
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_a.write_text(json.dumps(a))
    path_b.write_text(json.dumps(legacy))

    with pytest.raises(ValueError, match="oracle_observation missing"):
        main([str(path_a), str(path_b)])

    main([str(path_a), str(path_b), "--allow-missing-config"])
    out = capsys.readouterr().out
    assert "NOT a valid promotion gate" in out


def test_protocol_mismatch_refused():
    # A sampled or search-assisted run is a different decision protocol than
    # a greedy one; identical seeds do not make them comparable.
    seeds = list(range(4))
    means = [0.1, -0.1, 0.2, 0.0]
    greedy = {"checkpoint": "a.pt", "online": make_report(seeds, means)}
    sampled = {
        "checkpoint": "b.pt",
        "online": make_report(seeds, means),
        "sampling": {"temperature": 0.8, "top_k": 3, "action_family": "discard", "seed": 1},
    }
    searched = {
        "checkpoint": "c.pt",
        "online": make_report(seeds, means),
        "search": {"num_determinizations": 16, "max_candidates": 4, "prior_mass_cutoff": 0.95,
                   "max_rollout_decisions": 512, "seed": 7, "fallback_count": 0},
    }
    with pytest.raises(ValueError, match="decision protocol"):
        paired_comparison(greedy, sampled)
    with pytest.raises(ValueError, match="decision protocol"):
        paired_comparison(sampled, searched)
    # Bare (unwrapped) report == protocol-free == greedy wrapper: comparable.
    result = paired_comparison(greedy, make_report(seeds, means))
    assert result["num_seeds"] == 4


def test_search_fallback_count_is_result_not_protocol():
    # fallback_count is a run RESULT inside the search block; two runs of the
    # identical search protocol may differ on it and stay comparable.
    seeds = list(range(4))
    means = [0.1, -0.1, 0.2, 0.0]
    search_params = {"num_determinizations": 16, "max_candidates": 4, "prior_mass_cutoff": 0.95,
                     "max_rollout_decisions": 512, "seed": 7}
    a = {"online": make_report(seeds, means), "search": {**search_params, "fallback_count": 0}}
    b = {"online": make_report(seeds, means), "search": {**search_params, "fallback_count": 3}}
    result = paired_comparison(a, b)
    assert result["num_seeds"] == 4


def test_large_loss_threshold_mismatch_refused():
    seeds = [1, 2, 3]
    means = [0.0, 0.1, -0.1]
    a = make_report(seeds, means)
    b = make_report(seeds, means)
    a["large_loss_threshold"] = -800.0
    b["large_loss_threshold"] = -500.0
    with pytest.raises(ValueError, match="not comparable.*large_loss_threshold"):
        paired_comparison(a, b)


def test_bare_extracted_report_keeps_protocol():
    # The evaluator persists sampling/search blocks INSIDE the online report:
    # extracting it from the wrapper must not launder it into a greedy run.
    seeds = list(range(4))
    means = [0.1, -0.1, 0.2, 0.0]
    sampled_inner = make_report(seeds, means)
    sampled_inner["sampling"] = {"temperature": 0.8, "top_k": 3, "action_family": "discard", "seed": 1}
    greedy_wrapped = {"checkpoint": "a.pt", "online": make_report(seeds, means)}
    with pytest.raises(ValueError, match="decision protocol"):
        paired_comparison(sampled_inner, greedy_wrapped)


def test_bridge_digest_mismatch_refused_unless_opted_in(capsys):
    seeds = list(range(4))
    means = [0.1, -0.1, 0.2, 0.0]
    a = make_report(seeds, means)
    b = make_report(seeds, means)
    b["bridge_lib_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="bridge_lib_sha256.*cross-simulator"):
        paired_comparison(a, b)

    result = paired_comparison(a, b, allow_bridge_mismatch=True)
    assert result["bridge_check"] == "mismatch-allowed"
    same = paired_comparison(a, make_report(seeds, means))
    assert same["bridge_check"] == "match"


def test_bridge_library_digest_helper(tmp_path, monkeypatch):
    import hashlib

    from fh_mahjong_ai.evaluate import _bridge_library_digest

    lib = tmp_path / "libfake_bridge.so"
    lib.write_bytes(b"simulator build 1")
    expected = hashlib.sha256(b"simulator build 1").hexdigest()
    assert _bridge_library_digest("go", str(lib)) == expected

    monkeypatch.setenv("FH_MAHJONG_BRIDGE_LIB", str(lib))
    assert _bridge_library_digest("go", None) == expected

    assert _bridge_library_digest("mock", None) is None
    assert _bridge_library_digest("go", str(tmp_path / "missing.so")) is None


def test_null_digests_are_not_provenance():
    # Two reports with bridge_lib_sha256=null share NO verified simulator:
    # strict mode refuses; the legacy opt-in compares but marks non-gating.
    seeds = list(range(4))
    means = [0.1, -0.1, 0.2, 0.0]
    a = make_report(seeds, means)
    b = make_report(seeds, means)
    a["bridge_lib_sha256"] = None
    b["bridge_lib_sha256"] = None
    with pytest.raises(ValueError, match="no\\s+verifiable simulator provenance"):
        paired_comparison(a, b)

    result = paired_comparison(a, b, allow_missing_config=True)
    assert result["config_check"] == "legacy"

    # Malformed digest strings are absent provenance too.
    a["bridge_lib_sha256"] = "not-a-sha"
    b["bridge_lib_sha256"] = "a" * 64
    with pytest.raises(ValueError, match="report\\(s\\) A"):
        paired_comparison(a, b)


def test_snapshot_bridge_library_immutable_artifact(tmp_path):
    # The digest and the loaded path must refer to the same immutable bytes:
    # mutating the SOURCE library after snapshotting must not desync the
    # reported digest from the artifact the bridges load.
    import hashlib

    from fh_mahjong_ai.evaluate import _snapshot_bridge_library

    source = tmp_path / "libfake_bridge.so"
    source.write_bytes(b"simulator build 1")
    expected = hashlib.sha256(b"simulator build 1").hexdigest()

    path, digest, holder = _snapshot_bridge_library("go", str(source))
    try:
        assert digest == expected
        assert path != str(source)
        # Simulate a concurrent rebuild of the source AFTER the snapshot.
        source.write_bytes(b"simulator build 2 -- rebuilt mid-eval")
        snapshot_bytes = open(path, "rb").read()
        assert hashlib.sha256(snapshot_bytes).hexdigest() == digest
    finally:
        if holder is not None:
            holder.cleanup()

    # Non-Go bridges and unreadable libraries pass through with no digest.
    assert _snapshot_bridge_library("mock", None) == (None, None, None)
    missing_path, missing_digest, missing_holder = _snapshot_bridge_library(
        "go", str(tmp_path / "missing.so")
    )
    assert missing_digest is None and missing_holder is None
    assert missing_path == str(tmp_path / "missing.so")


def test_constant_nonzero_delta_is_significant():
    # A perfectly consistent per-seed delta collapses the CI to a point
    # estimate — that is maximal evidence, not "no significance".
    # Integer-valued means keep the per-seed deltas EXACTLY equal in float,
    # so the CI width is exactly 0 (not rounding noise) — the case the old
    # `ci95 > 0` rule wrongly reported as not significant.
    seeds = list(range(6))
    base = [1.0, -2.0, 3.0, 0.0, -1.0, 2.0]
    result = paired_comparison(
        make_report(seeds, [b + 1.0 for b in base]),
        make_report(seeds, base),
    )
    assert result["mean_delta"] == pytest.approx(1.0)
    assert result["delta_ci95_clustered"] == 0.0
    assert result["significant"] is True

    # But a single seed can never be significant (no degrees of freedom).
    single = paired_comparison(make_report([1], [0.5]), make_report([1], [0.0]))
    assert single["significant"] is False


def test_event_window_mismatch_refused():
    seeds = [1, 2, 3]
    means = [0.0, 0.1, -0.1]
    a = make_report(seeds, means)
    b = make_report(seeds, means)
    a["event_history_window"] = 128
    b["event_history_window"] = 0
    with pytest.raises(ValueError, match="not comparable.*event_history_window"):
        paired_comparison(a, b)


def test_window_mismatch_allowed_with_flag():
    # The promotion comparison: window-on candidate vs window-off champion —
    # the window IS the intervention under test; labeled, never silent.
    seeds = [1, 2, 3]
    means = [0.0, 0.1, -0.1]
    a = make_report(seeds, means)
    b = make_report(seeds, means)
    a["event_history_window"] = 128
    b["event_history_window"] = 0
    result = paired_comparison(a, b, allow_window_mismatch=True)
    assert result["window_check"] == "mismatch-allowed"

    same = paired_comparison(make_report(seeds, means), make_report(seeds, means))
    assert same["window_check"] == "match"


def make_tail_report(seeds, placements, fourth, ll, util, deal_in=0.12):
    r = make_report(seeds, placements)
    r["per_seed_mean_fourth_share"] = list(map(float, fourth))
    r["per_seed_mean_large_loss"] = list(map(float, ll))
    r["per_seed_mean_training_utility"] = list(map(float, util))
    r["deal_in_rate"] = deal_in
    r["rank_parity_mismatches"] = 0
    return r


def test_tail_metrics_paired_and_gated():
    seeds = list(range(1300000, 1300040))
    n = len(seeds)
    a = make_tail_report(seeds, [0.0]*n, [0.20]*n, [0.04]*n, [0.1]*n)
    b = make_tail_report(seeds, [0.0]*n, [0.25]*n, [0.05]*n, [0.0]*n)
    # add tiny seed-varying noise so SEM is finite and nonzero
    a["per_seed_mean_fourth_share"] = [0.20 + 0.001*((i % 3) - 1) for i in range(n)]
    res = paired_comparison(a, b)
    t = res["tail_metrics"]["fourth_share"]
    assert t["mean_delta"] == pytest.approx(-0.05, abs=1e-3)
    assert t["ci95_upper"] < 0
    assert res["tail_metrics"]["large_loss"]["mean_delta"] == pytest.approx(-0.01)
    assert res["deal_in_rate_a"] == 0.12
    g = res["tail_gate"]
    assert g["fourth_primary_pass"] and g["canonical_noninferiority_pass"] and g["large_loss_safety_pass"] and g["all_pass"]
    assert res["significant"] is False  # canonical metric untouched


def test_tail_metrics_missing_in_one_report_is_error():
    seeds = list(range(10)); n = 10
    a = make_tail_report(seeds, [0.0]*n, [0.2]*n, [0.0]*n, [0.0]*n)
    b = make_report(seeds, [0.0]*n)
    with pytest.raises(ValueError, match="tail"):
        paired_comparison(a, b)


def test_tail_metrics_absent_in_both_is_none():
    seeds = list(range(10))
    res = paired_comparison(make_report(seeds, [0.0]*10), make_report(seeds, [0.0]*10))
    assert res["tail_metrics"] is None and res["tail_gate"] is None


# --- Gate-boundary lock tests -------------------------------------------
#
# These pin each of the three registered tail-gate conditions at or near its
# boundary, including the FAIL branch, so a future accidental sign flip
# (e.g. `>=` for `<`, or flipping a comparison operand) is caught by CI
# rather than only by an all-PASS smoke test far from every threshold.


def add_tail_fields(report, fourth, ll, util, deal_in=0.12):
    """Like make_tail_report, but attaches tail fields to an EXISTING report
    (built with its own placements) instead of building both sides from the
    same placements list — needed to control the canonical placement delta
    and the tail deltas independently for boundary tests."""
    report["per_seed_mean_fourth_share"] = list(map(float, fourth))
    report["per_seed_mean_large_loss"] = list(map(float, ll))
    report["per_seed_mean_training_utility"] = list(map(float, util))
    report["deal_in_rate"] = deal_in
    report["rank_parity_mismatches"] = 0
    return report


def test_fourth_primary_pass_at_exact_delta_boundary():
    # Constant per-seed deltas => sem=0, ci=0, so ci95_upper == mean_delta
    # exactly. Subtracting from 0.0 (a=0.0, b=0.01) introduces no rounding
    # error, so mean_delta is bit-exact -0.010 == FOURTH_PRIMARY_MAX_DELTA
    # (verified: a generic a=0.20/b=0.21 pair is NOT bit-exact here — numpy's
    # array-mean summation order lands at -0.009999999999999981, the wrong
    # side of the boundary — hence this specific construction).
    seeds = list(range(5))
    a = make_tail_report(seeds, [0.0]*5, [0.0]*5, [0.0]*5, [0.0]*5)
    b = make_tail_report(seeds, [0.0]*5, [0.01]*5, [0.0]*5, [0.0]*5)
    res = paired_comparison(a, b)
    f = res["tail_metrics"]["fourth_share"]
    assert f["mean_delta"] == -0.010
    assert f["ci95_upper"] < 0.0
    assert res["tail_gate"]["fourth_primary_pass"] is True


def test_fourth_primary_fails_when_delta_short_of_threshold():
    # mean_delta ~= -0.009, i.e. strictly above (less negative than) -0.010.
    # ci95_upper is still < 0 (constant deltas => ci=0), so this isolates
    # the delta-magnitude leg of the AND — a `<=` -> `<` flip on the
    # threshold comparison would NOT be caught by this test (it would still
    # fail), but a dropped delta check entirely would be.
    seeds = list(range(5))
    a = make_tail_report(seeds, [0.0]*5, [0.201]*5, [0.0]*5, [0.0]*5)
    b = make_tail_report(seeds, [0.0]*5, [0.210]*5, [0.0]*5, [0.0]*5)
    res = paired_comparison(a, b)
    f = res["tail_metrics"]["fourth_share"]
    assert f["mean_delta"] > -0.010
    assert f["ci95_upper"] < 0.0
    assert res["tail_gate"]["fourth_primary_pass"] is False


def test_fourth_primary_fails_when_ci_upper_nonnegative_despite_delta():
    # mean_delta <= -0.010 but the per-seed deltas are noisy enough that the
    # CI upper bound crosses zero -> must FAIL despite the delta condition
    # alone being satisfied. Uses n=2 (df=1, t_crit ~= 12.706) with deltas
    # [-0.02, 0.0] (mean -0.01, sem 0.01, ci ~=0.127, ci95_upper ~=+0.117).
    seeds = [1, 2]
    a = make_tail_report(seeds, [0.0, 0.0], [0.18, 0.20], [0.0, 0.0], [0.0, 0.0])
    b = make_tail_report(seeds, [0.0, 0.0], [0.20, 0.20], [0.0, 0.0], [0.0, 0.0])
    res = paired_comparison(a, b)
    f = res["tail_metrics"]["fourth_share"]
    assert f["mean_delta"] == pytest.approx(-0.01)
    assert f["ci95_upper"] > 0.0
    assert res["tail_gate"]["fourth_primary_pass"] is False


def _canonical_ci95_lower_case(target_offset):
    """Build a 2-seed report pair whose canonical placement delta has
    mean_delta == 0 and ci95_lower == -target_offset exactly (computed via
    the module's own _t_critical_975, not a hardcoded approximation).

    With deltas [-k, +k] on n=2: mean=0, sem = |d1-d2|/2 = k,
    ci = t_crit(df=1) * k. Choosing k = target_offset / t_crit makes
    ci95_lower = mean - ci = -target_offset by construction.
    """
    seeds = [1, 2]
    t_crit = _t_critical_975(1)
    k = target_offset / t_crit
    placements_a = [-k, k]
    placements_b = [0.0, 0.0]
    a = add_tail_fields(make_report(seeds, placements_a), [0.2, 0.2], [0.0, 0.0], [0.0, 0.0])
    b = add_tail_fields(make_report(seeds, placements_b), [0.2, 0.2], [0.0, 0.0], [0.0, 0.0])
    return paired_comparison(a, b)


def test_canonical_noninferiority_fails_just_below_boundary():
    # ci95_lower ~= -0.032, i.e. NOT > -0.030 -> fails.
    res = _canonical_ci95_lower_case(0.030 + 0.002)
    assert (res["mean_delta"] - res["delta_ci95_clustered"]) == pytest.approx(-0.032, abs=1e-9)
    assert res["tail_gate"]["canonical_noninferiority_pass"] is False


def test_canonical_noninferiority_passes_just_above_boundary():
    # ci95_lower ~= -0.028, i.e. > -0.030 -> passes.
    res = _canonical_ci95_lower_case(0.030 - 0.002)
    assert (res["mean_delta"] - res["delta_ci95_clustered"]) == pytest.approx(-0.028, abs=1e-9)
    assert res["tail_gate"]["canonical_noninferiority_pass"] is True


def _large_loss_ci95_upper_case(target):
    """2-seed pair whose large-loss delta has mean_delta == 0 and
    ci95_upper == target exactly, via the same t_crit-scaled construction
    as _canonical_ci95_lower_case (see there for the derivation)."""
    seeds = [1, 2]
    t_crit = _t_critical_975(1)
    k = target / t_crit
    a = make_tail_report(seeds, [0.0, 0.0], [0.2, 0.2], [-k, k], [0.0, 0.0])
    b = make_tail_report(seeds, [0.0, 0.0], [0.2, 0.2], [0.0, 0.0], [0.0, 0.0])
    return paired_comparison(a, b)


def test_large_loss_safety_fails_just_above_boundary():
    # ci95_upper ~= 0.006 > 0.005 -> fails.
    res = _large_loss_ci95_upper_case(0.005 + 0.001)
    ll = res["tail_metrics"]["large_loss"]
    assert ll["ci95_upper"] == pytest.approx(0.006, abs=1e-9)
    assert res["tail_gate"]["large_loss_safety_pass"] is False


def test_large_loss_safety_passes_at_or_below_boundary():
    # ci95_upper ~= 0.004 <= 0.005 -> passes. (Testing a value just below
    # the boundary rather than bit-exact 0.005 avoids float-equality
    # brittleness on the `<=` comparison; the case above already pins the
    # other side of the same boundary.)
    res = _large_loss_ci95_upper_case(0.005 - 0.001)
    ll = res["tail_metrics"]["large_loss"]
    assert ll["ci95_upper"] == pytest.approx(0.004, abs=1e-9)
    assert res["tail_gate"]["large_loss_safety_pass"] is True


def test_tail_gate_fail_renders_in_format_text():
    seeds = [1, 2]
    a = make_tail_report(seeds, [0.0, 0.0], [0.18, 0.20], [0.0, 0.0], [0.0, 0.0])
    b = make_tail_report(seeds, [0.0, 0.0], [0.20, 0.20], [0.0, 0.0], [0.0, 0.0])
    res = paired_comparison(a, b)
    assert res["tail_gate"]["all_pass"] is False
    text = _format_text(res, "A", "B")
    assert "tail gate: FAIL" in text
    assert "primary fail" in text


def test_tail_gate_pass_renders_in_format_text():
    seeds = list(range(1300000, 1300040))
    n = len(seeds)
    a = make_tail_report(seeds, [0.0]*n, [0.20]*n, [0.04]*n, [0.1]*n)
    b = make_tail_report(seeds, [0.0]*n, [0.25]*n, [0.05]*n, [0.0]*n)
    a["per_seed_mean_fourth_share"] = [0.20 + 0.001*((i % 3) - 1) for i in range(n)]
    res = paired_comparison(a, b)
    assert res["tail_gate"]["all_pass"] is True
    text = _format_text(res, "A", "B")
    assert "tail gate: PASS" in text
    assert "primary pass" in text


def test_absent_tail_metrics_note_renders_in_format_text():
    seeds = list(range(10))
    res = paired_comparison(make_report(seeds, [0.0]*10), make_report(seeds, [0.0]*10))
    text = _format_text(res, "A", "B")
    assert "NOTE: no tail metrics — reports predate the tail-aware evaluator" in text
