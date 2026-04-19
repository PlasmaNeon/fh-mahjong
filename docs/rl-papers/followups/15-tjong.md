# Read Report: Tjong

- Original DOI: [Tjong: A transformer-based Mahjong AI via hierarchical decision-making and fan backward](https://doi.org/10.1049/cit2.12298)
- Accessible publication record: [NJIT publication page](https://digitalcommons.njit.edu/fac_pubs/267/)

## Access note

The DOI points to the publisher page, which may require access controls. The public NJIT publication page is a useful backup for metadata and the abstract.

## Why it matters

This is one of the most directly relevant newer Mahjong AI papers because it combines newer model structure with Mahjong-specific decision decomposition.

## Main ideas

- transformer-based backbone
- hierarchical decision-making instead of one flat action choice
- "fan backward" reward shaping to push sparse win-value information backward through the trajectory

## What seems most useful for fh-mahjong

- A hierarchical policy matches Mahjong naturally and may fit our 204-action space better than one undifferentiated head.
- Transformer memory is attractive once we care about long context, defense, and opponent inference.
- Reward shaping that propagates fan or score information backward is a concrete alternative to using only terminal reward.

## Useful cautions

- This is a later paper, but that does not automatically mean it is the best first implementation for our repo.
- A transformer-heavy hierarchical agent will need a more mature training pipeline than we have today.

## Bottom line

Tjong is a strong candidate for our second-generation model design after the current BC and self-play pipeline is stable.
