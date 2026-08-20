"""serve_policy: event-contract validation, enriched /healthz, and a
validated /reload that never swaps in an incompatible checkpoint."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.events import EVENT_CONTRACT_V1
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.serve_policy import (
    PolicyHolder,
    PolicyRequestHandler,
    observation_from_json,
)
from fh_mahjong_ai.serving import CheckpointPolicy
from fh_mahjong_ai.storage import model_config_metadata, save_checkpoint
from conftest import SMALL_MODEL

_ENV = EnvConfig()


def _event_model_config(window: int = 8) -> ModelConfig:
    return ModelConfig(**dict(SMALL_MODEL, event_window=window))


def _save_checkpoint(tmp_path: Path, model_config: ModelConfig, step: int = 1, name: str = "model.pt") -> Path:
    model = PolicyValueNet(_ENV, model_config)
    path = tmp_path / name
    save_checkpoint(path, model, step=step, metadata={"model_config": model_config_metadata(model_config)})
    return path


def _bearer(token: str) -> dict:
    """The `Authorization: Bearer <token>` header POST /reload now requires
    (adversarial round 15, Finding 1) — the admin token no longer travels as
    a JSON body field."""
    return {"Authorization": f"Bearer {token}"}


def _observation_payload(legal: list[int], **event_fields) -> dict:
    env = EnvConfig()
    mask = [0] * env.action_space_size
    for action_id in legal:
        mask[action_id] = 1
    payload = {
        "seat": 0,
        "planes": np.zeros(env.plane_shape, dtype=np.float32).tolist(),
        "scalars": np.zeros(env.scalar_features, dtype=np.float32).tolist(),
        "action_mask": mask,
    }
    payload.update(event_fields)
    return payload


class _Server:
    """A ThreadingHTTPServer bound to port 0, serving a real PolicyHolder, for
    exercising the /act, /healthz, and /reload HTTP contract end to end."""

    def __init__(
        self,
        checkpoint_path: Path,
        manifest_path: Path,
        logit_export_token: str | None = None,
        admin_token: str | None = None,
        evaluate_token: str | None = None,
        policy: CheckpointPolicy | None = None,
    ) -> None:
        # `policy` lets a test serve a specifically-configured policy (e.g. a
        # sampling one); the default is the plain greedy checkpoint policy.
        if policy is None:
            policy = CheckpointPolicy.from_checkpoint(checkpoint_path)
        self.holder = PolicyHolder(
            policy, manifest_path=manifest_path, logit_export_token=logit_export_token, admin_token=admin_token,
            evaluate_token=evaluate_token,
        )
        handler = type("BoundPolicyRequestHandler", (PolicyRequestHandler,), {"holder": self.holder})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def request(
        self, method: str, path: str, payload: dict | None = None, headers: dict | None = None,
    ) -> tuple[int, dict]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = json.dumps(payload) if payload is not None else None
        all_headers = {"content-type": "application/json"} if body is not None else {}
        if headers:
            all_headers.update(headers)
        conn.request(method, path, body=body, headers=all_headers)
        response = conn.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        status = response.status
        conn.close()
        return status, data

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


# --- observation_from_json unit tests -----------------------------------------------------


def test_observation_from_json_window_zero_rejects_garbage_event_fields() -> None:
    """Adversarial round 12, Finding 2 (deliberate contract tightening): a
    window-0 model used to silently ignore ANY event fields sent alongside
    the observation. That let rollback skew (a caller still configured for
    an event model, or with a stale contract_version) succeed against a
    window-0 checkpoint instead of failing loudly. Now, once ANY of the four
    event-contract fields is present, validation is symmetric with the
    event-model branch — garbage values are rejected, not ignored."""
    payload = _observation_payload(
        [0, 1, 2], event_history="not even a list", event_count=-999,
        event_window="garbage", contract_version=None,
    )

    with pytest.raises(ValueError):
        observation_from_json(payload, model_event_window=0)


def test_observation_from_json_window_zero_accepts_no_event_fields_at_all() -> None:
    """True legacy callers (pre-B2c Go, or old test payloads) that omit ALL
    FOUR event-contract fields keep the pre-existing window-0 acceptance."""
    payload = _observation_payload([0, 1, 2])

    observation = observation_from_json(payload, model_event_window=0)

    assert observation.event_history.size == 0


def test_observation_from_json_window_zero_accepts_go_legacy_scalars() -> None:
    """The branch's Go legacy path always sends event_count/event_window/
    contract_version as 0/0/1 even against a window-0 model — this must still
    pass (window 0 == 0, version 1 matches EVENT_CONTRACT_V1)."""
    payload = _observation_payload(
        [0, 1, 2], event_count=0, event_window=0, contract_version=EVENT_CONTRACT_V1,
    )

    observation = observation_from_json(payload, model_event_window=0)

    assert observation.event_history.size == 0


def test_observation_from_json_window_zero_rejects_wrong_event_window() -> None:
    payload = _observation_payload(
        [0, 1, 2], event_count=0, event_window=128, contract_version=EVENT_CONTRACT_V1,
    )

    with pytest.raises(ValueError, match="event_window"):
        observation_from_json(payload, model_event_window=0)


def test_observation_from_json_window_zero_rejects_wrong_contract_version() -> None:
    payload = _observation_payload(
        [0, 1, 2], event_count=0, event_window=0, contract_version=EVENT_CONTRACT_V1 + 1,
    )

    with pytest.raises(ValueError, match="contract_version"):
        observation_from_json(payload, model_event_window=0)


def test_observation_from_json_accepts_valid_short_history() -> None:
    payload = _observation_payload(
        [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
        contract_version=EVENT_CONTRACT_V1,
    )

    observation = observation_from_json(payload, model_event_window=8)

    assert observation.event_history.tolist() == [1, 2, 3]


def test_observation_from_json_accepts_zero_count_early_round() -> None:
    payload = _observation_payload(
        [0, 1, 2], event_history=[], event_count=0, event_window=8,
        contract_version=EVENT_CONTRACT_V1,
    )

    observation = observation_from_json(payload, model_event_window=8)

    assert observation.event_history.size == 0


def test_observation_from_json_missing_event_history_with_zero_count_is_valid() -> None:
    payload = _observation_payload([0, 1, 2], event_count=0, event_window=8, contract_version=EVENT_CONTRACT_V1)
    assert "event_history" not in payload

    observation = observation_from_json(payload, model_event_window=8)

    assert observation.event_history.size == 0


def test_observation_from_json_missing_required_fields_raises() -> None:
    payload = _observation_payload([0, 1, 2])

    with pytest.raises(ValueError):
        observation_from_json(payload, model_event_window=8)


def test_observation_from_json_history_length_mismatch_raises() -> None:
    payload = _observation_payload(
        [0, 1, 2], event_history=[1, 2], event_count=3, event_window=8,
        contract_version=EVENT_CONTRACT_V1,
    )

    with pytest.raises(ValueError, match="event_history"):
        observation_from_json(payload, model_event_window=8)


def test_observation_from_json_count_exceeds_window_raises() -> None:
    payload = _observation_payload(
        [0, 1, 2], event_history=list(range(9)), event_count=9, event_window=8,
        contract_version=EVENT_CONTRACT_V1,
    )

    with pytest.raises(ValueError, match="event_count"):
        observation_from_json(payload, model_event_window=8)


def test_observation_from_json_window_mismatch_raises() -> None:
    payload = _observation_payload(
        [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=16,
        contract_version=EVENT_CONTRACT_V1,
    )

    with pytest.raises(ValueError, match="event_window"):
        observation_from_json(payload, model_event_window=8)


def test_observation_from_json_contract_version_mismatch_raises() -> None:
    payload = _observation_payload(
        [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
        contract_version=EVENT_CONTRACT_V1 + 1,
    )

    with pytest.raises(ValueError, match="contract_version"):
        observation_from_json(payload, model_event_window=8)


# --- HTTP /act contract ---------------------------------------------------------------


def test_http_act_accepts_valid_short_event_history(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
                contract_version=EVENT_CONTRACT_V1,
            ),
        )
    finally:
        server.close()

    assert status == 200, data
    assert data["action_id"] in (0, 1, 2)


def test_http_act_accepts_valid_zero_count_early_round(tmp_path: Path) -> None:
    """Adversarial round 10, Finding 2: a contract-valid zero-event request
    (explicit event_count=0, a documented legitimate early-round case) must
    NOT 400 — CheckpointPolicy.choose's defense-in-depth empty-history raise
    must not fire for a request that observation_from_json already validated
    as explicitly, consistently empty."""
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history=[], event_count=0, event_window=8,
                contract_version=EVENT_CONTRACT_V1,
            ),
        )
    finally:
        server.close()

    assert status == 200, data
    assert data["action_id"] in (0, 1, 2)


def test_http_act_accepts_valid_zero_count_with_missing_event_history_field(tmp_path: Path) -> None:
    """Same as above but with `event_history` omitted entirely (Go's
    `omitempty` drops an empty slice) rather than sent as `[]` — both wire
    shapes are equally valid for event_count=0."""
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_count=0, event_window=8, contract_version=EVENT_CONTRACT_V1,
            ),
        )
    finally:
        server.close()

    assert status == 200, data
    assert data["action_id"] in (0, 1, 2)


def test_http_act_still_400s_when_event_fields_missing_for_event_model(tmp_path: Path) -> None:
    """A request that omits the event fields altogether (not an explicit
    count==0) is the "silently missing" case this fix must keep rejecting —
    contrast with the explicit-zero cases above."""
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request("POST", "/act", _observation_payload([0, 1, 2]))
    finally:
        server.close()

    assert status == 400
    assert "error" in data


def test_http_act_window_zero_model_rejects_garbage_event_fields(tmp_path: Path) -> None:
    """Adversarial round 12, Finding 2 (deliberate contract tightening): a
    window-0 model no longer silently ignores garbage event fields — see
    test_observation_from_json_window_zero_rejects_garbage_event_fields for
    the unit-level version of this same tightening."""
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**SMALL_MODEL))  # event_window=0
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history="garbage", event_count=-999,
                event_window="garbage", contract_version=None,
            ),
        )
    finally:
        server.close()

    assert status == 400
    assert "error" in data


def test_http_act_window_zero_model_accepts_no_event_fields(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**SMALL_MODEL))  # event_window=0
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request("POST", "/act", _observation_payload([0, 1, 2]))
    finally:
        server.close()

    assert status == 200, data
    assert data["action_id"] in (0, 1, 2)


def test_http_act_window_zero_model_accepts_go_legacy_scalars(tmp_path: Path) -> None:
    """The Go legacy path always sends event_count/event_window/
    contract_version as 0/0/1 even against a window-0 model — must still
    succeed (window 0 == 0, version 1 matches)."""
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**SMALL_MODEL))  # event_window=0
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_count=0, event_window=0, contract_version=EVENT_CONTRACT_V1,
            ),
        )
    finally:
        server.close()

    assert status == 200, data
    assert data["action_id"] in (0, 1, 2)


@pytest.mark.parametrize(
    "event_fields,expected_snippet",
    [
        (dict(event_history=[1, 2], event_count=3, event_window=8, contract_version=EVENT_CONTRACT_V1), "event_history"),
        (dict(event_history=list(range(9)), event_count=9, event_window=8, contract_version=EVENT_CONTRACT_V1), "event_count"),
        (dict(event_history=[1, 2, 3], event_count=3, event_window=16, contract_version=EVENT_CONTRACT_V1), "event_window"),
        (dict(event_history=[1, 2, 3], event_count=3, event_window=8, contract_version=EVENT_CONTRACT_V1 + 1), "contract_version"),
    ],
)
def test_http_act_rejects_each_invalid_event_condition(tmp_path: Path, event_fields: dict, expected_snippet: str) -> None:
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request("POST", "/act", _observation_payload([0, 1, 2], **event_fields))
    finally:
        server.close()

    assert status == 400
    assert expected_snippet in data["error"]


# --- HTTP /evaluate contract ------------------------------------------------------------


def test_http_evaluate_threads_event_history_into_evaluate_batch(tmp_path: Path) -> None:
    """/evaluate must feed each observation's validated event_history into
    evaluate_batch, not silently score against a zero history. We pin this by
    comparing the HTTP response against a direct evaluate_batch call with the
    same histories threaded (must match) and against the same call with
    events=None (must NOT match — guards against the fields being dropped)."""
    model_config = _event_model_config(window=8)
    checkpoint = _save_checkpoint(tmp_path, model_config)
    server = _Server(checkpoint, tmp_path / "manifest.json", evaluate_token="eval-token")
    try:
        obs_a = _observation_payload(
            [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
            contract_version=EVENT_CONTRACT_V1,
        )
        obs_b = _observation_payload(
            [0, 1, 2], event_history=[4, 5, 6, 7], event_count=4, event_window=8,
            contract_version=EVENT_CONTRACT_V1,
        )
        status, data = server.request(
            "POST", "/evaluate", {"observations": [obs_a, obs_b]}, headers=_bearer("eval-token"),
        )
    finally:
        server.close()

    assert status == 200, data
    results = data["results"]
    assert len(results) == 2

    policy = CheckpointPolicy.from_checkpoint(checkpoint)
    env = EnvConfig()
    planes = np.zeros((2, *env.plane_shape), dtype=np.float32)
    scalars = np.zeros((2, env.scalar_features), dtype=np.float32)
    mask = np.zeros((2, env.action_space_size), dtype=np.int8)
    mask[:, [0, 1, 2]] = 1
    events = np.zeros((2, 8), dtype=np.int64)
    events[0, :3] = [1, 2, 3]
    events[1, :4] = [4, 5, 6, 7]
    event_lengths = np.array([3, 4], dtype=np.int64)

    _, expected_values = policy.evaluate_batch(planes, scalars, mask, events=events, event_lengths=event_lengths)
    _, zero_history_values = policy.evaluate_batch(planes, scalars, mask, events=None, event_lengths=None)

    for i in range(2):
        assert results[i]["value"] == pytest.approx(float(expected_values[i]), abs=1e-5)
    # Guard against a tautological pass: the events=None baseline must actually
    # differ, otherwise this test wouldn't catch events being dropped.
    assert not (
        results[0]["value"] == pytest.approx(float(zero_history_values[0]), abs=1e-5)
        and results[1]["value"] == pytest.approx(float(zero_history_values[1]), abs=1e-5)
    )


def test_http_evaluate_window_zero_model_rejects_garbage_event_fields(tmp_path: Path) -> None:
    """Adversarial round 12, Finding 2 (deliberate contract tightening):
    /evaluate applies the same symmetric validation as /act — a window-0
    model no longer silently ignores partially-present garbage event
    fields."""
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**SMALL_MODEL))  # event_window=0
    server = _Server(checkpoint, tmp_path / "manifest.json", evaluate_token="eval-token")
    try:
        status, data = server.request(
            "POST", "/evaluate",
            {"observations": [_observation_payload([0, 1, 2], event_history="garbage", event_count=-999)]},
            headers=_bearer("eval-token"),
        )
    finally:
        server.close()

    assert status == 400
    assert "error" in data


def test_http_evaluate_window_zero_model_accepts_no_event_fields(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**SMALL_MODEL))  # event_window=0
    server = _Server(checkpoint, tmp_path / "manifest.json", evaluate_token="eval-token")
    try:
        status, data = server.request(
            "POST", "/evaluate",
            {"observations": [_observation_payload([0, 1, 2])]},
            headers=_bearer("eval-token"),
        )
    finally:
        server.close()

    assert status == 200, data
    assert len(data["results"]) == 1


def test_http_evaluate_accepts_zero_count_event_row(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json", evaluate_token="eval-token")
    try:
        status, data = server.request(
            "POST", "/evaluate",
            {
                "observations": [
                    _observation_payload(
                        [0, 1, 2], event_count=0, event_window=8, contract_version=EVENT_CONTRACT_V1,
                    )
                ]
            },
            headers=_bearer("eval-token"),
        )
    finally:
        server.close()

    assert status == 200, data
    assert len(data["results"]) == 1


# --- adversarial round 19: /evaluate authenticates before running inference -------------


def test_http_evaluate_disabled_without_token_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No --evaluate-token configured at all: /evaluate must refuse
    immediately (403) WITHOUT ever invoking evaluate_batch — a tripwire on
    evaluate_batch itself, not just an assertion on the status code, so a
    regression that authenticates but still runs inference is caught."""
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**SMALL_MODEL))
    server = _Server(checkpoint, tmp_path / "manifest.json")  # evaluate_token defaults None

    def _tripwire(*args: object, **kwargs: object) -> None:
        raise AssertionError("evaluate_batch must not be invoked when /evaluate is disabled")

    monkeypatch.setattr(CheckpointPolicy, "evaluate_batch", _tripwire)

    try:
        status, data = server.request(
            "POST", "/evaluate", {"observations": [_observation_payload([0, 1, 2])]},
        )
    finally:
        server.close()

    assert status == 403
    assert "error" in data


def test_http_evaluate_wrong_bearer_token_rejected_no_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**SMALL_MODEL))
    server = _Server(checkpoint, tmp_path / "manifest.json", evaluate_token="eval-token")

    def _tripwire(*args: object, **kwargs: object) -> None:
        raise AssertionError("evaluate_batch must not be invoked with a wrong bearer token")

    monkeypatch.setattr(CheckpointPolicy, "evaluate_batch", _tripwire)

    try:
        status, data = server.request(
            "POST", "/evaluate",
            {"observations": [_observation_payload([0, 1, 2])]},
            headers=_bearer("wrong-token"),
        )
    finally:
        server.close()

    assert status == 403
    assert "error" in data


def test_http_evaluate_missing_bearer_header_rejected_no_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**SMALL_MODEL))
    server = _Server(checkpoint, tmp_path / "manifest.json", evaluate_token="eval-token")

    def _tripwire(*args: object, **kwargs: object) -> None:
        raise AssertionError("evaluate_batch must not be invoked without a bearer token")

    monkeypatch.setattr(CheckpointPolicy, "evaluate_batch", _tripwire)

    try:
        status, data = server.request(
            "POST", "/evaluate", {"observations": [_observation_payload([0, 1, 2])]},
        )
    finally:
        server.close()

    assert status == 403
    assert "error" in data


# --- /healthz --------------------------------------------------------------------------


def test_healthz_reads_single_consistent_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Adversarial round 6, Finding 2: do_GET must derive every /healthz field
    from ONE snapshot read, not two independent PolicyHolder property reads
    (holder.policy then holder.checkpoint_sha256). We simulate a /reload
    landing in between those two reads by making the `policy` property itself
    trigger a reload (as a side effect, mimicking a concurrent request) the
    first time it's accessed, then confirm the response never mixes the old
    checkpoint's identity with the new one's."""
    old_config = _event_model_config(window=8)
    new_config = _event_model_config(window=16)
    old_checkpoint = _save_checkpoint(tmp_path, old_config, step=1, name="old.pt")
    new_checkpoint = _save_checkpoint(tmp_path, new_config, step=2, name="new.pt")

    server = _Server(old_checkpoint, tmp_path / "manifest.json")
    holder = server.holder

    original_policy_getter = type(holder).policy.fget
    swapped = {"done": False}

    def racy_policy_getter(self: PolicyHolder) -> CheckpointPolicy:
        result = original_policy_getter(self)
        if not swapped["done"]:
            swapped["done"] = True
            # Simulate a concurrent /reload completing right after the
            # handler's first field read.
            self.reload(checkpoint=str(new_checkpoint), expected_event_window=16)
        return result

    monkeypatch.setattr(PolicyHolder, "policy", property(racy_policy_getter))

    try:
        status, data = server.request("GET", "/healthz")
    finally:
        server.close()

    assert status == 200, data
    old_sha = hashlib.sha256(old_checkpoint.read_bytes()).hexdigest()
    new_sha = hashlib.sha256(new_checkpoint.read_bytes()).hexdigest()

    if data["checkpoint_step"] == 1:
        assert data["checkpoint"] == str(old_checkpoint)
        assert data["checkpoint_sha256"] == old_sha
        assert data["event_window"] == 8
        assert data["model_config"]["event_window"] == 8
    else:
        assert data["checkpoint_step"] == 2
        assert data["checkpoint"] == str(new_checkpoint)
        assert data["checkpoint_sha256"] == new_sha
        assert data["event_window"] == 16
        assert data["model_config"]["event_window"] == 16


def test_healthz_carries_sha256_window_and_contract_version(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request("GET", "/healthz")
    finally:
        server.close()

    assert status == 200
    expected_sha = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    assert data["checkpoint_sha256"] == expected_sha
    assert data["event_window"] == 8
    assert data["contract_version"] == EVENT_CONTRACT_V1
    assert data["model_config"]["event_window"] == 8
    # Existing fields must still be present.
    assert data["ok"] is True
    assert data["checkpoint_step"] == 1


def test_act_response_includes_checkpoint_sha256(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        act_status, act_data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
                contract_version=EVENT_CONTRACT_V1,
            ),
        )
        healthz_status, healthz_data = server.request("GET", "/healthz")
    finally:
        server.close()

    assert act_status == 200, act_data
    expected_sha = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    assert act_data["checkpoint_sha256"] == expected_sha
    assert healthz_status == 200
    assert act_data["checkpoint_sha256"] == healthz_data["checkpoint_sha256"]
    # Existing fields must still be present.
    assert act_data["checkpoint_step"] == 1


# --- /reload validation ------------------------------------------------------------------


def test_policy_holder_reload_rejects_incompatible_event_window(tmp_path: Path) -> None:
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=16), step=2, name="new.pt")
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(old), manifest_path=tmp_path / "manifest.json")

    with pytest.raises(ValueError):
        holder.reload(checkpoint=str(new))

    assert holder.policy.checkpoint_step == 1
    assert holder.policy.checkpoint_path == old


def test_policy_holder_reload_allows_override_via_expected_event_window(tmp_path: Path) -> None:
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=16), step=2, name="new.pt")
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(old), manifest_path=tmp_path / "manifest.json")

    holder.reload(checkpoint=str(new), expected_event_window=16)

    assert holder.policy.checkpoint_step == 2
    assert holder.policy.checkpoint_path == new


def test_http_reload_incompatible_window_leaves_old_policy_serving(tmp_path: Path) -> None:
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=16), step=2, name="new.pt")
    server = _Server(old, tmp_path / "manifest.json", admin_token="op-token")
    try:
        reload_status, reload_data = server.request(
            "POST", "/reload", {"checkpoint": str(new)}, headers=_bearer("op-token"),
        )
        act_status, act_data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
                contract_version=EVENT_CONTRACT_V1,
            ),
        )
    finally:
        server.close()

    assert reload_status == 400
    assert "error" in reload_data
    assert act_status == 200, act_data
    assert act_data["checkpoint_step"] == 1


def test_policy_holder_reload_failure_after_load_leaves_policy_and_hash_consistent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adversarial round 3, Finding 1 (re-scoped for round 5's Finding 2 fix):
    if ANYTHING fails after the new checkpoint's policy+hash have already been
    produced but before they are swapped in, the reload must fail WITHOUT
    having swapped in the new policy — /act and /healthz must both keep
    observing the OLD policy and the OLD hash together, never a new policy
    paired with a stale hash or vice versa.

    Since round 5's Finding 2 fix, policy and hash are derived together from a
    single read of the checkpoint bytes; since round 14's Finding 1b fix, the
    `checkpoint=` (path) branch reads bytes, hashes them, and only then builds
    the policy via `CheckpointPolicy.from_checkpoint_bytes` — so the old
    "hash the path a second time and make THAT call fail" seam
    (`PolicyHolder._sha256_of`) no longer sits on `reload`'s hot path at all.
    This exercises the equivalent seam instead: `from_checkpoint_bytes`
    succeeds (producing a real new policy, mirroring "the new checkpoint was
    fully loaded and hashed"), then something else fails before the snapshot
    swap — the holder must still show only the OLD snapshot."""
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=8), step=2, name="new.pt")
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(old), manifest_path=tmp_path / "manifest.json")
    old_policy = holder.policy
    old_sha256 = holder.checkpoint_sha256

    real_from_checkpoint_bytes = CheckpointPolicy.from_checkpoint_bytes

    def _flaky_from_checkpoint_bytes(*args: object, **kwargs: object):
        # Fully deserialize the new checkpoint (the real path succeeds
        # normally) — then fail afterward, before `reload` gets a chance to
        # swap the snapshot.
        real_from_checkpoint_bytes(*args, **kwargs)
        raise OSError("simulated failure after policy+hash were produced, before the snapshot swap")

    monkeypatch.setattr(CheckpointPolicy, "from_checkpoint_bytes", _flaky_from_checkpoint_bytes)

    with pytest.raises(OSError):
        holder.reload(checkpoint=str(new))

    assert holder.policy is old_policy
    assert holder.policy.checkpoint_step == 1
    assert holder.checkpoint_sha256 == old_sha256


def test_policy_holder_reload_success_updates_policy_and_hash_together(tmp_path: Path) -> None:
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=8), step=2, name="new.pt")
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(old), manifest_path=tmp_path / "manifest.json")

    holder.reload(checkpoint=str(new))

    assert holder.policy.checkpoint_step == 2
    assert holder.policy.checkpoint_path == new
    assert holder.checkpoint_sha256 == hashlib.sha256(new.read_bytes()).hexdigest()


# --- adversarial round 14, Finding 1a: /reload admin-token authentication ---------------


def test_http_reload_disabled_when_no_admin_token_configured(tmp_path: Path) -> None:
    """No --admin-token configured on the server at all (adversarial round
    14, Finding 1a): POST /reload must be refused entirely, never silently
    accepted, even when the request itself carries no admin_token field."""
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=8), step=2, name="new.pt")
    server = _Server(old, tmp_path / "manifest.json")  # admin_token defaults None
    try:
        status, data = server.request("POST", "/reload", {"checkpoint": str(new)})
        healthz_status, healthz_data = server.request("GET", "/healthz")
    finally:
        server.close()

    assert status in (400, 403)
    assert "error" in data
    assert healthz_status == 200
    assert healthz_data["checkpoint_step"] == 1


def test_http_reload_missing_admin_token_rejected_policy_unchanged(tmp_path: Path) -> None:
    """A server DOES have an admin token configured, but the request omits
    'admin_token' entirely — must be rejected exactly like a wrong token, not
    treated as an implicit disable."""
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=8), step=2, name="new.pt")
    server = _Server(old, tmp_path / "manifest.json", admin_token="op-token")
    try:
        status, data = server.request("POST", "/reload", {"checkpoint": str(new)})
        act_status, act_data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
                contract_version=EVENT_CONTRACT_V1,
            ),
        )
    finally:
        server.close()

    assert status in (400, 403)
    assert "error" in data
    assert act_status == 200, act_data
    assert act_data["checkpoint_step"] == 1


def test_http_reload_wrong_admin_token_rejected_policy_unchanged(tmp_path: Path) -> None:
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=8), step=2, name="new.pt")
    server = _Server(old, tmp_path / "manifest.json", admin_token="op-token")
    try:
        status, data = server.request(
            "POST", "/reload", {"checkpoint": str(new)}, headers=_bearer("wrong-token"),
        )
        act_status, act_data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
                contract_version=EVENT_CONTRACT_V1,
            ),
        )
    finally:
        server.close()

    assert status in (400, 403)
    assert "error" in data
    assert act_status == 200, act_data
    assert act_data["checkpoint_step"] == 1


def test_http_reload_correct_admin_token_swaps_policy(tmp_path: Path) -> None:
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=8), step=2, name="new.pt")
    server = _Server(old, tmp_path / "manifest.json", admin_token="op-token")
    try:
        status, data = server.request(
            "POST", "/reload", {"checkpoint": str(new)}, headers=_bearer("op-token"),
        )
    finally:
        server.close()

    assert status == 200, data
    assert data["ok"] is True
    assert data["checkpoint_step"] == 2


# --- adversarial round 14, Finding 1b: /reload checkpoint path safety -------------------


def test_http_reload_rejects_directory_path(tmp_path: Path) -> None:
    """A directory is not a regular file — must be rejected by the os.stat
    check before anything attempts to read it, and the old policy must keep
    serving."""
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    a_directory = tmp_path / "not_a_file"
    a_directory.mkdir()
    server = _Server(old, tmp_path / "manifest.json", admin_token="op-token")
    try:
        status, data = server.request(
            "POST", "/reload", {"checkpoint": str(a_directory)}, headers=_bearer("op-token"),
        )
        act_status, act_data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
                contract_version=EVENT_CONTRACT_V1,
            ),
        )
    finally:
        server.close()

    assert status == 400
    assert "regular file" in data["error"]
    assert act_status == 200, act_data
    assert act_data["checkpoint_step"] == 1


def test_http_reload_rejects_fifo_path(tmp_path: Path) -> None:
    """A FIFO has no meaningful size and would block on read — must be
    rejected by the S_ISREG check without ever calling read_bytes() on it."""
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    fifo_path = tmp_path / "a.fifo"
    os.mkfifo(fifo_path)
    server = _Server(old, tmp_path / "manifest.json", admin_token="op-token")
    try:
        status, data = server.request(
            "POST", "/reload", {"checkpoint": str(fifo_path)}, headers=_bearer("op-token"),
        )
    finally:
        server.close()

    assert status == 400
    assert "regular file" in data["error"]


def test_policy_holder_reload_rejects_oversize_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A regular file that exceeds the reload size cap must be rejected
    before any bytes are read from it."""
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    huge = tmp_path / "huge.pt"
    huge.write_bytes(b"\x00" * 16)

    import fh_mahjong_ai.scripts.serve_policy as serve_policy_module

    monkeypatch.setattr(serve_policy_module, "MAX_RELOAD_CHECKPOINT_BYTES", 8)
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(old), manifest_path=tmp_path / "manifest.json")

    with pytest.raises(ValueError, match="exceeding"):
        holder.reload(checkpoint=str(huge))

    assert holder.policy.checkpoint_step == 1


def test_http_reload_rejects_oversize_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    huge = tmp_path / "huge.pt"
    huge.write_bytes(b"\x00" * 16)

    import fh_mahjong_ai.scripts.serve_policy as serve_policy_module

    monkeypatch.setattr(serve_policy_module, "MAX_RELOAD_CHECKPOINT_BYTES", 8)
    server = _Server(old, tmp_path / "manifest.json", admin_token="op-token")
    try:
        status, data = server.request(
            "POST", "/reload", {"checkpoint": str(huge)}, headers=_bearer("op-token"),
        )
    finally:
        server.close()

    assert status == 400
    assert "exceeding" in data["error"]


# --- adversarial round 14, Finding 1b: /reload expected_sha256 verification -------------


def test_policy_holder_reload_rejects_expected_sha256_mismatch(tmp_path: Path) -> None:
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=8), step=2, name="new.pt")
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(old), manifest_path=tmp_path / "manifest.json")

    with pytest.raises(ValueError, match="expected_sha256"):
        holder.reload(checkpoint=str(new), expected_sha256="0" * 64)

    assert holder.policy.checkpoint_step == 1


def test_policy_holder_reload_accepts_matching_expected_sha256(tmp_path: Path) -> None:
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=8), step=2, name="new.pt")
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(old), manifest_path=tmp_path / "manifest.json")
    new_sha256 = hashlib.sha256(new.read_bytes()).hexdigest()

    holder.reload(checkpoint=str(new), expected_sha256=new_sha256)

    assert holder.policy.checkpoint_step == 2


def test_http_reload_rejects_expected_sha256_mismatch(tmp_path: Path) -> None:
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=8), step=2, name="new.pt")
    server = _Server(old, tmp_path / "manifest.json", admin_token="op-token")
    try:
        status, data = server.request(
            "POST", "/reload",
            {"checkpoint": str(new), "expected_sha256": "0" * 64},
            headers=_bearer("op-token"),
        )
        act_status, act_data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
                contract_version=EVENT_CONTRACT_V1,
            ),
        )
    finally:
        server.close()

    assert status == 400
    assert "expected_sha256" in data["error"]
    assert act_status == 200, act_data
    assert act_data["checkpoint_step"] == 1


# --- adversarial round 12/13, Finding 1: /act logit export gating ---------------------


def test_http_act_return_logits_no_token_configured_gets_400(tmp_path: Path) -> None:
    """No --logit-export-token configured on the server at all (adversarial
    round 12/13, Finding 1): a request with return_logits=true must get a
    loud HTTP 400, never a silent no-op — the parity harness's --endpoint
    hard gate must fail clearly rather than comparing nothing when
    misconfigured."""
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json")  # logit_export_token defaults None
    try:
        status, data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
                contract_version=EVENT_CONTRACT_V1, return_logits=True,
            ),
        )
    finally:
        server.close()

    assert status == 400
    assert "logit export" in data["error"]
    assert "logits" not in data


def test_http_act_return_logits_correct_token_returns_logits(tmp_path: Path) -> None:
    """Adversarial round 13, Finding 1: a shared-secret token replaces the
    old process-wide --enable-logit-export boolean. A request that carries
    the SAME token the server was configured with gets logits back."""
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json", logit_export_token="s3cr3t-token")
    try:
        status, data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
                contract_version=EVENT_CONTRACT_V1, return_logits=True,
                logit_export_token="s3cr3t-token",
            ),
        )
    finally:
        server.close()

    assert status == 200, data
    assert "logits" in data
    assert isinstance(data["logits"], list)


def test_http_act_return_logits_wrong_token_rejected_no_logits(tmp_path: Path) -> None:
    """Adversarial round 13, Finding 1: a token IS configured on the server,
    but the request carries the wrong one — this must be rejected (no
    unauthenticated-once-flag-is-on mode), and the response must not leak
    logits."""
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json", logit_export_token="s3cr3t-token")
    try:
        status, data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
                contract_version=EVENT_CONTRACT_V1, return_logits=True,
                logit_export_token="wrong-token",
            ),
        )
    finally:
        server.close()

    assert status == 400
    assert "logits" not in data


def test_http_act_return_logits_missing_token_rejected_no_logits(tmp_path: Path) -> None:
    """Adversarial round 13, Finding 1: a token IS configured on the server,
    but the request omits 'logit_export_token' entirely — this is the exact
    "any network caller" scenario the finding calls out, and must be
    rejected just like a wrong token, not treated as an implicit disable."""
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json", logit_export_token="s3cr3t-token")
    try:
        status, data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
                contract_version=EVENT_CONTRACT_V1, return_logits=True,
            ),
        )
    finally:
        server.close()

    assert status == 400
    assert "logits" not in data


def test_http_act_without_return_logits_unaffected_by_export_token(tmp_path: Path) -> None:
    """A normal /act request (no return_logits) must succeed regardless of
    whether the server has a --logit-export-token configured — the gate
    only applies to requests that actually ask for logits."""
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json")  # no token configured
    try:
        status, data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
                contract_version=EVENT_CONTRACT_V1,
            ),
        )
    finally:
        server.close()

    assert status == 200, data
    assert "logits" not in data


# --- adversarial round 15, Finding 1: /reload authenticates before reading the body -----


class _TripwireRFile:
    """A stand-in for `rfile` that records whether `.read()` was ever
    called, instead of raising — a raise would be silently swallowed by
    `_handle_reload`'s broad `except Exception`, defeating the point (see
    the docstring on `_handle_reload`'s ordering)."""

    def __init__(self) -> None:
        self.was_read = False

    def read(self, *args: object, **kwargs: object) -> bytes:
        self.was_read = True
        return b""


class _CaseInsensitiveHeaders(dict):
    def get(self, key, default=None):  # type: ignore[override]
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


class _FakeReloadHandler:
    """Enough of a `PolicyRequestHandler` stand-in to call `_handle_reload`
    directly — no real socket/HTTP server involved — so tests can assert
    on `rfile.was_read` deterministically instead of racing a timeout."""

    def __init__(self, headers: dict, holder: PolicyHolder) -> None:
        self.headers = _CaseInsensitiveHeaders(headers)
        self.holder = holder
        self.rfile = _TripwireRFile()
        self.responses: list[tuple[int, dict]] = []

    def _write_json(self, payload: dict, status: int = 200) -> None:
        self.responses.append((status, payload))


def _reload_holder(tmp_path: Path, admin_token: str | None) -> PolicyHolder:
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    return PolicyHolder(
        CheckpointPolicy.from_checkpoint(checkpoint),
        manifest_path=tmp_path / "manifest.json",
        admin_token=admin_token,
    )


def test_reload_no_admin_token_configured_rejected_without_reading_body(tmp_path: Path) -> None:
    """No --admin-token configured at all: /reload must refuse immediately,
    BEFORE even looking at Content-Length or any header — a caller could
    supply neither and it must still never read the body."""
    holder = _reload_holder(tmp_path, admin_token=None)
    fake = _FakeReloadHandler(headers={}, holder=holder)

    PolicyRequestHandler._handle_reload(fake)

    assert fake.rfile.was_read is False
    status, data = fake.responses[0]
    assert status == 403
    assert "error" in data
    assert holder.policy.checkpoint_step == 1


def test_reload_oversized_content_length_rejected_without_reading_body(tmp_path: Path) -> None:
    """A Content-Length far beyond the tiny reload cap must be rejected
    before a single body byte is read, even when the caller's bearer token
    is otherwise correct — this is the DoS surface Finding 1 closes."""
    holder = _reload_holder(tmp_path, admin_token="op-token")
    fake = _FakeReloadHandler(
        headers={"Authorization": "Bearer op-token", "content-length": str(10 * 1024 * 1024)},
        holder=holder,
    )

    PolicyRequestHandler._handle_reload(fake)

    assert fake.rfile.was_read is False
    status, data = fake.responses[0]
    assert status == 400
    assert "error" in data
    assert holder.policy.checkpoint_step == 1


def test_reload_missing_content_length_rejected_without_reading_body(tmp_path: Path) -> None:
    holder = _reload_holder(tmp_path, admin_token="op-token")
    fake = _FakeReloadHandler(headers={"Authorization": "Bearer op-token"}, holder=holder)

    PolicyRequestHandler._handle_reload(fake)

    assert fake.rfile.was_read is False
    status, data = fake.responses[0]
    assert status == 400
    assert "error" in data


def test_reload_missing_bearer_header_rejected_without_reading_body(tmp_path: Path) -> None:
    holder = _reload_holder(tmp_path, admin_token="op-token")
    fake = _FakeReloadHandler(headers={"content-length": "2"}, holder=holder)

    PolicyRequestHandler._handle_reload(fake)

    assert fake.rfile.was_read is False
    status, data = fake.responses[0]
    assert status == 403
    assert "error" in data
    assert holder.policy.checkpoint_step == 1


def test_reload_wrong_bearer_token_rejected_without_reading_body(tmp_path: Path) -> None:
    holder = _reload_holder(tmp_path, admin_token="op-token")
    fake = _FakeReloadHandler(
        headers={"Authorization": "Bearer wrong-token", "content-length": "2"}, holder=holder,
    )

    PolicyRequestHandler._handle_reload(fake)

    assert fake.rfile.was_read is False
    status, data = fake.responses[0]
    assert status == 403
    assert "error" in data
    assert holder.policy.checkpoint_step == 1


def test_http_reload_correct_bearer_token_and_valid_size_swaps_policy(tmp_path: Path) -> None:
    """End-to-end (real HTTP): the correct 'Authorization: Bearer <token>'
    header plus a small body succeeds — the positive-path counterpart to
    the tripwire tests above."""
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=8), step=2, name="new.pt")
    server = _Server(old, tmp_path / "manifest.json", admin_token="op-token")
    try:
        status, data = server.request(
            "POST", "/reload", {"checkpoint": str(new)}, headers=_bearer("op-token"),
        )
    finally:
        server.close()

    assert status == 200, data
    assert data["ok"] is True
    assert data["checkpoint_step"] == 2


def test_http_act_rejects_oversized_content_length(tmp_path: Path) -> None:
    """/act is unauthenticated by design but still caps Content-Length
    (adversarial round 15, Finding 1) — a generous cap, but not infinite."""
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        import fh_mahjong_ai.scripts.serve_policy as serve_policy_module

        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        conn.putrequest("POST", "/act")
        conn.putheader("Content-Length", str(serve_policy_module.MAX_ACT_REQUEST_BYTES + 1))
        conn.endheaders()
        response = conn.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        status = response.status
        conn.close()
    finally:
        server.close()

    assert status == 400
    assert "error" in data


def test_http_evaluate_rejects_oversized_content_length(tmp_path: Path) -> None:
    """A correct bearer token does not exempt the request from the
    Content-Length cap — mirrors /reload's oversized-Content-Length test."""
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json", evaluate_token="eval-token")
    try:
        import fh_mahjong_ai.scripts.serve_policy as serve_policy_module

        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        conn.putrequest("POST", "/evaluate")
        conn.putheader("Content-Length", str(serve_policy_module.MAX_EVALUATE_REQUEST_BYTES + 1))
        conn.putheader("Authorization", "Bearer eval-token")
        conn.endheaders()
        response = conn.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        status = response.status
        conn.close()
    finally:
        server.close()

    assert status == 400
    assert "error" in data


# --- adversarial round 15, Finding 2: /reload verifies expected_sha256 before deserializing --


def _manifest_with_checkpoint(tmp_path: Path, checkpoint_path: Path, manifest_name: str = "manifest.json") -> Path:
    manifest_path = tmp_path / manifest_name
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "current_reward_trained_best": {
                    "id": "current",
                    "method": "test",
                    "checkpoint_path": str(checkpoint_path),
                },
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def test_policy_holder_reload_checkpoint_id_rejects_mismatch_before_deserializing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Adversarial round 15, Finding 2: the checkpoint_id/manifest-resolved
    reload branch must verify expected_sha256 BEFORE calling
    CheckpointPolicy.from_checkpoint_bytes (torch.load) at all — a mismatch
    must never reach the deserializer, not just fail to swap in afterward.
    Pinned with a tripwire that counts calls to from_checkpoint_bytes."""
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=8), step=2, name="new.pt")
    manifest_path = _manifest_with_checkpoint(tmp_path, new)
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(old), manifest_path=manifest_path)

    calls = {"n": 0}
    real_from_checkpoint_bytes = CheckpointPolicy.from_checkpoint_bytes

    def _counting_from_checkpoint_bytes(*args: object, **kwargs: object):
        calls["n"] += 1
        return real_from_checkpoint_bytes(*args, **kwargs)

    monkeypatch.setattr(CheckpointPolicy, "from_checkpoint_bytes", _counting_from_checkpoint_bytes)

    with pytest.raises(ValueError, match="expected_sha256"):
        holder.reload(checkpoint_id="current", expected_sha256="0" * 64)

    assert calls["n"] == 0
    assert holder.policy.checkpoint_step == 1


def test_policy_holder_reload_checkpoint_id_accepts_matching_expected_sha256(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=8), step=2, name="new.pt")
    manifest_path = _manifest_with_checkpoint(tmp_path, new)
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(old), manifest_path=manifest_path)
    new_sha256 = hashlib.sha256(new.read_bytes()).hexdigest()

    calls = {"n": 0}
    real_from_checkpoint_bytes = CheckpointPolicy.from_checkpoint_bytes

    def _counting_from_checkpoint_bytes(*args: object, **kwargs: object):
        calls["n"] += 1
        return real_from_checkpoint_bytes(*args, **kwargs)

    monkeypatch.setattr(CheckpointPolicy, "from_checkpoint_bytes", _counting_from_checkpoint_bytes)

    holder.reload(checkpoint_id="current", expected_sha256=new_sha256)

    assert calls["n"] == 1
    assert holder.policy.checkpoint_step == 2


# --- adversarial round 20, Finding 1: reload rejects unbounded/mismatched metadata -------


def test_policy_holder_reload_rejects_oversized_metadata_channels_keeps_old_policy(
    tmp_path: Path,
) -> None:
    """Round 20, Finding 1: a checkpoint whose metadata claims an oversized
    `channels` must be rejected during reload, and the previously serving
    policy must remain active -- not just fail to swap after the process
    already stalled/OOM'd trying to build the huge net."""
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    bad = tmp_path / "bad.pt"
    bad_model = PolicyValueNet(_ENV, _event_model_config(window=8))
    bad_metadata = {
        "model_config": {**model_config_metadata(_event_model_config(window=8)), "channels": 10**6},
    }
    save_checkpoint(bad, bad_model, step=2, metadata=bad_metadata)
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(old), manifest_path=tmp_path / "manifest.json")

    with pytest.raises(ValueError, match="channels"):
        holder.reload(checkpoint=str(bad))

    assert holder.policy.checkpoint_step == 1


# --- adversarial round 20, Finding 2: checkpoint_id reload shares file safety checks -----


def test_http_reload_checkpoint_id_rejects_fifo_manifest_target(tmp_path: Path) -> None:
    """A manifest entry pointing at a FIFO must be rejected the same way the
    `checkpoint` (explicit path) branch already rejects one -- previously
    only that branch ran the regular-file + size-cap checks before reading;
    the checkpoint_id/manifest-resolved branch called path.read_bytes()
    directly, so a manifest entry pointing at a FIFO would hang the worker."""
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    fifo_path = tmp_path / "a.fifo"
    os.mkfifo(fifo_path)
    manifest_path = _manifest_with_checkpoint(tmp_path, fifo_path)
    server = _Server(old, manifest_path, admin_token="op-token")
    try:
        status, data = server.request(
            "POST", "/reload", {"checkpoint_id": "current"}, headers=_bearer("op-token"),
        )
    finally:
        server.close()

    assert status == 400
    assert "regular file" in data["error"]


def test_policy_holder_reload_checkpoint_id_rejects_oversize_manifest_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A manifest entry pointing at an oversized regular file must be
    rejected before any bytes are read from it, exactly like the explicit
    `checkpoint` path branch."""
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    huge = tmp_path / "huge.pt"
    huge.write_bytes(b"\x00" * 16)
    manifest_path = _manifest_with_checkpoint(tmp_path, huge)

    import fh_mahjong_ai.scripts.serve_policy as serve_policy_module

    monkeypatch.setattr(serve_policy_module, "MAX_RELOAD_CHECKPOINT_BYTES", 8)
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(old), manifest_path=manifest_path)

    with pytest.raises(ValueError, match="exceeding"):
        holder.reload(checkpoint_id="current")

    assert holder.policy.checkpoint_step == 1


def test_policy_holder_reload_checkpoint_id_happy_path_still_works(tmp_path: Path) -> None:
    """The checkpoint_id reload path must keep working for a normal,
    well-formed manifest-resolved checkpoint after the fd-based fstat+read
    unification."""
    old = _save_checkpoint(tmp_path, _event_model_config(window=8), step=1, name="old.pt")
    new = _save_checkpoint(tmp_path, _event_model_config(window=8), step=2, name="new.pt")
    manifest_path = _manifest_with_checkpoint(tmp_path, new)
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(old), manifest_path=manifest_path)

    holder.reload(checkpoint_id="current")

    assert holder.policy.checkpoint_step == 2


# --- adversarial round 15, Finding 4: privileged-critic values are never published -------


def _privileged_event_model_config(window: int = 8) -> ModelConfig:
    return ModelConfig(**dict(SMALL_MODEL, event_window=window, privileged_critic=True, aux_heads=True))


def test_http_act_privileged_critic_checkpoint_nulls_value(tmp_path: Path) -> None:
    """A privileged-critic checkpoint's value head is out-of-distribution
    against serving's public-only planes — /act must null the value out and
    flag it, never publish a misleading number. Action selection is
    unaffected."""
    checkpoint = _save_checkpoint(tmp_path, _privileged_event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
                contract_version=EVENT_CONTRACT_V1,
            ),
        )
    finally:
        server.close()

    assert status == 200, data
    assert data["action_id"] in (0, 1, 2)
    assert data["value"] is None
    assert data["value_calibrated"] is False


def test_http_act_non_privileged_checkpoint_keeps_value(tmp_path: Path) -> None:
    """Window-0 (or any non-privileged-critic) checkpoint: unchanged
    behavior — a real float value, flagged calibrated."""
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))  # privileged_critic=False
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request(
            "POST", "/act",
            _observation_payload(
                [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
                contract_version=EVENT_CONTRACT_V1,
            ),
        )
    finally:
        server.close()

    assert status == 200, data
    assert isinstance(data["value"], float)
    assert data["value_calibrated"] is True


def test_http_evaluate_privileged_critic_checkpoint_nulls_values_and_flags_response(
    tmp_path: Path,
) -> None:
    checkpoint = _save_checkpoint(tmp_path, _privileged_event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json", evaluate_token="eval-token")
    try:
        status, data = server.request(
            "POST", "/evaluate",
            {
                "observations": [
                    _observation_payload(
                        [0, 1, 2], event_history=[1, 2, 3], event_count=3, event_window=8,
                        contract_version=EVENT_CONTRACT_V1,
                    )
                ]
            },
            headers=_bearer("eval-token"),
        )
    finally:
        server.close()

    assert status == 200, data
    assert data["values_calibrated"] is False
    assert len(data["results"]) == 1
    assert data["results"][0]["value"] is None
    # Probs (action ranking) are unaffected by the calibration flag.
    assert len(data["results"][0]["probs"]) == EnvConfig().action_space_size


def test_http_evaluate_non_privileged_checkpoint_keeps_values(tmp_path: Path) -> None:
    """Window-0 old-champion-style checkpoint: values unchanged, flag true."""
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**SMALL_MODEL))  # event_window=0, privileged_critic=False
    server = _Server(checkpoint, tmp_path / "manifest.json", evaluate_token="eval-token")
    try:
        status, data = server.request(
            "POST", "/evaluate",
            {"observations": [_observation_payload([0, 1, 2])]},
            headers=_bearer("eval-token"),
        )
    finally:
        server.close()

    assert status == 200, data
    assert data["values_calibrated"] is True
    assert isinstance(data["results"][0]["value"], float)


# --- POST /warmup ------------------------------------------------------------------------
# Part 1 of the policy-warmup feature: a dedicated endpoint that performs a
# genuine forward pass so the Go backend can eliminate serve_policy's
# post-idle cold start BEFORE admitting an RL room. Part 2 (the Go-side
# warmup manager that calls this) is separate.


def test_http_warmup_returns_200_with_all_fields_matching_healthz(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**SMALL_MODEL))  # event_window=0
    server = _Server(checkpoint, tmp_path / "manifest.json")  # no evaluate token -> warmup open
    try:
        status, data = server.request("POST", "/warmup", {})
        healthz_status, healthz_data = server.request("GET", "/healthz")
    finally:
        server.close()

    assert status == 200, data
    assert data["warmed"] is True
    assert data["checkpoint_path"] == healthz_data["checkpoint"]
    assert data["checkpoint_step"] == healthz_data["checkpoint_step"]
    assert data["checkpoint_sha256"] == healthz_data["checkpoint_sha256"]
    assert data["contract_version"] == healthz_data["contract_version"]
    assert data["event_window"] == healthz_data["event_window"] == 0
    assert isinstance(data["latency_ms"], float)
    assert data["latency_ms"] > 0


def test_http_warmup_accepts_empty_body(tmp_path: Path) -> None:
    """POST /warmup with no body at all (not even '{}') must still work —
    its content is always ignored."""
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**SMALL_MODEL))
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request("POST", "/warmup", None)
    finally:
        server.close()

    assert status == 200, data
    assert data["warmed"] is True


def test_http_warmup_disabled_token_no_header_rejected(tmp_path: Path) -> None:
    """When an evaluate token IS configured, /warmup piggybacks on it —
    mirroring /evaluate's 403 status for a missing bearer header."""
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**SMALL_MODEL))
    server = _Server(checkpoint, tmp_path / "manifest.json", evaluate_token="eval-token")
    try:
        status, data = server.request("POST", "/warmup", {})
    finally:
        server.close()

    assert status == 403
    assert "error" in data


def test_http_warmup_wrong_token_rejected(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**SMALL_MODEL))
    server = _Server(checkpoint, tmp_path / "manifest.json", evaluate_token="eval-token")
    try:
        status, data = server.request(
            "POST", "/warmup", {}, headers=_bearer("wrong-token"),
        )
    finally:
        server.close()

    assert status == 403
    assert "error" in data


def test_http_warmup_correct_token_succeeds(tmp_path: Path) -> None:
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**SMALL_MODEL))
    server = _Server(checkpoint, tmp_path / "manifest.json", evaluate_token="eval-token")
    try:
        status, data = server.request(
            "POST", "/warmup", {}, headers=_bearer("eval-token"),
        )
    finally:
        server.close()

    assert status == 200, data
    assert data["warmed"] is True


def test_http_warmup_open_when_no_token_configured(tmp_path: Path) -> None:
    """No --evaluate-token configured at all: /warmup must stay open and
    unauthenticated — the primary production instance runs tokenless, and
    warmup exists precisely to serve it."""
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**SMALL_MODEL))
    server = _Server(checkpoint, tmp_path / "manifest.json")  # evaluate_token defaults None
    try:
        status, data = server.request("POST", "/warmup", {})
    finally:
        server.close()

    assert status == 200, data
    assert data["warmed"] is True


def test_http_warmup_does_not_advance_the_sampling_rng(tmp_path: Path) -> None:
    """/warmup's action is thrown away, so it must NOT consume draws from the
    sampling RNG: otherwise a warmed server would play a DIFFERENT game than
    an unwarmed one (and every restart-plus-warm would resample), turning an
    observability feature into a behavioural change. The warmup forward pass
    therefore takes the greedy path (`choose(..., force_greedy=True)`).

    Pinned end to end: the sampled /act sequence after two /warmup calls must
    be byte-identical to the same sequence with no warmup at all."""
    checkpoint = _save_checkpoint(tmp_path, ModelConfig(**SMALL_MODEL))

    def sampled_sequence(warmups: int) -> tuple[list[int], tuple]:
        policy = CheckpointPolicy.from_checkpoint(
            checkpoint, sample_temperature=1.0, seed=20260812,
        )
        server = _Server(checkpoint, tmp_path / "manifest.json", policy=policy)
        try:
            for _ in range(warmups):
                status, data = server.request("POST", "/warmup", {})
                assert status == 200, data
            actions = []
            for _ in range(12):
                status, data = server.request(
                    "POST", "/act", _observation_payload([0, 1, 2, 3, 4]),
                )
                assert status == 200, data
                actions.append(data["action_id"])
        finally:
            server.close()
        return actions, policy._rng.bit_generator.state["state"]["state"]

    warmed_actions, warmed_rng = sampled_sequence(warmups=2)
    cold_actions, cold_rng = sampled_sequence(warmups=0)

    assert warmed_actions == cold_actions, "warmup shifted the sampling stream"
    assert warmed_rng == cold_rng, "warmup consumed RNG draws"
    # Guard the guard: the policy really is sampling, so the equality above is
    # a statement about the RNG, not about a degenerate all-greedy run.
    assert len(set(warmed_actions)) > 1, "sampling policy produced a constant action"


def test_http_warmup_event_window_checkpoint_succeeds(tmp_path: Path) -> None:
    """An event model (event_window > 0) must also get a genuine forward
    pass, exercising the event encoder path, not just window-0 models."""
    checkpoint = _save_checkpoint(tmp_path, _event_model_config(window=8))
    server = _Server(checkpoint, tmp_path / "manifest.json")
    try:
        status, data = server.request("POST", "/warmup", {})
    finally:
        server.close()

    assert status == 200, data
    assert data["warmed"] is True
    assert data["event_window"] == 8
