from __future__ import annotations

from fh_mahjong_ai.action_catalog import action_family, action_label, chii_label, tile_face_42_label


def test_action_labels_use_backend_tile_order() -> None:
    assert tile_face_42_label(0) == "1m"
    assert tile_face_42_label(9) == "1p"
    assert tile_face_42_label(18) == "1s"
    assert tile_face_42_label(27) == "1z"
    assert tile_face_42_label(34) == "flower1"
    assert action_label(5) == "discard 1m"
    assert action_label(14) == "discard 1p"
    assert action_label(23) == "discard 1s"


def test_action_labels_cover_calls() -> None:
    assert action_family(47) == "pon"
    assert action_label(47) == "pon 1m"
    assert action_label(81) == "kan_direct 1m"
    assert chii_label(0) == "1m2m3m"
    assert chii_label(7) == "1p2p3p"
    assert chii_label(14) == "1s2s3s"
    assert action_label(183) == "chii 1m2m3m"
