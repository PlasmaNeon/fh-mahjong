# Spec B2b: Event Encoder + Privileged Critic + Auxiliaries Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Train-time upgrade of PolicyValueNet — GRU event encoder, privileged 12ch critic branch, three auxiliary heads (belief / deal-in / rank-bust = Spec C) — warm-started from champion iter275, with the evaluation flags and comparability keys to gate it.

**Architecture:** All new modules are config-gated (default-off → state_dict identical, champion loads strict). The policy path consumes `planes[:, :39]` through the UNCHANGED 39ch stem — warm-start needs no conv surgery; events enter the trunk through zero-init columns so step-0 logits equal the champion's exactly. Privileged features (planes 39:51 via a small encoder) feed ONLY the value head; aux heads read the public trunk. A `collect_b2b_rollouts` variant records 51ch obs + event rows + hindsight labels; `ppo_update` adds `0.1·(belief_bce + dealin_bce + rank_ce)`.

**Tech Stack:** Python 3.12 / PyTorch (`ai/` only — NO Go changes in B2b).

**Spec:** `docs/superpowers/specs/2026-07-16-spec-b2b-training-design.md` (approved). Branch: `claude/spec-b2b-training` (exists, off main @ ae29337).

## Global Constraints

- Dormancy is the regression bar: default `ModelConfig` must produce a state_dict with IDENTICAL keys/shapes to today's, and a champion-shaped checkpoint must `load_checkpoint` strict.
- Collection uses the PROCESS collector path (`ParallelSelfplayCollector` pattern); batched/pool collector support is out of scope.
- No serving changes (B2c), no KL-to-champion, aux weight fixed at `0.1`.
- NO Go changes. After Python changes: `uv run --project ai pytest`.
- Warm-start invariant: `build_b2b_model` output's policy logits on any obs equal the champion's (atol 1e-5) regardless of events/oracle-channel content.
- Commits end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- Event bit layout (from `events.py`, already shipped): type bits 0-3, rel_seat 4-5, face 6-11, rel_from 12-13, tsumogiri bit 14, haitei bit 15; token = `(type*4 + rel_seat)*64 + face` ∈ [0, 2048).

---

### Task 1: Model — EventEncoder, privileged critic branch, aux heads

**Files:**
- Modify: `ai/src/fh_mahjong_ai/config.py` (ModelConfig, after `channel_attention_ratio`)
- Modify: `ai/src/fh_mahjong_ai/model.py` (PolicyValueNet `__init__`/`forward`/`encode`)
- Create: `ai/tests/test_b2b_model.py`

**Interfaces:**
- Consumes: existing `PolicyValueNet` structure; `ModelConfig`.
- Produces (later tasks rely on EXACTLY these):
  - `ModelConfig` fields: `event_window: int = 0`, `event_embed_dim: int = 32`, `event_hidden_dim: int = 128`, `privileged_critic: bool = False`, `aux_heads: bool = False`.
  - `PolicyValueNet.forward(planes, scalars, action_mask, events=None, event_lengths=None) -> (masked_logits, value)` — accepts 39ch OR 51ch planes; policy path always uses `planes[:, :39]`; when `privileged_critic` and planes are 51ch, `planes[:, 39:51]` reaches ONLY the value head (zeros substituted when only 39ch given).
  - `PolicyValueNet.encode(planes, scalars, events=None, event_lengths=None) -> Tensor` (public trunk features).
  - `PolicyValueNet.aux_predictions(features) -> dict` with keys `belief` `[B,12,42]`, `dealin` `[B]`, `rank` `[B,5]` (only when `aux_heads`).
  - `PolicyValueNet.wants_events -> bool` property (`event_window > 0`).
  - Module names (state_dict keys): `event_encoder.*`, `privileged_encoder.*`, `belief_head.*`, `dealin_head.*`, `rank_head.*`.

- [ ] **Step 1: Write the failing tests**

Create `ai/tests/test_b2b_model.py`:

```python
import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet

ENV39 = EnvConfig(bridge_kind="mock")  # plane_shape (39, 42, 1), 58 scalars, 204 actions


def _rand_obs(batch, channels=39, seed=0):
    rng = np.random.default_rng(seed)
    planes = torch.from_numpy(rng.random((batch, channels, 42, 1), dtype=np.float32))
    scalars = torch.from_numpy(rng.random((batch, 58), dtype=np.float32))
    mask = torch.zeros((batch, 204), dtype=torch.int8)
    mask[:, :8] = 1
    return planes, scalars, mask


def _rand_events(batch, window, seed=1):
    rng = np.random.default_rng(seed)
    events = torch.from_numpy(
        rng.integers(0, 0x10000, size=(batch, window), dtype=np.uint32).astype(np.int64)
    )
    lengths = torch.from_numpy(rng.integers(0, window + 1, size=(batch,)).astype(np.int64))
    return events, lengths


def test_default_config_state_dict_unchanged():
    # Dormancy: the default model's parameter names must not mention any new module.
    model = PolicyValueNet(ENV39, ModelConfig())
    keys = set(model.state_dict().keys())
    for banned in ("event_encoder", "privileged_encoder", "belief_head", "dealin_head", "rank_head"):
        assert not any(banned in k for k in keys), banned
    assert model.wants_events is False


def test_b2b_flags_create_modules_and_forward_shapes():
    config = ModelConfig(event_window=16, privileged_critic=True, aux_heads=True)
    model = PolicyValueNet(ENV39, config)
    keys = set(model.state_dict().keys())
    for expected in ("event_encoder", "privileged_encoder", "belief_head", "dealin_head", "rank_head"):
        assert any(expected in k for k in keys), expected

    planes, scalars, mask = _rand_obs(4, channels=51)
    events, lengths = _rand_events(4, 16)
    logits, value = model(planes, scalars, mask, events=events, event_lengths=lengths)
    assert logits.shape == (4, 204) and value.shape == (4,)

    features = model.encode(planes, scalars, events=events, event_lengths=lengths)
    aux = model.aux_predictions(features)
    assert aux["belief"].shape == (4, 12, 42)
    assert aux["dealin"].shape == (4,)
    assert aux["rank"].shape == (4, 5)


def test_policy_ignores_oracle_channels_and_privileged_feeds_value_only():
    # Same 39ch content, different oracle channels -> identical LOGITS,
    # (generally) different VALUES.
    config = ModelConfig(event_window=8, privileged_critic=True, aux_heads=True)
    model = PolicyValueNet(ENV39, config)
    model.eval()
    planes51a, scalars, mask = _rand_obs(3, channels=51, seed=2)
    planes51b = planes51a.clone()
    planes51b[:, 39:51] = torch.rand_like(planes51b[:, 39:51])
    events, lengths = _rand_events(3, 8)
    with torch.no_grad():
        la, va = model(planes51a, scalars, mask, events=events, event_lengths=lengths)
        lb, vb = model(planes51b, scalars, mask, events=events, event_lengths=lengths)
    assert torch.allclose(la, lb, atol=1e-6)
    assert not torch.allclose(va, vb, atol=1e-6)

    # 39ch input (eval/serving shape): privileged slice substituted with zeros, no crash.
    planes39 = planes51a[:, :39]
    with torch.no_grad():
        lc, _ = model(planes39, scalars, mask, events=events, event_lengths=lengths)
    assert torch.allclose(la, lc, atol=1e-6)


def test_event_encoder_gather_and_zero_length():
    config = ModelConfig(event_window=4)
    model = PolicyValueNet(ENV39, config)
    model.eval()
    planes, scalars, mask = _rand_obs(2)
    # Row 0: two real events then padding; row 1: zero-length.
    events = torch.zeros((2, 4), dtype=torch.int64)
    events[0, 0] = 0x140  # self draw face 5
    events[0, 1] = 0x4A51  # tsumogiri discard face 41 by right
    lengths = torch.tensor([2, 0], dtype=torch.int64)
    feats = model.event_encoder(events, lengths)
    assert feats.shape == (2, config.event_hidden_dim)
    assert torch.all(feats[1] == 0), "zero-length row must yield zeros"
    # Padding must not influence the gathered feature: changing pad slots is a no-op.
    events2 = events.clone()
    events2[0, 2] = 0x8B7
    feats2 = model.event_encoder(events2, lengths)
    assert torch.allclose(feats[0], feats2[0], atol=0), "padding leaked into the GRU feature"


def test_event_window_zero_forward_matches_legacy_signature():
    model = PolicyValueNet(ENV39, ModelConfig())
    planes, scalars, mask = _rand_obs(2)
    logits, value = model(planes, scalars, mask)  # legacy 3-arg call still works
    assert logits.shape == (2, 204)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai pytest ai/tests/test_b2b_model.py -v`
Expected: FAIL (`TypeError: __init__() got an unexpected keyword argument 'event_window'`).

- [ ] **Step 3: Implement**

`ai/src/fh_mahjong_ai/config.py` — append to `ModelConfig`:

```python
    # --- Spec B2b (all default-off => state_dict identical to pre-B2b) ---
    event_window: int = 0          # 0 = no event encoder (dormant)
    event_embed_dim: int = 32
    event_hidden_dim: int = 128
    privileged_critic: bool = False
    aux_heads: bool = False
```

`ai/src/fh_mahjong_ai/model.py` — add the encoder module (top level, after `DuelingQHead`):

```python
class EventEncoder(nn.Module):
    """GRU over the packed public-event history (Spec B2b).

    Input: raw packed uint32 codec values as int64 [B, W] + lengths [B].
    Bit layout (events.py): type 0-3 | rel_seat 4-5 | face 6-11 |
    rel_from 12-13 | tsumogiri bit 14 | haitei bit 15.
    Token = (type*4 + rel_seat)*64 + face  in [0, 2048).
    """

    NUM_TOKENS = 8 * 4 * 64  # 2048

    def __init__(self, embed_dim: int, hidden_dim: int) -> None:
        super().__init__()
        self.embedding = nn.Embedding(self.NUM_TOKENS, embed_dim)
        self.side_proj = nn.Linear(6, embed_dim)
        self.gru = nn.GRU(embed_dim, hidden_dim, batch_first=True)
        self.hidden_dim = hidden_dim

    def forward(self, events: Tensor, lengths: Tensor) -> Tensor:
        # Decode bits on-device (cheap, vectorized).
        ev_type = (events >> 0) & 0xF
        rel_seat = (events >> 4) & 0x3
        face = (events >> 6) & 0x3F
        rel_from = (events >> 12) & 0x3
        tsumogiri = ((events >> 14) & 0x1).float()
        haitei = ((events >> 15) & 0x1).float()
        tokens = (ev_type * 4 + rel_seat) * 64 + face
        side = torch.cat(
            [
                tsumogiri.unsqueeze(-1),
                haitei.unsqueeze(-1),
                torch.nn.functional.one_hot(rel_from, num_classes=4).float(),
            ],
            dim=-1,
        )
        x = self.embedding(tokens) + self.side_proj(side)
        out, _ = self.gru(x)  # [B, W, H] over the PADDED sequence
        # Gather the output at index length-1; zero-length rows -> zeros.
        batch = events.shape[0]
        idx = (lengths - 1).clamp(min=0).view(batch, 1, 1).expand(-1, 1, self.hidden_dim)
        gathered = out.gather(1, idx).squeeze(1)
        return gathered * (lengths > 0).float().unsqueeze(-1)
```

In `PolicyValueNet.__init__` (note: the policy stem stays 39ch — store the split):

```python
        self.policy_channels = channels  # 39: the stem consumes exactly these
        self.model_config = model_config
```

after `self.scalar_encoder`, replace the trunk construction with:

```python
        trunk_in = model_config.plane_feature_dim + model_config.scalar_hidden_dim
        if model_config.event_window > 0:
            self.event_encoder = EventEncoder(model_config.event_embed_dim, model_config.event_hidden_dim)
            trunk_in += model_config.event_hidden_dim
        self.trunk = nn.Sequential(
            nn.Linear(trunk_in, model_config.trunk_hidden_dim),
            nn.GELU(),
        )
```

after the trunk, the privileged encoder + value head input:

```python
        value_in = model_config.trunk_hidden_dim
        if model_config.privileged_critic:
            self.privileged_encoder = nn.Sequential(
                nn.Conv2d(12, 32, kernel_size=3, padding=1),
                nn.GELU(),
                nn.Flatten(start_dim=1),
                nn.Linear(32 * height * width, 128),
                nn.GELU(),
            )
            value_in += 128
        self.value_head = nn.Sequential(
            nn.Linear(value_in, model_config.value_hidden_dim),
            nn.GELU(),
            nn.Linear(model_config.value_hidden_dim, 1),
            nn.Tanh(),
        )
        if model_config.aux_heads:
            self.belief_head = nn.Linear(model_config.trunk_hidden_dim, 12 * 42)
            self.dealin_head = nn.Linear(model_config.trunk_hidden_dim, 1)
            self.rank_head = nn.Linear(model_config.trunk_hidden_dim, 5)
```

(the existing `self.value_head = ...` block is REPLACED by the above; with all flags off, `value_in == trunk_hidden_dim` and the produced state_dict is identical.)

`encode` gains events (planes sliced to the policy stem):

```python
    @property
    def wants_events(self) -> bool:
        return self.model_config.event_window > 0

    def encode(self, planes: Tensor, scalars: Tensor, events: Tensor | None = None,
               event_lengths: Tensor | None = None) -> Tensor:
        policy_planes = planes[:, : self.policy_channels]
        plane_features = self.plane_head(self.plane_projection(self.plane_blocks(self.plane_stem(policy_planes))))
        expected_scalars = self.scalar_encoder[0].in_features
        if scalars.shape[1] < expected_scalars:
            scalars = torch.nn.functional.pad(scalars, (0, expected_scalars - scalars.shape[1]))
        elif scalars.shape[1] > expected_scalars:
            raise ValueError(f"expected at most {expected_scalars} scalars, got {scalars.shape[1]}")
        scalar_features = self.scalar_encoder(scalars)
        parts = [plane_features, scalar_features]
        if self.wants_events:
            if events is None or event_lengths is None:
                batch = planes.shape[0]
                event_features = torch.zeros(batch, self.model_config.event_hidden_dim,
                                             device=planes.device, dtype=plane_features.dtype)
            else:
                event_features = self.event_encoder(events, event_lengths)
            parts.append(event_features)
        return self.trunk(torch.cat(parts, dim=1))
```

`forward` (and a private `_value` helper used by forward/q_values):

```python
    def _value_features(self, features: Tensor, planes: Tensor) -> Tensor:
        if not self.model_config.privileged_critic:
            return features
        if planes.shape[1] >= 51:
            priv = self.privileged_encoder(planes[:, self.policy_channels : self.policy_channels + 12])
        else:
            priv = torch.zeros(planes.shape[0], 128, device=planes.device, dtype=features.dtype)
        return torch.cat([features, priv], dim=1)

    def forward(self, planes: Tensor, scalars: Tensor, action_mask: Tensor,
                events: Tensor | None = None, event_lengths: Tensor | None = None) -> tuple[Tensor, Tensor]:
        features = self.encode(planes, scalars, events, event_lengths)
        logits = self.policy_head(features)
        masked_logits = logits.masked_fill(action_mask <= 0, torch.finfo(logits.dtype).min)
        value = self.value_head(self._value_features(features, planes)).squeeze(-1)
        return masked_logits, value

    def aux_predictions(self, features: Tensor) -> dict:
        return {
            "belief": self.belief_head(features).view(-1, 12, 42),
            "dealin": self.dealin_head(features).squeeze(-1),
            "rank": self.rank_head(features),
        }
```

Other `encode(...)` callers inside model.py (`q_values`, `large_loss_predictions`, `action_risk_predictions`) keep their signatures but now transparently work (they call `self.encode(planes, scalars)`, which zero-fills event features when `wants_events` — acceptable: those heads are not used by the B2b training/eval paths). `q_values`'s `value_head` call must go through `self._value_features(features, planes)` too.

- [ ] **Step 4: Run the tests**

Run: `uv run --project ai pytest ai/tests/test_b2b_model.py -v` — all PASS.
Run: `uv run --project ai pytest ai/tests/test_model.py ai/tests/test_ppo.py -q` — pre-existing model/ppo tests still PASS (dormancy).

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/config.py ai/src/fh_mahjong_ai/model.py ai/tests/test_b2b_model.py
git commit -m "feat(ai): B2b model — event GRU, privileged critic branch, aux heads (config-gated, dormant)

Policy path consumes planes[:, :39] through the unchanged 39ch stem;
privileged 12ch features feed only the value head; aux heads read the
public trunk. Default config builds a byte-identical state_dict.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: PPO — event tensors and aux losses through the update

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py` (`RolloutBatch` ~125, `_ROLLOUT_ARRAY_FIELDS` ~140, `ppo_update` ~205)
- Test: `ai/tests/test_b2b_ppo.py` (create)

**Interfaces:**
- Consumes: Task 1's model contract (`forward(..., events=, event_lengths=)`, `aux_predictions`, `wants_events`, `model_config.aux_heads`).
- Produces: `RolloutBatch` optional fields `events: np.ndarray | None = None` (`[N,W] uint32`), `event_lengths: np.ndarray | None = None` (`[N] int32`), `dealin_labels: np.ndarray | None = None` (`[N] float32`), `rank_labels: np.ndarray | None = None` (`[N] int64`, −1 = masked). `ppo_update` metrics gain `belief_loss`, `dealin_loss`, `rank_loss` keys when aux is active. Aux weight constant `AUX_LOSS_WEIGHT = 0.1`.

- [ ] **Step 1: Write the failing tests**

Create `ai/tests/test_b2b_ppo.py`:

```python
import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import (
    AUX_LOSS_WEIGHT,
    PPOConfig,
    RolloutBatch,
    compute_gae,
    concat_rollout_batches,
    ppo_update,
)

ENV = EnvConfig(bridge_kind="mock")


def _batch(n, window=8, seed=0, with_events=True):
    rng = np.random.default_rng(seed)
    kwargs = {}
    if with_events:
        kwargs = dict(
            events=rng.integers(0, 0x10000, size=(n, window), dtype=np.uint32),
            event_lengths=rng.integers(0, window + 1, size=n).astype(np.int32),
            dealin_labels=rng.integers(0, 2, size=n).astype(np.float32),
            rank_labels=rng.integers(-1, 5, size=n).astype(np.int64),
        )
    return RolloutBatch(
        planes=rng.random((n, 51, 42, 1), dtype=np.float32),
        scalars=rng.random((n, 58), dtype=np.float32),
        action_mask=np.ones((n, 204), dtype=np.int8),
        actions=rng.integers(0, 204, size=n),
        old_logprobs=rng.random(n).astype(np.float32) * -1,
        values=rng.random(n).astype(np.float32),
        rewards=rng.random(n).astype(np.float32),
        dones=(rng.random(n) < 0.1).astype(np.float32),
        **kwargs,
    )


def test_concat_keeps_event_rows_aligned():
    a, b = _batch(5, seed=1), _batch(3, seed=2)
    a_events0 = a.events[0].copy()
    merged = concat_rollout_batches([a, b])
    assert merged.events.shape == (8, 8)
    assert merged.event_lengths.shape == (8,)
    assert np.array_equal(merged.events[0], a_events0)
    assert merged.rank_labels.shape == (8,)


def test_concat_legacy_batches_without_events():
    merged = concat_rollout_batches([_batch(4, with_events=False), _batch(2, with_events=False)])
    assert merged.events is None and merged.rank_labels is None


def test_ppo_update_with_aux_heads_runs_and_reports():
    model = PolicyValueNet(ENV, ModelConfig(
        channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
        trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16,
        event_window=8, privileged_critic=True, aux_heads=True))
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    batch = _batch(32)
    adv, ret = compute_gae(batch.rewards, batch.values, batch.dones, 1.0, 0.95)
    config = PPOConfig(device="cpu", ppo_epochs=1, minibatch_size=16)
    metrics = ppo_update(model, optimizer, batch, adv, ret, config)
    for key in ("belief_loss", "dealin_loss", "rank_loss"):
        assert key in metrics and np.isfinite(metrics[key])
    assert AUX_LOSS_WEIGHT == 0.1


def test_ppo_update_legacy_model_unchanged_metrics():
    model = PolicyValueNet(ENV, ModelConfig(
        channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
        trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16))
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    batch = _batch(16, with_events=False)
    batch = RolloutBatch(**{**batch.__dict__, "planes": batch.planes[:, :39]})
    adv, ret = compute_gae(batch.rewards, batch.values, batch.dones, 1.0, 0.95)
    metrics = ppo_update(model, optimizer, batch, adv, ret, PPOConfig(device="cpu", ppo_epochs=1, minibatch_size=8))
    assert "belief_loss" not in metrics  # legacy metric schema untouched


def test_rank_ce_ignores_masked_rows():
    # All rank labels -1 -> rank CE contributes exactly 0 and stays finite.
    model = PolicyValueNet(ENV, ModelConfig(
        channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
        trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16,
        event_window=8, privileged_critic=True, aux_heads=True))
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    batch = _batch(16, seed=5)
    batch.rank_labels[:] = -1
    adv, ret = compute_gae(batch.rewards, batch.values, batch.dones, 1.0, 0.95)
    metrics = ppo_update(model, optimizer, batch, adv, ret, PPOConfig(device="cpu", ppo_epochs=1, minibatch_size=8))
    assert metrics["rank_loss"] == 0.0


def test_aux_gradients_reach_trunk():
    model = PolicyValueNet(ENV, ModelConfig(
        channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
        trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16,
        event_window=8, privileged_critic=True, aux_heads=True))
    batch = _batch(8, seed=7)
    planes = torch.from_numpy(batch.planes)
    scalars = torch.from_numpy(batch.scalars)
    events = torch.from_numpy(batch.events.astype(np.int64))
    lengths = torch.from_numpy(batch.event_lengths.astype(np.int64))
    features = model.encode(planes, scalars, events, lengths)
    aux = model.aux_predictions(features)
    target = torch.sigmoid(torch.randn_like(aux["belief"]))
    loss = torch.nn.functional.binary_cross_entropy_with_logits(aux["belief"], target)
    loss.backward()
    assert model.trunk[0].weight.grad is not None
    assert model.trunk[0].weight.grad.abs().sum() > 0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai pytest ai/tests/test_b2b_ppo.py -v`
Expected: FAIL (`TypeError: RolloutBatch.__init__() got an unexpected keyword argument 'events'` / ImportError for `AUX_LOSS_WEIGHT`).

- [ ] **Step 3: Implement**

`ai/src/fh_mahjong_ai/ppo.py`:

1. Constant near the top: `AUX_LOSS_WEIGHT = 0.1`.
2. `RolloutBatch` gains (after `dones`):

```python
    truncated_matches: int = 0  # (existing field, unchanged position)
    events: np.ndarray | None = None          # [N, W] uint32 packed codec values
    event_lengths: np.ndarray | None = None   # [N] int32 true lengths
    dealin_labels: np.ndarray | None = None   # [N] float32 hindsight deal-in
    rank_labels: np.ndarray | None = None     # [N] int64 rank 0-3 / 4=bust / -1=masked
```

(keep `truncated_matches` where it is; append the four optionals after it.)

3. `_ROLLOUT_ARRAY_FIELDS` gains the four names. `concat_rollout_batches` must handle optional fields: concatenate when present in ALL batches, propagate `None` when absent in all, and raise `ValueError` on a mixed present/absent set (silent misalignment is the failure mode).

4. `ppo_update`: move events/labels to device once (when `batch.events is not None`): `events_t` as int64, `lengths_t` int64, `dealin_t` float32, `rank_t` int64. Belief targets: `belief_target = (planes[:, 39:51] > 0).float()` computed once when the model has aux heads (planes are the 51ch batch; the oracle threshold planes are already 0/1-valued — the `> 0` keeps it robust). In the minibatch loop, replace the model call with:

```python
            mb_events = events_t[idx] if events_t is not None else None
            mb_lengths = lengths_t[idx] if lengths_t is not None else None
            masked_logits, value = model(planes[idx], scalars[idx], action_mask[idx],
                                         events=mb_events, event_lengths=mb_lengths)
```

and after the entropy term, when `getattr(model, "model_config", None)` has `aux_heads`:

```python
            features = model.encode(planes[idx], scalars[idx], mb_events, mb_lengths)
            aux = model.aux_predictions(features)
            belief_loss = torch.nn.functional.binary_cross_entropy_with_logits(
                aux["belief"], belief_target[idx])
            dealin_loss = torch.nn.functional.binary_cross_entropy_with_logits(
                aux["dealin"], dealin_t[idx])
            rank_mask = rank_t[idx] >= 0
            if rank_mask.any():
                rank_loss = torch.nn.functional.cross_entropy(
                    aux["rank"][rank_mask], rank_t[idx][rank_mask])
            else:
                rank_loss = torch.zeros((), device=device)
            loss = loss + AUX_LOSS_WEIGHT * (belief_loss + dealin_loss + rank_loss)
```

(one `encode` recompute per minibatch is acceptable at this scale; do NOT restructure forward to return features — that would change the legacy call contract.) Metrics dict gains the three keys only on the aux path (legacy schema untouched).

- [ ] **Step 4: Run tests, then the full suite**

Run: `uv run --project ai pytest ai/tests/test_b2b_ppo.py -v` — all PASS.
Run: `uv run --project ai pytest` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/ppo.py ai/tests/test_b2b_ppo.py
git commit -m "feat(ai): event tensors + aux losses through RolloutBatch and ppo_update

Optional batch fields concat-aligned (mixed present/absent raises);
0.1-weighted belief/deal-in/rank losses with -1-masked rank CE; legacy
metric schema untouched.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Collection + warm-start + training CLI

**Files:**
- Modify: `ai/src/fh_mahjong_ai/oracle.py` (add `build_b2b_model`, `collect_b2b_rollouts`, `ParallelB2bCollector`, `train_b2b`)
- Create: `ai/src/fh_mahjong_ai/scripts/train_b2b.py`
- Modify: `ai/pyproject.toml` (`fh-mj-train-b2b = "fh_mahjong_ai.scripts.train_b2b:main"`)
- Test: `ai/tests/test_b2b_training.py` (create)

**Interfaces:**
- Consumes: Tasks 1-2 contracts; existing `collect_selfplay_rollouts` structure (seat-contiguous emission, dense reward crediting, seeded RNG), `ParallelSelfplayCollector` worker pattern, `cpu_state_snapshot`, `load_compatible_checkpoint`, `save_checkpoint`, `feature_dropout_schedule` NOT used (no dropout in B2b).
- Produces:
  - `build_b2b_model(env_config, model_config, champion_checkpoint, device="cpu") -> PolicyValueNet` — model built with `plane_shape=(39,42,1)` env config (stem 39ch) and B2b flags; copies all champion tensors by shape; the trunk's first Linear weight `[trunk_hidden, plane_feature+scalar_hidden+event_hidden]` gets the champion's `[trunk_hidden, plane_feature+scalar_hidden]` block copied and the event columns ZEROED; new modules default-init.
  - `collect_b2b_rollouts(env_config, model, config, base_seed) -> RolloutBatch` — env at `oracle_observation=True`, `event_history_window=model.model_config.event_window`; records 51ch planes, event rows (tail-padded uint32 [n,W] + lengths), per-seat hand ids; at match end assembles `dealin_labels` (rows of seat s in hand h = 1 iff hand h's round outcome was a non-draw ron — `win_type_name == "ACTION_RON"` — with `discarder_seat == s`) and `rank_labels` (final placement 0-3 by descending final score `starting_score + net_delta`, stable seat-order tiebreak; 4 if final score <= chongci bust threshold; −1 for truncated matches). Hand boundaries: a step whose `StepResult.info` carries `round_outcome` closes the current hand for ALL seats.
  - `ParallelB2bCollector(env_config, model_config, ppo_config, num_workers)` — mirror of `ParallelSelfplayCollector` running `collect_b2b_rollouts` (no drop_prob in the task tuple).
  - `train_b2b(env_config, model_config, champion_checkpoint, checkpoint_dir, config, base_seed=0) -> list[dict]` — mirror of `train_selfplay_oracle` minus dropout/ACH: warm-start via `build_b2b_model`, per-iter collect (parallel when `num_workers > 1`) → `compute_gae` → `ppo_update`, save checkpoint + history.json rows carrying the aux metric keys.
  - CLI `fh-mj-train-b2b`: mirrors `scripts/train_selfplay_oracle.py` flags plus `--event-window 128`, `--privileged-critic/--no-privileged-critic` (default on), `--aux-heads/--no-aux-heads` (default on), `--champion` (checkpoint path).

- [ ] **Step 1: Write the failing tests**

Create `ai/tests/test_b2b_training.py` with these tests (full code; mirror the fixture style of `ai/tests/test_oracle_phase2.py` for the small `ModelConfig` and mock env config):

```python
import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.oracle import build_b2b_model, collect_b2b_rollouts, train_b2b
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.storage import save_checkpoint

_SMALL = dict(channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
              trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16)


def _champion(tmp_path):
    env39 = EnvConfig(bridge_kind="mock")
    model = PolicyValueNet(env39, ModelConfig(**_SMALL))
    path = tmp_path / "champion.pt"
    save_checkpoint(path, model)
    return env39, path


def test_warm_start_logit_equivalence(tmp_path):
    env39, champion_path = _champion(tmp_path)
    champion = PolicyValueNet(env39, ModelConfig(**_SMALL))
    from fh_mahjong_ai.storage import load_checkpoint
    load_checkpoint(champion_path, champion)
    champion.eval()

    b2b_config = ModelConfig(**_SMALL, event_window=16, privileged_critic=True, aux_heads=True)
    model = build_b2b_model(env39, b2b_config, champion_path)
    model.eval()

    rng = np.random.default_rng(3)
    planes39 = torch.from_numpy(rng.random((4, 39, 42, 1), dtype=np.float32))
    planes51 = torch.cat([planes39, torch.from_numpy(rng.random((4, 12, 42, 1), dtype=np.float32))], dim=1)
    scalars = torch.from_numpy(rng.random((4, 58), dtype=np.float32))
    mask = torch.ones((4, 204), dtype=torch.int8)
    events = torch.from_numpy(rng.integers(0, 0x10000, size=(4, 16), dtype=np.uint32).astype(np.int64))
    lengths = torch.full((4,), 16, dtype=torch.int64)

    with torch.no_grad():
        ref, _ = champion(planes39, scalars, mask)
        got51, _ = model(planes51, scalars, mask, events=events, event_lengths=lengths)
        got39, _ = model(planes39, scalars, mask, events=events, event_lengths=lengths)
    assert torch.allclose(ref, got51, atol=1e-5)
    assert torch.allclose(ref, got39, atol=1e-5)


def test_collect_b2b_records_events_and_labels(tmp_path):
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=32)
    model = PolicyValueNet(env, ModelConfig(**_SMALL, event_window=8,
                                            privileged_critic=True, aux_heads=True))
    config = PPOConfig(device="cpu", matches_per_iter=2, max_steps_per_episode=32,
                       match_mode="classic")
    batch = collect_b2b_rollouts(env, model, config, base_seed=11)
    n = len(batch)
    assert batch.planes.shape[1] == 51
    assert batch.events.shape == (n, 8) and batch.events.dtype == np.uint32
    assert batch.event_lengths.shape == (n,)
    assert np.all(batch.event_lengths <= 8)
    assert batch.dealin_labels.shape == (n,)
    assert set(np.unique(batch.rank_labels)).issubset({-1, 0, 1, 2, 3, 4})


def test_hindsight_label_assembly_fixture():
    # Pure-function check on the label assembler with a scripted match:
    # 2 hands; hand 0 ends in a ron paid by seat 2; hand 1 is a draw.
    from fh_mahjong_ai.oracle import _assemble_hindsight_labels

    # rows: (seat, hand_id) in emission order for a 3-seat toy
    rows = [(0, 0), (2, 0), (2, 0), (1, 1), (2, 1)]
    hand_outcomes = {0: {"is_draw": False, "win_type_name": "ACTION_RON", "discarder_seat": 2},
                     1: {"is_draw": True, "win_type_name": "ACTION_UNKNOWN", "discarder_seat": 0}}
    final_scores = {0: 2500.0, 1: 2000.0, 2: -100.0, 3: 1600.0}
    dealin, rank = _assemble_hindsight_labels(rows, hand_outcomes, final_scores,
                                              bust_threshold=0.0, truncated=False)
    assert dealin.tolist() == [0.0, 1.0, 1.0, 0.0, 0.0]
    # scores: seat0=2500 (rank0), seat1=2000 (rank1), seat3=1600 (rank2), seat2 busted (4)
    assert rank.tolist() == [0, 4, 4, 1, 4]

    dealin_t, rank_t = _assemble_hindsight_labels(rows, hand_outcomes, final_scores,
                                                  bust_threshold=0.0, truncated=True)
    assert rank_t.tolist() == [-1] * 5
    assert dealin_t.tolist() == [0.0, 1.0, 1.0, 0.0, 0.0]  # deal-in survives truncation


def test_train_b2b_two_iters_mock(tmp_path):
    env39, champion_path = _champion(tmp_path)
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=2, matches_per_iter=2,
                       max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                       num_workers=1, match_mode="classic")
    history = train_b2b(env, ModelConfig(**_SMALL, event_window=8, privileged_critic=True,
                                         aux_heads=True),
                        champion_path, tmp_path / "ckpt", config, base_seed=5)
    assert len(history) == 2
    assert (tmp_path / "ckpt" / "iter_002.pt").exists()
    for key in ("belief_loss", "dealin_loss", "rank_loss"):
        assert key in history[0]
```

NOTE for the implementer: the mock bridge produces random planes/scalars and no real round outcomes — `collect_b2b_rollouts` must handle `info` without `round_outcome` (hand never closes → all dealin 0, rank labels computed at termination normally). The pure-function fixture test is where label CORRECTNESS is pinned; the mock e2e test pins plumbing/shapes. `_assemble_hindsight_labels(rows, hand_outcomes, final_scores, bust_threshold, truncated)` is the factored pure function: `rows` = list of (seat, hand_id) in EMISSION order (seat-contiguous blocks, matching the collector's emission), returns `(dealin float32[N], rank int64[N])`. Rank from final_scores: descending sort, stable seat-index tiebreak; score <= bust_threshold → 4; truncated → all −1.

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai pytest ai/tests/test_b2b_training.py -v`
Expected: FAIL (ImportError: `build_b2b_model`).

- [ ] **Step 3: Implement in oracle.py**

`build_b2b_model`: construct `PolicyValueNet(env39, b2b_model_config)`; `load_compatible_checkpoint(champion_path, model)` (loads every same-shape tensor; SKIPS `trunk.0.weight` since its input dim grew and `value_head.0.weight` when privileged); then explicit surgery:

```python
def build_b2b_model(env_config, model_config, champion_checkpoint, device="cpu"):
    """Warm-start the B2b net from the 39ch champion. The plane stem is
    UNCHANGED (39ch policy slice), so only two tensors need surgery:
    trunk.0 (event columns zeroed => step-0 logits == champion) and
    value_head.0 (privileged columns zeroed => step-0 values == champion)."""
    model = PolicyValueNet(env_config, model_config).to(device)
    load_compatible_checkpoint(Path(champion_checkpoint), model)
    payload = torch.load(Path(champion_checkpoint), map_location="cpu")
    old_trunk_w = payload["model"]["trunk.0.weight"]      # [T, P+S]
    old_value_w = payload["model"]["value_head.0.weight"]  # [V, T]
    with torch.no_grad():
        w = model.trunk[0].weight                          # [T, P+S(+E)]
        w.zero_()
        w[:, : old_trunk_w.shape[1]].copy_(old_trunk_w.to(w.device))
        model.trunk[0].bias.copy_(payload["model"]["trunk.0.bias"].to(w.device))
        if model_config.privileged_critic:
            vw = model.value_head[0].weight                # [V, T+128]
            vw.zero_()
            vw[:, : old_value_w.shape[1]].copy_(old_value_w.to(vw.device))
            model.value_head[0].bias.copy_(payload["model"]["value_head.0.bias"].to(vw.device))
    model.eval()
    return model
```

`collect_b2b_rollouts`: copy `collect_selfplay_rollouts`'s structure with these deltas — env config sets `oracle_observation=True`, `event_history_window=model.model_config.event_window`; NO drop_prob/masking; per-row also record the event row (`np.zeros(W, np.uint32)` filled with `obs.event_history`, length recorded) and the current `hand_id` per seat row; `hand_counter` increments when `step.info.get("round_outcome")` is present, and that hand's outcome dict is stored in `hand_outcomes[hand_id]`; model call passes events (`torch.from_numpy(row_events.astype(np.int64)).unsqueeze(0)`, length tensor). At match end compute per-seat final scores: `starting = config.chongci_starting_score if chongci else 0.0`; `final_scores[k] = starting + sum(seat_rewards[k])`; assemble labels via `_assemble_hindsight_labels` with `truncated = step.truncated`; extend the flat lists including events/lengths/labels; dones as before.

`_assemble_hindsight_labels`: the pure function specified in the test note.

`ParallelB2bCollector`: mirror `ParallelSelfplayCollector`/`_oracle_worker_loop` with a task tuple `(worker_id, state_dict, base_seed, matches)` and `collect_b2b_rollouts` in the worker; workers construct the model from `model_config` (which carries the B2b flags) — reuse `_split_counts` and result-queue conventions verbatim.

`train_b2b`: mirror `train_selfplay_oracle` minus dropout/ACH/pool paths: `build_b2b_model` → loop: collect (parallel via `ParallelB2bCollector` + `cpu_state_snapshot` when `num_workers > 1`, else sequential) → `compute_gae` → `ppo_update` → merge metrics (aux keys flow automatically) → `save_checkpoint` + history.json.

`scripts/train_b2b.py`: clone `scripts/train_selfplay_oracle.py`'s argparse (drop `--collector`/pool args and ACH args; add `--champion` required, `--event-window` default 128, `--privileged-critic` default True with `--no-privileged-critic`, `--aux-heads` default True with `--no-aux-heads`); register `fh-mj-train-b2b` in pyproject.

- [ ] **Step 4: Run tests, then full suite**

Run: `uv run --project ai pytest ai/tests/test_b2b_training.py -v` — all PASS.
Run: `uv run --project ai pytest` — all PASS.
Run: `uv run --project ai fh-mj-train-b2b --help` — usage prints.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/oracle.py ai/src/fh_mahjong_ai/scripts/train_b2b.py ai/pyproject.toml ai/tests/test_b2b_training.py
git commit -m "feat(ai): B2b collection, warm-start surgery, and fh-mj-train-b2b

collect_b2b_rollouts records 51ch obs + event rows + hindsight labels
(pure-function assembler with fixture tests); build_b2b_model zeroes only
the trunk event columns and privileged value columns (step-0 logits ==
champion, tested); train_b2b mirrors the champion pipeline minus dropout.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Evaluation flags + comparability key

**Files:**
- Modify: `ai/src/fh_mahjong_ai/scripts/model_config_args.py` (add `--model-event-window`, `--model-privileged-critic`, `--model-aux-heads`)
- Modify: `ai/src/fh_mahjong_ai/scripts/evaluate.py` (add `--event-history-window`, thread into EnvConfig construction)
- Modify: `ai/src/fh_mahjong_ai/evaluate.py` (persist `event_history_window` in both duplicate-seat reports; `TorchGreedyPolicy` event threading — see below)
- Modify: `ai/src/fh_mahjong_ai/policies.py` (`TorchGreedyPolicy` passes events when the model wants them)
- Modify: `ai/src/fh_mahjong_ai/scripts/compare_reports.py` (`_COMPAT_KEYS` gains `"event_history_window"`)
- Test: extend `ai/tests/test_b2b_model.py` + `ai/tests/test_compare_reports.py`

**Interfaces:**
- Consumes: Task 1's `wants_events`; `Observation.event_history` (uint32 array, already delivered by bridges); Spec A's persisted-config pattern (`"max_steps_per_episode": max_steps_per_episode,` lines in both duplicate builders).
- Produces: `fh-mj-evaluate --event-history-window 128 --model-event-window 128 --model-privileged-critic --model-aux-heads` runs the deployable inference path end-to-end; reports carry `event_history_window`; `fh-mj-compare` refuses window-mismatched pairs.

- [ ] **Step 1: Write the failing tests**

Append to `ai/tests/test_compare_reports.py`:

```python
def test_event_window_mismatch_refused():
    seeds = [1, 2, 3]
    means = [0.0, 0.1, -0.1]
    a = make_report(seeds, means)
    b = make_report(seeds, means)
    a["event_history_window"] = 128
    b["event_history_window"] = 0
    with pytest.raises(ValueError, match="not comparable.*event_history_window"):
        paired_comparison(a, b)
```

Append to `ai/tests/test_b2b_model.py`:

```python
def test_greedy_policy_threads_events():
    from fh_mahjong_ai.policies import TorchGreedyPolicy
    from fh_mahjong_ai.types import Observation

    model = PolicyValueNet(ENV39, ModelConfig(
        channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
        trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16, event_window=8))
    policy = TorchGreedyPolicy(model, device="cpu")
    rng = np.random.default_rng(9)
    mask = np.zeros(204, dtype=np.int8)
    mask[:4] = 1
    obs = Observation(
        seat=0,
        planes=rng.random((39, 42, 1), dtype=np.float32),
        scalars=rng.random(58, dtype=np.float32),
        action_mask=mask,
        event_history=np.asarray([0x140, 0x4A51], dtype=np.uint32),
    )
    action_a = policy.select_action(obs)
    # Different history CAN change the choice; the contract test is only
    # that events are consumed without error and the action is legal.
    assert 0 <= action_a < 4
```

(Check `TorchGreedyPolicy`'s actual method name in `policies.py` — `select_action` or `__call__` — and use the real one; do not guess.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai pytest ai/tests/test_compare_reports.py::test_event_window_mismatch_refused ai/tests/test_b2b_model.py::test_greedy_policy_threads_events -v`
Expected: compare test FAILS (no such compat key — comparison succeeds); policy test may fail on missing event threading (model with `wants_events` receives no events → zero-filled features; the test still passes action-legality — if it passes trivially, strengthen it by asserting the model was called with a non-None events tensor via a small monkeypatch on `model.forward`). Implement the monkeypatch variant if needed so the test is RED first.

- [ ] **Step 3: Implement**

1. `compare_reports.py`: add `"event_history_window"` to `_COMPAT_KEYS` (before `bridge_lib_sha256`, with a one-line comment: window-on vs window-off is a different protocol).
2. `evaluate.py`: in BOTH duplicate-seat report dicts, after `"oracle_observation": oracle_observation,` add `"event_history_window": event_history_window,` — which requires threading an `event_history_window: int = 0` parameter through `evaluate_duplicate_seats_policy`, `evaluate_duplicate_seats`, `evaluate_online`, `evaluate_policy_online` into the internal `EnvConfig(...)` constructions (grep `oracle_observation=` inside evaluate.py and mirror every occurrence).
3. `policies.py` `TorchGreedyPolicy`: where `_obs_to_tensors`-style conversion happens, add:

```python
        events = lengths = None
        if getattr(self.model, "wants_events", False):
            history = np.asarray(getattr(obs, "event_history", np.zeros(0, np.uint32)), dtype=np.uint32)
            window = self.model.model_config.event_window
            row = np.zeros((1, window), dtype=np.int64)
            n = min(len(history), window)
            if n:
                row[0, :n] = history[-n:].astype(np.int64)
            events = torch.from_numpy(row).to(self.device)
            lengths = torch.tensor([n], dtype=torch.int64, device=self.device)
```

and pass `events=events, event_lengths=lengths` to the model call.
4. `scripts/model_config_args.py`: `--model-event-window` (int, default 0), `--model-privileged-critic` (store_true), `--model-aux-heads` (store_true) + wire into the ModelConfig it builds.
5. `scripts/evaluate.py`: `--event-history-window` (int, default 0) → the EnvConfig(s) built for online eval + pass down to the duplicate-seat call's new parameter.

- [ ] **Step 4: Run tests, then full suite**

Run: `uv run --project ai pytest ai/tests/test_compare_reports.py ai/tests/test_b2b_model.py ai/tests/test_evaluate.py -q` — PASS.
Run: `uv run --project ai pytest` — PASS.
Run: `uv run --project ai fh-mj-evaluate --checkpoint /dev/null --help > /dev/null && echo ok` — flag listed in `--help`.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/model_config_args.py ai/src/fh_mahjong_ai/scripts/evaluate.py ai/src/fh_mahjong_ai/evaluate.py ai/src/fh_mahjong_ai/policies.py ai/src/fh_mahjong_ai/scripts/compare_reports.py ai/tests/test_b2b_model.py ai/tests/test_compare_reports.py
git commit -m "feat(ai): eval flags for the B2b inference path + window comparability key

--event-history-window threads bridge->policy (TorchGreedyPolicy passes
tail-windowed events when the model wants them); duplicate-seat reports
persist the window; fh-mj-compare refuses window-mismatched pairs.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Docs + runbook + whole-branch verification

**Files:**
- Modify: `ai/AGENTS.md` (model.py B2b modules, ppo.py fields/losses, oracle.py b2b entry points, evaluate/compare flags — one bullet each, matching file style)
- Create: `docs/superpowers/plans/2026-07-16-spec-b2b-runbook.md` (the §6 run protocol as an operational checklist)

- [ ] **Step 1: Write the runbook**

Create `docs/superpowers/plans/2026-07-16-spec-b2b-runbook.md`:

```markdown
# B2b Run Protocol (post-merge, RTX 4090 box)

Prereqs: merged main pulled on the box (`ssh wsl`, /root/fh-mahjong); bridge
rebuilt (`go build -buildmode=c-shared -o build/libfh_mahjong_bridge.so ./cmd/rlbridge`).
Champion: /root/fh-mahjong-runs/deploy/selfplay-deep4-student-iter275-39ch.pt.
Champion screening report: /root/fh-mahjong-runs/spec-a/champion-fixed.json.

1. Train (150 iters, ckpt every iter — pruning later is cheaper than regret):
   /root/.local/bin/uv run --project ai fh-mj-train-b2b \
     --champion /root/fh-mahjong-runs/deploy/selfplay-deep4-student-iter275-39ch.pt \
     --checkpoint-dir /root/fh-mahjong-runs/b2b/ckpt \
     --model-residual-blocks 4 --event-window 128 \
     --iterations 150 --matches-per-iter 256 --num-workers 5 \
     --lr 2e-5 --entropy-coef 0 --ppo-epochs 2 --gamma 1.0 \
     --match-mode chongci --max-steps-per-episode 4000 --device cuda \
     --mlflow
   (exact flag names per scripts/train_b2b.py; matches-per-iter matches the
   champion pipeline's box scripts — confirm against the phaseB1 run command
   in the progress note before launching.)
2. Screening at iters 25/50/75/100/125/150:
   fh-mj-evaluate --checkpoint ckpt/iter_XXX.pt --model-residual-blocks 4 \
     --model-event-window 128 --model-privileged-critic --model-aux-heads \
     --event-history-window 128 --duplicate-seats --online-episodes 120 \
     --start-seed 910000 --match-mode chongci --device cuda \
     --report-output /root/fh-mahjong-runs/b2b/screen-XXX.json
   then: fh-mj-compare screen-XXX.json /root/fh-mahjong-runs/spec-a/champion-fixed.json
   (bridge digests match — same library — so this is a STRICT comparison.)
3. KILL RULE: at iter >= 50, paired delta < -0.06 -> stop, diagnose, report
   (scratch run or aux-weight change is a NEW user decision).
4. Promotion gate: best screening checkpoint ->
   both the candidate AND the champion evaluated on --start-seed 950000,
   --online-episodes 1500 (~6h each), same bridge, then fh-mj-compare strict.
   Promote iff the paired delta's clustered CI clears 0.
5. Record the outcome + per-head loss curves in
   docs/rl-papers/chongci-rl-experiment-progress.md (win or lose).
   On promotion: write the B2c spec (serving integration) BEFORE deployment.
```

- [ ] **Step 2: AGENTS.md sweep + full verification**

Update `ai/AGENTS.md` (four bullets). Then:

```bash
uv run --project ai pytest
git diff origin/main --stat
```
Expected: suite green; diff touches only `ai/` files + the two docs + spec/plan.

- [ ] **Step 3: Commit**

```bash
git add ai/AGENTS.md docs/superpowers/plans/2026-07-16-spec-b2b-runbook.md
git commit -m "docs(ai): B2b AGENTS.md sweep + 4090 run protocol

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Then: final whole-branch review → adversarial-review-loop → PR → GitHub Codex approval → `gh pr merge N --merge` → execute the runbook.
