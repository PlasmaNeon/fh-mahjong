from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class EnvConfig:
    action_space_size: int = 204
    plane_shape: tuple[int, int, int] = (39, 42, 1)
    scalar_features: int = 58
    max_steps_per_episode: int = 256
    bridge_kind: str = "go"
    seed: int = 1
    learning_seats: tuple[int, ...] = (0,)
    auto_play_heuristics: bool = True
    bridge_library_path: Optional[Path] = None
    match_mode: str = "classic"
    chongci_starting_score: int = 2000
    chongci_bust_threshold: int = 0
    chongci_max_hands: int = 50
    oracle_observation: bool = False
    event_history_window: int = 0

    # Mirrors internal/rl MaxEventHistoryWindow: the window sizes per-row
    # pool allocations, so an unbounded value could OOM the bridge process.
    MAX_EVENT_HISTORY_WINDOW = 512

    def __post_init__(self) -> None:
        if self.event_history_window > self.MAX_EVENT_HISTORY_WINDOW:
            raise ValueError(
                f"event_history_window {self.event_history_window} exceeds maximum "
                f"{self.MAX_EVENT_HISTORY_WINDOW}"
            )
        # Oracle mode appends the 3 opponents' closed hands (39 -> 51 channels);
        # resolve plane_shape so callers don't have to remember the channel count.
        # An explicitly-set non-default plane_shape is respected.
        if self.oracle_observation and tuple(self.plane_shape) == (39, 42, 1):
            self.plane_shape = (51, 42, 1)


@dataclass
class ModelConfig:
    channels: int = 96
    residual_blocks: int = 2
    plane_feature_dim: int = 256
    scalar_hidden_dim: int = 128
    trunk_hidden_dim: int = 256
    value_hidden_dim: int = 128
    q_hidden_dim: int = 256
    pool_planes: bool = False
    channel_attention: bool = False
    channel_attention_ratio: int = 16
    dueling_q: bool = True
    # --- Spec B2b (all default-off => state_dict identical to pre-B2b) ---
    event_window: int = 0          # 0 = no event encoder (dormant)
    event_embed_dim: int = 32
    event_hidden_dim: int = 128
    # 0 = equal to event_hidden_dim (no projection module; dormant default,
    # state_dict byte-identical to pre-gru-width). See EventEncoder.output_dim.
    event_output_dim: int = 0
    privileged_critic: bool = False
    aux_heads: bool = False
    # --- deep16-rezero capacity growth (default 0 => state_dict identical to today) ---
    growth_blocks: int = 0
    # --- mortal-scale-scratch: conv kernel width over the 42x1 plane axis.
    # 3 = the historical 3x3 kernel (default, state_dict-identical to today);
    # 1 = a (3,1) 1-D kernel (Mortal-style; two-thirds fewer conv params on a
    # width-1 plane, where a 3x3 kernel only ever multiplies padding).
    kernel_width: int = 3

    # Round 20, Finding 1a: `infer_model_config` (model.py) takes
    # `metadata["model_config"]` from a checkpoint as authoritative and
    # passes it straight into this constructor, then instantiates a real
    # PolicyValueNet from it for the shape cross-check. Round 16 bounded
    # only `event_window` (a value no weight tensor encodes, so the shape
    # cross-check can't catch it); every OTHER dimension here was still
    # unbounded, so malformed/hostile metadata claiming e.g.
    # channels=10**6 or residual_blocks=10**6 would allocate a
    # correspondingly huge network and OOM or stall the process — fatal
    # during hot reload, since the old serving policy dies with it. These
    # caps are DoS bounds, not design limits: the largest real trained
    # config to date is 8 residual blocks at 320 channels, comfortably
    # inside every ceiling below (roughly 3-4x headroom for legitimate
    # future growth).
    MAX_CHANNELS = 1024
    MAX_RESIDUAL_BLOCKS = 64
    MAX_HIDDEN_DIM = 8192
    MAX_ATTENTION_RATIO = 1024

    def __post_init__(self) -> None:
        # Round 16, Finding 2 / Round 20, Finding 1a: every architecture
        # dimension that isn't itself boolean is bounded here so a
        # metadata-supplied ModelConfig can never request an unboundedly
        # large network before any tensor is allocated.
        self._validate_bounded_int("channels", minimum=1, maximum=self.MAX_CHANNELS)
        self._validate_bounded_int("residual_blocks", minimum=0, maximum=self.MAX_RESIDUAL_BLOCKS)
        self._validate_bounded_int("plane_feature_dim", minimum=1, maximum=self.MAX_HIDDEN_DIM)
        self._validate_bounded_int("scalar_hidden_dim", minimum=1, maximum=self.MAX_HIDDEN_DIM)
        self._validate_bounded_int("trunk_hidden_dim", minimum=1, maximum=self.MAX_HIDDEN_DIM)
        self._validate_bounded_int("value_hidden_dim", minimum=1, maximum=self.MAX_HIDDEN_DIM)
        self._validate_bounded_int("q_hidden_dim", minimum=1, maximum=self.MAX_HIDDEN_DIM)
        self._validate_bounded_int(
            "channel_attention_ratio", minimum=1, maximum=self.MAX_ATTENTION_RATIO
        )
        self._validate_bounded_int("event_embed_dim", minimum=1, maximum=self.MAX_HIDDEN_DIM)
        self._validate_bounded_int("event_hidden_dim", minimum=1, maximum=self.MAX_HIDDEN_DIM)
        self._validate_bounded_int("event_output_dim", minimum=0, maximum=self.MAX_HIDDEN_DIM)
        self._validate_bounded_int("growth_blocks", minimum=0, maximum=self.MAX_RESIDUAL_BLOCKS)
        # Round 17: residual_blocks<=64 and growth_blocks<=64 are each
        # individually bounded above, but nothing stopped them composing --
        # residual_blocks=64 + growth_blocks=64 = 128 total blocks (~9GiB
        # fp32), individually legal under both caps, would still be accepted
        # here and constructed by infer_model_config's shape cross-check,
        # defeating the checkpoint-loading memory guard. MAX_RESIDUAL_BLOCKS
        # (64) is a DoS bound, not a design limit -- the largest real config
        # to date is 4 residual + 12 growth = 16 total, comfortably inside
        # this combined ceiling -- so treat it as the TOTAL depth budget.
        total_blocks = self.residual_blocks + self.growth_blocks
        if total_blocks > self.MAX_RESIDUAL_BLOCKS:
            raise ValueError(
                f"residual_blocks ({self.residual_blocks}) + growth_blocks "
                f"({self.growth_blocks}) = {total_blocks} exceeds combined "
                f"maximum {self.MAX_RESIDUAL_BLOCKS}"
            )
        # Round 16, Finding 2: metadata-authoritative checkpoint loading
        # (model.py's infer_model_config) passes a checkpoint-supplied
        # event_window straight into this constructor. GRU weights are
        # window-independent, so the shape cross-check that guards every
        # other reconstructed field can't catch a malformed/hostile value
        # here — and /act and /evaluate both allocate arrays sized by it, so
        # an unbounded value is a remote memory-exhaustion vector. Bound it
        # to the same MAX_EVENT_HISTORY_WINDOW ceiling EnvConfig enforces on
        # event_history_window (they describe the same wire quantity).
        if not isinstance(self.event_window, int) or isinstance(self.event_window, bool):
            raise ValueError(
                f"event_window must be an int, got {type(self.event_window).__name__}"
            )
        if not (0 <= self.event_window <= EnvConfig.MAX_EVENT_HISTORY_WINDOW):
            raise ValueError(
                f"event_window {self.event_window} out of bounds "
                f"[0, {EnvConfig.MAX_EVENT_HISTORY_WINDOW}]"
            )
        # Adversarial review round 2, Finding 1: event_window == 0 means
        # PolicyValueNet builds NO EventEncoder at all, so a positive
        # event_output_dim in that configuration describes a projection
        # module that will never exist -- the state_dict can never carry the
        # `event_encoder.output_proj.*` keys such a claim implies. Left
        # unrejected, this constructs happily but produces a checkpoint whose
        # own metadata `infer_model_config`'s shape cross-check then refuses
        # to load (claimed nonzero projection vs. a derived 0), bricking the
        # checkpoint. Reject the combination here, before anything is built,
        # rather than normalizing it silently at verification/serialization
        # time -- a projection width with no encoder to attach it to is not
        # a meaningful configuration to accept in the first place.
        if self.event_output_dim != 0 and self.event_window == 0:
            raise ValueError(
                f"event_output_dim ({self.event_output_dim}) must be 0 when "
                f"event_window is 0 -- a dormant event encoder (event_window == 0) "
                "builds no projection module, so a nonzero event_output_dim claims "
                "a module that will never exist"
            )
        # `isinstance(True, int)` is True and `True in (1, 3)` is True, so a
        # bare membership test would accept `kernel_width=True` and build a
        # width-1 conv from a boolean -- rejected here the same way
        # `_validate_bounded_int` rejects bools for every other int field.
        if isinstance(self.kernel_width, bool) or self.kernel_width not in (1, 3):
            raise ValueError(f"kernel_width must be 1 or 3, got {self.kernel_width!r}")

    def _validate_bounded_int(self, field: str, *, minimum: int, maximum: int) -> None:
        value = getattr(self, field)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{field} must be an int, got {type(value).__name__}")
        if not (minimum <= value <= maximum):
            raise ValueError(f"{field} {value} out of bounds [{minimum}, {maximum}]")


@dataclass
class TrainConfig:
    batch_size: int = 64
    learning_rate: float = 3e-4
    weight_decay: float = 1e-4
    max_grad_norm: float = 5.0
    device: str = "cpu"
    seed: int = 0


@dataclass
class OfflineQConfig:
    gamma: float = 0.99
    conservative_weight: float = 0.1
    bc_weight: float = 0.1
    value_weight: float = 0.25
    target_update_interval: int = 25
    target_tau: float = 1.0


@dataclass
class DiscreteIQLConfig:
    gamma: float = 0.99
    target_mode: str = "mc"
    expectile: float = 0.7
    temperature: float = 1.0
    max_weight: float = 20.0
    q_weight: float = 1.0
    value_weight: float = 1.0
    policy_weight: float = 1.0
    bc_weight: float = 1.0
    cql_weight: float = 0.0
    target_update_interval: int = 25
    target_tau: float = 0.005
    large_loss_threshold: Optional[float] = None
    large_loss_penalty: float = 0.0
    large_loss_weight: float = 1.0
    pairwise_weight: float = 0.0
    pairwise_margin: float = 0.0
    pairwise_q_weight: float = 0.0
    pairwise_q_margin: float = 0.0
    pairwise_reward_delta_weight: float = 0.0
    pairwise_reward_delta_margin_scale: float = 0.0
    pairwise_reward_delta_clip: float = 2.0
    policy_kl_weight: float = 0.0
    large_loss_aux_weight: float = 0.0
    large_loss_severity_weight: float = 0.0
    large_loss_aux_detach: bool = False
    large_loss_bc_weight: float = 0.0
    external_risk_policy_weight: float = 0.0
    external_risk_policy_threshold: float = 0.6
    external_risk_policy_family: str = "all"
    external_risk_policy_severity_weight: float = 0.0
    reward_shaping: str = "raw"
    placement_values: tuple = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0)


@dataclass
class AdvantageWeightedBCConfig:
    temperature: float = 1.0
    max_weight: float = 20.0
    value_weight: float = 0.25


@dataclass
class SelfPlayConfig:
    episodes_per_iteration: int = 32
    checkpoint_dir: Path = Path("checkpoints")
    replay_dir: Path = Path("replays")
    deterministic_eval: bool = True
