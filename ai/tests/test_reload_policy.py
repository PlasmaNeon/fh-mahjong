from __future__ import annotations

import pytest
from fh_mahjong_ai.scripts.reload_policy import _auth_headers, reload_payload


def test_reload_payload_checkpoint_path() -> None:
    assert reload_payload("/models/a.pt", None) == {"checkpoint": "/models/a.pt"}


def test_reload_payload_checkpoint_id() -> None:
    assert reload_payload(None, "current") == {"checkpoint_id": "current"}


def test_reload_payload_requires_a_target() -> None:
    with pytest.raises(ValueError):
        reload_payload(None, None)


def test_reload_payload_never_carries_admin_token() -> None:
    """Adversarial round 15, Finding 1: the admin token must NEVER appear in
    the /reload request body — the server authenticates it from an
    `Authorization: Bearer <token>` header before reading the body at all
    (see `_auth_headers`), so `reload_payload` has no `admin_token`
    parameter to accidentally leak it through."""
    assert reload_payload("/models/a.pt", None) == {"checkpoint": "/models/a.pt"}
    assert "admin_token" not in reload_payload("/models/a.pt", None, expected_sha256="deadbeef")


def test_reload_payload_carries_expected_sha256() -> None:
    assert reload_payload("/models/a.pt", None, expected_sha256="deadbeef") == {
        "checkpoint": "/models/a.pt",
        "expected_sha256": "deadbeef",
    }


def test_reload_payload_omits_expected_sha256_when_absent() -> None:
    assert reload_payload("/models/a.pt", None, expected_sha256=None) == {
        "checkpoint": "/models/a.pt",
    }


def test_reload_payload_carries_expected_event_window() -> None:
    """Enables a deliberate cross-window swap (e.g. window-0 -> window-128)
    through the CLI: without this field the server requires the new
    checkpoint's event_window to match the currently-serving policy's
    window, which refuses exactly that kind of swap."""
    assert reload_payload("/models/a.pt", None, expected_event_window=128) == {
        "checkpoint": "/models/a.pt",
        "expected_event_window": 128,
    }


def test_reload_payload_omits_expected_event_window_when_absent() -> None:
    assert reload_payload("/models/a.pt", None, expected_event_window=None) == {
        "checkpoint": "/models/a.pt",
    }


def test_reload_payload_combines_sha256_and_event_window() -> None:
    assert reload_payload(
        "/models/a.pt", None, expected_sha256="deadbeef", expected_event_window=128
    ) == {
        "checkpoint": "/models/a.pt",
        "expected_sha256": "deadbeef",
        "expected_event_window": 128,
    }


def test_auth_headers_carries_bearer_token() -> None:
    """Adversarial round 15, Finding 1: the CLI must thread --admin-token
    (or FH_MJ_ADMIN_TOKEN) through as an `Authorization: Bearer <token>`
    header, since the server now authenticates POST /reload from that
    header (checked before the body is read) rather than a body field."""
    assert _auth_headers("s3cr3t") == {"Authorization": "Bearer s3cr3t"}


def test_auth_headers_empty_when_no_token() -> None:
    assert _auth_headers(None) == {}
    assert _auth_headers("") == {}
