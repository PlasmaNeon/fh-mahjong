from fh_mahjong_ai.evaluate import parse_seed_windows


def test_bare_start_uses_episode_count():
    assert parse_seed_windows(["950000"], episodes=3) == [950000, 950001, 950002]


def test_explicit_count_overrides_episodes():
    assert parse_seed_windows(["950000:2"], episodes=99) == [950000, 950001]


def test_windows_concatenate_in_order():
    assert parse_seed_windows(["910000:2", "950000:2"], episodes=1) == [
        910000,
        910001,
        950000,
        950001,
    ]


def test_no_windows_falls_back_to_start_seed():
    # The evaluate/guarded CLIs default to a contiguous window at --start-seed.
    assert parse_seed_windows([], episodes=3, start_seed=950000) == [950000, 950001, 950002]


def test_no_windows_and_no_start_seed_is_empty():
    # paired_trace requires explicit windows and must not invent a default one.
    assert parse_seed_windows([], episodes=3) == []
