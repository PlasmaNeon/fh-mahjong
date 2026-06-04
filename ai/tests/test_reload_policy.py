from __future__ import annotations

import pytest
from fh_mahjong_ai.scripts.reload_policy import reload_payload


def test_reload_payload_checkpoint_path() -> None:
    assert reload_payload("/models/a.pt", None) == {"checkpoint": "/models/a.pt"}


def test_reload_payload_checkpoint_id() -> None:
    assert reload_payload(None, "current") == {"checkpoint_id": "current"}


def test_reload_payload_requires_a_target() -> None:
    with pytest.raises(ValueError):
        reload_payload(None, None)
