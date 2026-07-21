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


def test_reload_payload_carries_admin_token() -> None:
    """Adversarial round 14, Finding 1a/1c: the CLI must thread --admin-token
    (or FH_MJ_ADMIN_TOKEN) through to the request body, since the server
    refuses every /reload without a matching 'admin_token' field."""
    assert reload_payload("/models/a.pt", None, admin_token="s3cr3t") == {
        "checkpoint": "/models/a.pt",
        "admin_token": "s3cr3t",
    }


def test_reload_payload_carries_expected_sha256() -> None:
    assert reload_payload("/models/a.pt", None, expected_sha256="deadbeef") == {
        "checkpoint": "/models/a.pt",
        "expected_sha256": "deadbeef",
    }


def test_reload_payload_omits_admin_token_and_expected_sha256_when_absent() -> None:
    assert reload_payload("/models/a.pt", None, admin_token=None, expected_sha256=None) == {
        "checkpoint": "/models/a.pt",
    }
