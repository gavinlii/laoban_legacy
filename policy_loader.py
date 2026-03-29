from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Tuple

import numpy as np
import torch
import torch.nn as nn

import encoder as current_encoder
import legacy_encoder
from game import GameEnv, RandomPlayer

if torch.cuda.is_available():
    DEVICE = torch.device("cuda")
elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
    DEVICE = torch.device("mps")
else:
    DEVICE = torch.device("cpu")

if DEVICE.type == "cpu":
    try:
        torch.set_num_threads(min(4, max(1, torch.get_num_threads())))
    except Exception:
        pass
    try:
        torch.set_num_interop_threads(1)
    except Exception:
        pass


class ActionConditionedPVNet(nn.Module):
    def __init__(self, state_dim: int, action_dim: int, hidden: int = 320, value_head_kind: str = "mlp"):
        super().__init__()
        self.hidden = hidden
        self.value_head_kind = value_head_kind
        self.state_net = nn.Sequential(
            nn.Linear(state_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
        )
        self.action_net = nn.Sequential(
            nn.Linear(action_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
        )
        self.policy_net = nn.Sequential(
            nn.Linear(hidden * 2, hidden), nn.ReLU(),
            nn.Linear(hidden, 1),
        )
        if value_head_kind == "mlp":
            self.value_head = nn.Sequential(
                nn.Linear(hidden, hidden), nn.ReLU(),
                nn.Linear(hidden, 1),
            )
        elif value_head_kind == "linear":
            self.value_head = nn.Linear(hidden, 1)
        else:
            raise ValueError(f"Unsupported value_head_kind={value_head_kind}")

    def score_actions(self, state_batch: torch.Tensor, action_batch: torch.Tensor):
        s = self.state_net(state_batch)
        a = self.action_net(action_batch)
        s_exp = s.unsqueeze(1).expand(-1, action_batch.shape[1], -1)
        joint = torch.cat([s_exp, a], dim=-1)
        logits = self.policy_net(joint).squeeze(-1)
        values = self.value_head(s).squeeze(-1)
        return logits, values


@dataclass(frozen=True)
class EncoderSpec:
    name: str
    module: ModuleType
    state_dim: int
    action_dim: int


@dataclass
class LoadedPolicy:
    path: str
    model: nn.Module
    encoder_spec: EncoderSpec
    checkpoint: dict
    hidden: int
    value_head_kind: str

    def choose_action(self, infoset, stochastic: bool = False):
        enc = self.encoder_spec.module
        state = enc.encode_state(infoset)
        legal_actions = infoset["legal_actions"]
        action_feats = np.stack([enc.encode_move(a, infoset) for a in legal_actions]).astype(np.float32)
        with torch.no_grad():
            state_t = torch.from_numpy(state).float().unsqueeze(0).to(DEVICE)
            acts_t = torch.from_numpy(action_feats).float().unsqueeze(0).to(DEVICE)
            logits, values = self.model.score_actions(state_t, acts_t)
            if stochastic:
                dist = torch.distributions.Categorical(logits=logits[0])
                idx = int(dist.sample().item())
                log_prob = float(dist.log_prob(torch.tensor(idx, device=DEVICE)).item())
            else:
                idx = int(torch.argmax(logits[0]).item())
                log_prob = None
            value = float(values[0].item())
            probs = torch.softmax(logits[0], dim=0).detach().cpu().numpy()
        return {
            "index": idx,
            "move": legal_actions[idx],
            "value": value,
            "probs": probs,
            "log_prob": log_prob,
            "action_features": action_feats,
        }


def _infer_encoder_specs() -> Tuple[EncoderSpec, EncoderSpec]:
    dummy_env = GameEnv([RandomPlayer(), RandomPlayer()], verbose=False)
    infoset = dummy_env._get_infoset(None, None)
    current = EncoderSpec(
        name="current",
        module=current_encoder,
        state_dim=len(current_encoder.encode_state(infoset)),
        action_dim=current_encoder.move_feature_dim(),
    )
    legacy = EncoderSpec(
        name="legacy",
        module=legacy_encoder,
        state_dim=len(legacy_encoder.encode_state(infoset)),
        action_dim=legacy_encoder.move_feature_dim(),
    )
    return current, legacy


CURRENT_ENCODER_SPEC, LEGACY_ENCODER_SPEC = _infer_encoder_specs()


def select_encoder_spec(state_dim: int, action_dim: int) -> EncoderSpec:
    for spec in (CURRENT_ENCODER_SPEC, LEGACY_ENCODER_SPEC):
        if spec.state_dim == state_dim and spec.action_dim == action_dim:
            return spec
    raise ValueError(
        f"Unsupported checkpoint dimensions: state_dim={state_dim}, action_dim={action_dim}. "
        f"Known current dims=({CURRENT_ENCODER_SPEC.state_dim}, {CURRENT_ENCODER_SPEC.action_dim}), "
        f"legacy dims=({LEGACY_ENCODER_SPEC.state_dim}, {LEGACY_ENCODER_SPEC.action_dim})."
    )


def _normalize_state_dict(raw_state_dict: dict) -> dict:
    state_dict = dict(raw_state_dict)
    # Some older checkpoints used q_head for the scalar value head.
    if "q_head.weight" in state_dict and "value_head.weight" not in state_dict:
        state_dict["value_head.weight"] = state_dict.pop("q_head.weight")
        state_dict["value_head.bias"] = state_dict.pop("q_head.bias")
    return state_dict


def _infer_value_head_kind(state_dict: dict) -> str:
    if "value_head.0.weight" in state_dict and "value_head.2.weight" in state_dict:
        return "mlp"
    if "value_head.weight" in state_dict:
        return "linear"
    raise RuntimeError(
        "Could not infer value head type from checkpoint. "
        "Expected either linear keys like 'value_head.weight' or MLP keys like 'value_head.0.weight'."
    )


def load_policy(checkpoint_path: str) -> LoadedPolicy:
    path = str(Path(checkpoint_path).expanduser().resolve())
    ckpt = torch.load(path, map_location=DEVICE)
    if not isinstance(ckpt, dict) or "model_state_dict" not in ckpt:
        raise ValueError(f"Checkpoint at {path} is not in the expected format.")

    state_dim = int(ckpt["state_dim"])
    action_dim = int(ckpt["action_dim"])
    encoder_spec = select_encoder_spec(state_dim, action_dim)

    state_dict = _normalize_state_dict(ckpt["model_state_dict"])
    hidden = int(ckpt.get("hidden") or state_dict["state_net.0.weight"].shape[0])
    value_head_kind = _infer_value_head_kind(state_dict)

    model = ActionConditionedPVNet(
        state_dim,
        action_dim,
        hidden=hidden,
        value_head_kind=value_head_kind,
    ).to(DEVICE)
    missing, unexpected = model.load_state_dict(state_dict, strict=False)
    if missing or unexpected:
        raise RuntimeError(
            f"Checkpoint load mismatch for {path}. "
            f"Missing keys: {missing}. Unexpected keys: {unexpected}. "
            f"Inferred value_head_kind={value_head_kind}, hidden={hidden}, "
            f"encoder={encoder_spec.name} ({state_dim}/{action_dim})."
        )
    model.eval()

    return LoadedPolicy(
        path=path,
        model=model,
        encoder_spec=encoder_spec,
        checkpoint=ckpt,
        hidden=hidden,
        value_head_kind=value_head_kind,
    )


def smoke_test_checkpoint(checkpoint_path: str) -> dict:
    policy = load_policy(checkpoint_path)
    env = GameEnv([RandomPlayer(), RandomPlayer()], verbose=False)
    infoset = env._get_infoset(None, None)
    decision = policy.choose_action(infoset)
    if decision["move"] not in infoset["legal_actions"]:
        raise RuntimeError("Policy chose an illegal move during smoke test.")
    return {
        "path": policy.path,
        "encoder": policy.encoder_spec.name,
        "state_dim": policy.encoder_spec.state_dim,
        "action_dim": policy.encoder_spec.action_dim,
        "hidden": policy.hidden,
        "value_head_kind": policy.value_head_kind,
        "episode": policy.checkpoint.get("episode", "unknown"),
        "legal_actions": len(infoset["legal_actions"]),
        "chosen_index": decision["index"],
    }
