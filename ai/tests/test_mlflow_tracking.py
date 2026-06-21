from fh_mahjong_ai.mlflow_tracking import _metric_key


def test_metric_key_sanitizes_nested_report_bucket_names():
    assert _metric_key("branch_cf.policy_logits.by_reward_gap.0.50+.count") == (
        "branch_cf.policy_logits.by_reward_gap.0.50_.count"
    )
