"""The checkpoints the production policy services serve (`deployed_ai_agents`)."""

import hashlib
import json
from pathlib import Path

import pytest

from fh_mahjong_ai.checkpoint_manifest import load_checkpoint_manifest
from fh_mahjong_ai.serving import CheckpointPolicy

AI = Path(__file__).resolve().parents[1]
MANIFEST = AI / "checkpoints" / "best-checkpoints.json"
AGENTS = json.loads(MANIFEST.read_text())["deployed_ai_agents"]


def test_manifest_still_loads():
    load_checkpoint_manifest(MANIFEST)


def test_agent_ids_and_order():
    assert [a["id"] for a in AGENTS] == ["v4", "v3", "v2", "v1"]
    assert [a["label"] for a in AGENTS] == ["AI v4", "AI v3", "AI v2", "AI v1"]


def test_deploy_dir_holds_exactly_the_agents():
    deploy = AI / "checkpoints" / "deploy"
    assert sorted(p.name for p in deploy.glob("*.pt")) == sorted(Path(a["checkpoint_path"]).name for a in AGENTS)


@pytest.mark.parametrize("agent", AGENTS, ids=lambda a: a["id"])
def test_deployed_checkpoint_matches_record_and_loads(agent):
    path = AI / agent["checkpoint_path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == agent["sha256"]
    assert path.name.endswith(agent["sha256"][:8] + ".pt")
    policy = CheckpointPolicy.from_checkpoint(path, device="cpu", symmetry=agent["symmetry"])
    config = policy.model.model_config
    assert config.event_window == agent["event_window"] == 128
    assert config.lookahead_version == 0


def test_dockerfile_default_serves_the_default_agent():
    text = (AI / "Dockerfile.deploy").read_text()
    assert f"FH_MJ_CHECKPOINT=/app/ai/{AGENTS[0]['checkpoint_path']}" in text
    assert "FH_MJ_SYMMETRY=suits" in text
    assert '--checkpoint \\"$FH_MJ_CHECKPOINT\\"' in text and '--symmetry-average \\"$FH_MJ_SYMMETRY\\"' in text
