import numpy as np
import pytest

from fh_mahjong_ai.placement_bonus import (
    PLACEMENT_RESHAPE_VALUES, exact_final_scores, placement_utilities, rank_occupancy,
)

V = PLACEMENT_RESHAPE_VALUES


def test_registered_vector_is_centered_and_rms_matched():
    v = np.asarray(V, dtype=np.float64)
    assert abs(v.mean()) < 1e-9
    canonical_rms = np.sqrt(np.mean(np.square([1.0, 1/3, -1/3, -1.0])))
    assert abs(np.sqrt(np.mean(v**2)) - canonical_rms) < 1e-9
    # shape of (10,5,1,-10) after centering: differences preserved up to one scale
    raw = np.asarray([10.0, 5.0, 1.0, -10.0]); raw = raw - raw.mean()
    assert np.allclose(v / raw, (v / raw)[0])


def test_exact_final_scores_rounds_reward_scale_to_points():
    assert exact_final_scores([1.5, 1.0, -2.5, 0.0], 2000.0) == [3500, 3000, -500, 2000]
    # float32 drift well below half a point must not flip
    assert exact_final_scores([1.4999996, 0, 0, 0], 2000.0)[0] == 3500


def test_utilities_distinct_scores_follow_rank():
    u = placement_utilities([3500, 3000, 2000, -500])
    assert np.allclose(u, V)
    assert abs(u.sum()) < 1e-9


@pytest.mark.parametrize("scores,expected", [
    # two tied leaders share slots 0,1
    ([3000, 3000, 2000, 1000], [(V[0]+V[1])/2, (V[0]+V[1])/2, V[2], V[3]]),
    # two distinct busted seats: still ranked by exact score
    ([3000, 2000, -100, -500], [V[0], V[1], V[2], V[3]]),
    # two tied busted seats share slots 2,3
    ([3000, 2000, -500, -500], [V[0], V[1], (V[2]+V[3])/2, (V[2]+V[3])/2]),
    # three busted with a tie among two of them
    ([4000, -200, -200, -900], [V[0], (V[1]+V[2])/2, (V[1]+V[2])/2, V[3]]),
    # all four tied
    ([2000, 2000, 2000, 2000], [0.0, 0.0, 0.0, 0.0]),
    # three-way tie at the bottom
    ([5000, 1000, 1000, 1000], [V[0]] + [(V[1]+V[2]+V[3])/3]*3),
])
def test_utilities_tie_matrix(scores, expected):
    u = placement_utilities(scores)
    assert np.allclose(u, expected)
    assert abs(u.sum()) < 1e-9


def test_rank_occupancy_fractional_ties():
    occ = rank_occupancy([3000, 3000, 2000, 1000])
    assert np.allclose(occ[0], [0.5, 0.5, 0, 0])
    assert np.allclose(occ[1], [0.5, 0.5, 0, 0])
    assert np.allclose(occ[2], [0, 0, 1, 0])
    assert np.allclose(occ[3], [0, 0, 0, 1])
    assert np.allclose(occ.sum(axis=1), 1.0)
    assert np.allclose(occ.sum(axis=0), 1.0)


def test_rank_occupancy_all_tied():
    assert np.allclose(rank_occupancy([1, 1, 1, 1]), 0.25)


def test_utilities_reject_wrong_seat_count():
    with pytest.raises(ValueError):
        placement_utilities([1, 2, 3])
