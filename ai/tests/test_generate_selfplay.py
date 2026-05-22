from __future__ import annotations

import json
from pathlib import Path

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.generate_selfplay import (
    generate_mixed_selfplay_dataset,
    parse_seat_policy,
    resolve_seat_policies,
)
from fh_mahjong_ai.storage import read_transition_arrays, read_transitions, save_checkpoint


def test_parse_seat_policy_checkpoint() -> None:
    spec = parse_seat_policy("2=checkpoint:/tmp/policy.pt")

    assert spec.seat == 2
    assert spec.kind == "checkpoint"
    assert spec.checkpoint_path == Path("/tmp/policy.pt")


def test_resolve_seat_policies_uses_checkpoint_convenience(tmp_path: Path) -> None:
    checkpoint = tmp_path / "model.pt"
    save_checkpoint(checkpoint, PolicyValueNet(EnvConfig(), ModelConfig()), step=3)

    specs = resolve_seat_policies([], checkpoint=checkpoint, checkpoint_seat=1)

    assert [spec.kind for spec in specs] == ["heuristic", "checkpoint", "heuristic", "heuristic"]
    assert specs[1].checkpoint_path == checkpoint
    assert [spec.source_id for spec in specs] == [0, 1, 2, 3]


def test_generate_mixed_selfplay_mock_npz(tmp_path: Path) -> None:
    output = tmp_path / "selfplay-npz"
    specs = resolve_seat_policies(
        ["0=random", "1=random", "2=random", "3=random"],
        bridge_kind="mock",
    )

    stats = generate_mixed_selfplay_dataset(
        episodes=2,
        start_seed=40,
        output_path=output,
        seat_policies=specs,
        bridge_kind="mock",
        chunk_size=1,
        output_format="npz_shards",
        shard_size=3,
        max_steps_per_episode=4,
    )

    transitions = read_transitions(output)
    arrays = read_transition_arrays(output, keys=("policy_source_ids", "policy_values"))
    manifest_payload = json.loads((tmp_path / "selfplay-npz.manifest.json").read_text())

    assert stats["episodes"] == 2
    assert stats["transitions"] == len(transitions)
    assert stats["transitions"] > 0
    assert set(arrays["policy_source_ids"].tolist()).issubset({0, 1, 2, 3})
    assert arrays["policy_values"].shape[0] == stats["transitions"]
    assert all("policy_source_id" in transition.info for transition in transitions)
    assert manifest_payload["source"]["policy"] == "mixed_selfplay"
    assert manifest_payload["environment"]["learning_seats"] == [0, 1, 2, 3]
    assert [policy["kind"] for policy in manifest_payload["seat_policies"]] == ["random", "random", "random", "random"]
