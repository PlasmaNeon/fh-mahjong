from __future__ import annotations

import torch

from fh_mahjong_ai.buffer import ReplayBuffer
from fh_mahjong_ai.config import EnvConfig, ModelConfig, TrainConfig
from fh_mahjong_ai.env import MahjongEnv
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.policies import RandomMaskedPolicy
from fh_mahjong_ai.trainer import BehaviorCloningTrainer, collect_episode


def main() -> None:
    env_config = EnvConfig()
    env = MahjongEnv(env_config)
    policy = RandomMaskedPolicy(seed=env_config.seed)

    replay_buffer = ReplayBuffer(capacity=2048)
    for episode_seed in range(4):
        replay_buffer.extend(collect_episode(env, policy, seed=episode_seed))

    model = PolicyValueNet(env_config, ModelConfig())
    optimizer = torch.optim.AdamW(model.parameters(), lr=TrainConfig().learning_rate)
    trainer = BehaviorCloningTrainer(model, optimizer, TrainConfig(batch_size=8))
    metrics = trainer.train_step(replay_buffer)

    print("self-play smoke complete")
    print(f"buffer size: {len(replay_buffer)}")
    print(f"loss: {metrics.loss:.4f}")


if __name__ == "__main__":
    main()
