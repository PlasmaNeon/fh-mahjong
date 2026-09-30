"""A checkpoint ensemble played as one policy: the mean of the members' masked log-probabilities.

`LogProbEnsemble` has `PolicyValueNet`'s forward signature and returns (averaged log-probabilities as
logits, mean value), so every greedy path — the batched evaluator, its CUDA-graph forward and its
symmetry averaging — plays the ensemble unchanged. Illegal actions stay at float32's finite minimum,
the value `PolicyValueNet` masks them to. Members must share the observation contract (event window,
privileged critic); their trunks may differ.
"""
from __future__ import annotations

from typing import Sequence

import torch
from torch import nn


class LogProbEnsemble(nn.Module):
    def __init__(self, members: Sequence[nn.Module]) -> None:
        super().__init__()
        if len(members) < 2:
            raise ValueError("an ensemble needs at least two members")
        windows = {int(getattr(m.model_config, "event_window", 0)) for m in members}
        if len(windows) != 1:
            raise ValueError(f"ensemble members disagree on event_window: {sorted(windows)}")
        self.members = nn.ModuleList(members)
        self.model_config = members[0].model_config
        self.wants_events = bool(getattr(members[0], "wants_events", False))

    def forward(self, planes, scalars, action_mask, events=None, event_lengths=None):
        logps, values = [], []
        for member in self.members:
            logits, value = member(planes, scalars, action_mask, events=events,
                                   event_lengths=event_lengths)
            logps.append(torch.log_softmax(logits.float(), dim=-1))
            values.append(value.float())
        # Re-mask: averaging entries near float32's minimum can overflow to -inf.
        mean = torch.stack(logps).mean(dim=0)
        mean = mean.masked_fill(action_mask <= 0, torch.finfo(mean.dtype).min)
        return mean, torch.stack(values).mean(dim=0)
