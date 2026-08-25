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


from fh_mahjong_ai.placement_bonus import apply_terminal_bonus, calibrate_lambda, return_scale_gates


def _tel(seed, scores, rets):
    u = placement_utilities(scores)
    return {"seed": seed, "final_scores": scores, "trajectory_returns": rets,
            "utilities": u.tolist(), "bonus": [0.0]*4, "truncated": False,
            "rank_occupancy": rank_occupancy(scores).tolist(), "tie_groups": 0, "busts": 0}


def test_calibrate_lambda_matches_closed_form():
    tel = [_tel(0, [3500, 3000, 2000, -500], [1.5, 1.0, 0.0, -2.5]),
           _tel(1, [2100, 2000, 1900, 2000], [0.1, 0.0, -0.1, 0.0])]
    out = calibrate_lambda(tel, V, k=0.5, require_matches=2)
    R = np.asarray([t["trajectory_returns"] for t in tel]).ravel()
    Vv = np.asarray([t["utilities"] for t in tel]).ravel()
    assert out["lambda"] == pytest.approx(0.5 * R.std() / Vv.std())
    assert out["corr_RV"] == pytest.approx(np.corrcoef(R, Vv)[0, 1])
    assert out["num_records"] == 8


def test_calibrate_lambda_requires_exact_match_count():
    with pytest.raises(ValueError, match="320"):
        calibrate_lambda([_tel(0, [1, 2, 3, 4], [0, 0, 0, 1])], V)


def test_apply_terminal_bonus_hits_each_segment_end():
    rewards = np.zeros(10, np.float32)
    dones = np.zeros(10, np.float32); dones[[1, 4, 6, 9]] = 1.0   # 4 segments = 1 match
    tel = [_tel(0, [3500, 3000, 2000, -500], [0, 0, 0, 0])]
    out = apply_terminal_bonus(rewards, dones, tel, V, 2.0)
    assert np.allclose(out[[1, 4, 6, 9]], 2.0 * np.asarray(V))
    assert np.count_nonzero(out) == 4
    with pytest.raises(ValueError):
        apply_terminal_bonus(rewards, dones[:9], tel, V, 1.0)  # segment/telemetry mismatch


def test_return_scale_gates():
    raw = np.array([1.0, -1.0, 0.5, -0.5]); shaped = raw * 1.2; pred = np.zeros(4)
    g = return_scale_gates(raw, shaped, pred)
    assert g["rms_ratio"] == pytest.approx(1.2) and g["rms_pass"]
    assert g["p99_ratio"] == pytest.approx(1.2) and g["p99_pass"]
    assert g["critic_mse_ratio"] == pytest.approx(1.44) and g["critic_mse_pass"]
    assert g["all_pass"]
    assert not return_scale_gates(raw, raw * 1.5, pred)["all_pass"]


from fh_mahjong_ai.placement_bonus import eval_episode_tail


def test_eval_episode_tail_truncation_is_full_fourth():
    t = eval_episode_tail(np.array([1.0, 0, 0, -1.0]), 0, 2000.0, truncated=True)
    assert t["fourth_share"] == 1.0 and t["utility"] == V[3]
    assert np.allclose(t["occupancy"], [0, 0, 0, 1])


def test_eval_episode_tail_ties_fractional():
    t = eval_episode_tail(np.array([0.0, 0.0, 1.0, -1.0]), 0, 2000.0, truncated=False)
    assert t["fourth_share"] == 0.0 and np.allclose(t["occupancy"], [0, 0.5, 0.5, 0])
    assert t["utility"] == pytest.approx((V[1] + V[2]) / 2)
    assert t["parity_ok"]
