# Read Report: CBAM

- Original paper: [CBAM: Convolutional Block Attention Module](https://arxiv.org/abs/1807.06521)

## What problem it tackles

Standard CNNs treat every channel and every spatial location equally. CBAM adds light-weight channel attention and spatial attention so the model can emphasize the most relevant features.

## Main ideas

CBAM stacks two small attention modules:

1. channel attention
2. spatial attention

It is designed to be easy to plug into existing CNN backbones.

## Why it matters

If we stay with a convolutional encoder for tile planes, CBAM is a low-cost way to test whether mild attention improves representation quality.

## What seems most useful for fh-mahjong

- It is easy to test in a Suphx-style no-pooling residual CNN.
- It may help the model focus on important tile groups, dangerous discards, or action-specific regions without redesigning the whole architecture.

## Useful cautions

- This paper is generic computer vision work, not Mahjong-specific RL.
- It is not a substitute for better rewards, better features, or better training data.
- If we move to a history-aware transformer later, CBAM probably becomes less central.

## Bottom line

CBAM is a good ablation, not a core design pillar. We should treat it as "cheap to try later" rather than "must have now."
