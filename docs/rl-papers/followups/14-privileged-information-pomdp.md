# Read Report: Privileged Information in POMDP RL

- Original paper: [Provable Partially Observable Reinforcement Learning with Privileged Information](https://arxiv.org/abs/2412.00985)

## Why it matters

This is a newer, theory-heavy confirmation that privileged-information training is a serious RL direction, not just an engineering trick.

## Main ideas

- study partially observable RL when training has access to privileged state information
- analyze asymmetric training setups where deployment only sees partial observations
- connect privileged information to stronger learning guarantees

## What seems most useful for fh-mahjong

- It supports the idea that oracle training should remain on our roadmap.
- It gives confidence that asymmetric actor-critic or auxiliary privileged targets are principled, not just ad hoc.

## Bottom line

This paper does not hand us an implementation, but it supports a major design choice: training with hidden information can be both useful and well-founded.
