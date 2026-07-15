import json

import numpy as np
import pytest

from fh_mahjong_ai.scripts.compare_reports import main, paired_comparison


def make_report(seeds, per_seed_means, large_loss_rate=0.05, with_field=True):
    """Minimal duplicate-seat report. with_field=False mimics an OLD report
    that predates per_seed_mean_placements (reconstruction fallback)."""
    report = {
        "seeds": list(seeds),
        "mean_placement": float(np.mean(per_seed_means)),
        "large_loss_rate": large_loss_rate,
        "seat_reports": [
            {"per_episode_placements": [float(m) for m in per_seed_means]}
            for _ in range(4)
        ],
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


def test_missing_config_keys_still_comparable():
    # Reports predating the persisted config fields must not be rejected:
    # the compatibility check applies only to keys present in BOTH reports.
    seeds = [1, 2, 3]
    means = [0.0, 0.1, -0.1]
    a = make_report(seeds, means)
    a["match_mode"] = "chongci"
    b = make_report(seeds, means)  # no match_mode at all
    result = paired_comparison(a, b)
    assert result["num_seeds"] == 3
