import numpy as np
import pytest

from fh_mahjong_ai.evaluate import (
    _t_critical_975,
    clustered_placement_stats,
)


def test_t_critical_matches_tables():
    # Known two-sided 95% Student-t critical values.
    assert _t_critical_975(1) == pytest.approx(12.706, abs=0.01)
    assert _t_critical_975(2) == pytest.approx(4.303, abs=0.01)
    assert _t_critical_975(4) == pytest.approx(2.776, abs=0.01)
    assert _t_critical_975(10) == pytest.approx(2.228, abs=0.01)
    assert _t_critical_975(119) == pytest.approx(1.980, abs=0.005)
    assert _t_critical_975(10_000) == pytest.approx(1.960, abs=0.002)


def test_per_seed_means_and_count():
    # 2 seats x 3 seeds; per-seed mean = column mean.
    stats = clustered_placement_stats([[1.0, 0.0, -1.0], [0.0, 1.0, -1.0]])
    assert stats["per_seed_mean_placements"] == pytest.approx([0.5, 0.5, -1.0])
    assert stats["num_seeds"] == 3
    assert stats["mean_placement_clustered"] == pytest.approx(0.0)


def test_seat_order_invariance():
    # Reordering seats (rows) must not change any statistic: the seed is the
    # cluster, and a per-seed mean is order-free.
    a = [[1.0, 0.2, -0.5, 0.9], [0.0, 0.4, -1.0, 0.3], [0.5, -0.2, 0.0, 0.1]]
    s1 = clustered_placement_stats(a)
    s2 = clustered_placement_stats([a[2], a[0], a[1]])
    assert s1["per_seed_mean_placements"] == pytest.approx(s2["per_seed_mean_placements"])
    assert s1["mean_placement_ci95_clustered"] == pytest.approx(s2["mean_placement_ci95_clustered"])
    assert s1["cluster_design_effect"] == pytest.approx(s2["cluster_design_effect"])


def test_unequal_lengths_rejected():
    with pytest.raises(ValueError):
        clustered_placement_stats([[1.0, 2.0], [1.0]])


def test_correlated_seeds_widen_ci():
    # Strong within-seed correlation: all 4 rotations of a seed share its
    # value. Clustered CI must exceed the naive iid CI (design effect > 1).
    rng = np.random.default_rng(0)
    seed_values = rng.normal(size=200)
    per_seat = [list(seed_values) for _ in range(4)]  # identical rotations
    stats = clustered_placement_stats(per_seat)
    flat = np.repeat(seed_values, 1)  # any one seat row IS the seed values
    naive_sem = float(np.std(np.concatenate([flat] * 4), ddof=1) / np.sqrt(800))
    naive_ci = 1.96 * naive_sem
    assert stats["mean_placement_ci95_clustered"] > naive_ci
    assert stats["cluster_design_effect"] == pytest.approx(4.0, rel=0.05)


def test_independent_data_design_effect_near_one():
    rng = np.random.default_rng(1)
    per_seat = [list(rng.normal(size=500)) for _ in range(4)]
    stats = clustered_placement_stats(per_seat)
    assert 0.7 < stats["cluster_design_effect"] < 1.3


def test_degenerate_inputs():
    empty = clustered_placement_stats([])
    assert empty["num_seeds"] == 0
    assert empty["per_seed_mean_placements"] == []
    assert empty["mean_placement_ci95_clustered"] == 0.0
    one = clustered_placement_stats([[0.5], [0.7]])
    assert one["num_seeds"] == 1
    assert one["mean_placement_ci95_clustered"] == 0.0  # no df -> no interval


def test_clustered_report_fields_from_seat_reports():
    from fh_mahjong_ai.evaluate import _clustered_report_fields

    seat_reports = [
        {"per_episode_placements": [1.0, -1.0]},
        {"per_episode_placements": [1.0 / 3.0, -1.0 / 3.0]},
        {"per_episode_placements": [-1.0 / 3.0, 1.0 / 3.0]},
        {"per_episode_placements": [-1.0, 1.0]},
    ]
    fields = _clustered_report_fields(seat_reports)
    # Duplicate seats of one seed cover all four ranks -> per-seed mean 0.
    assert fields["per_seed_mean_placements"] == pytest.approx([0.0, 0.0])
    assert fields["mean_placement_ci95_clustered"] == pytest.approx(0.0)

    # Ragged seat reports (defensive path) degrade to empty stats, not a crash.
    ragged = _clustered_report_fields([{"per_episode_placements": [1.0]}, {"per_episode_placements": []}])
    assert ragged["per_seed_mean_placements"] == []
