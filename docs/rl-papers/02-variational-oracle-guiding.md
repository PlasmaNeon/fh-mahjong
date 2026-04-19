# Read Report: Variational Oracle Guiding for Reinforcement Learning

- Original paper: [Variational Oracle Guiding for Reinforcement Learning](https://openreview.net/forum?id=pjqqxepwoMy)

## What problem it tackles

Oracle information can make training much easier in partially observable tasks, but naive oracle usage causes train-inference mismatch. The paper formalizes a cleaner way to use hidden information only during training.

## Main ideas

The model learns two related latent states:

- a visible-information latent state, which inference can use
- an oracle-information latent state, which only exists during training

Instead of simply concatenating hidden information and later removing it, the method matches these latent spaces with a variational objective.

## Why it matters

This is a principled version of the "oracle" idea that Suphx used more heuristically. Mahjong is exactly the kind of environment where this matters because the true hidden state is rich and strategically important.

## What seems most useful for fh-mahjong

- Keep the policy input pure at inference time.
- Add oracle-only auxiliary targets during training, such as:
  - opponent concealed tile histograms
  - future wall composition summaries
  - hidden dangerous-tile counts
- Use the oracle path to shape representation learning, not to leak hidden state into deployment.

## Useful cautions

- This paper gives a clean framework, but it is still more complex than plain behavior cloning.
- We should not block Phase 1 or Phase 2 training on a full VLOG implementation. A simple auxiliary-head version may be enough at first.

## Bottom line

If we use oracle training, this is the best conceptual template: privileged information should guide the representation during training, not become a hidden dependency of the deployed policy.
