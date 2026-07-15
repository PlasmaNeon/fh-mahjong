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
    result = paired_comparison(
        make_report(seeds, list(base + 0.5)),
        make_report(seeds, list(base)),
    )
    assert result["mean_delta"] == pytest.approx(0.5, abs=1e-6)
    assert result["delta_ci95_clustered"] < 0.1
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
