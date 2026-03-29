import argparse
import copy
import os
import random
import sys
from collections import Counter, deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from game import GameEnv, HumanPlayer, Move, RandomPlayer
from encoder import encode_move, encode_state, move_feature_dim
import legacy_encoder
import compat_encoder

GAMMA = 0.997
LAMBDA = 0.97
LR = 3e-5
EPS_CLIP = 0.10
EPOCHS = 2
MINIBATCH_SIZE = 128
ROLLOUTS_PER_BATCH = 24

ENTROPY_START = 0.012
ENTROPY_END = 0.0015
VALUE_COEF = 0.75

POINT_SCALE = 10.0
TERMINAL_WIN_BONUS = 4.0

LEAGUE_SIZE = 16
RECENT_POOL_SIZE = 8
FRONTIER_SIZE = 4
EXPLOITER_POOL_SIZE = 4
SNAPSHOT_EVAL_FREQ = 50
EVAL_PRINT_FREQ = 50
RANDOM_EVAL_GAMES = 20
BASELINE_EVAL_GAMES = 100
POOL_EVAL_GAMES = 14
RECENT_BEST_GAMES = 80
FRONTIER_EVAL_GAMES = 20
EXPLOITER_EVAL_GAMES = 24

ENDGAME_REPLAY_BUFFER_SIZE = 512
ENDGAME_REPLAY_MIN_BUFFER = 24
ENDGAME_REPLAY_START_EP = 120
ENDGAME_REPLAY_MAX_PROB = 0.30

CHECKPOINT_LATEST = "policy_latest.pt"
CHECKPOINT_BEST = "policy_best.pt"
DEFAULT_BASELINE_CHECKPOINT = "policy_latest_bl.pt"

if torch.cuda.is_available():
    DEVICE = torch.device("cuda")
elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
    DEVICE = torch.device("mps")
else:
    DEVICE = torch.device("cpu")

if DEVICE.type == "cpu":
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    torch.set_num_interop_threads(1)


class ActionConditionedPVNet(nn.Module):
    def __init__(self, state_dim: int, action_dim: int, hidden: int = 320):
        super().__init__()
        self.hidden = hidden
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
        self.value_head = nn.Sequential(
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def score_actions(self, state_batch: torch.Tensor, action_batch: torch.Tensor):
        s = self.state_net(state_batch)
        a = self.action_net(action_batch)
        s_exp = s.unsqueeze(1).expand(-1, action_batch.shape[1], -1)
        joint = torch.cat([s_exp, a], dim=-1)
        logits = self.policy_net(joint).squeeze(-1)
        values = self.value_head(s).squeeze(-1)
        return logits, values


class LegacyActionConditionedPVNet(nn.Module):
    def __init__(self, state_dim: int, action_dim: int, hidden: int = 256):
        super().__init__()
        self.hidden = hidden
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
        self.value_head = nn.Linear(hidden, 1)

    def score_actions(self, state_batch: torch.Tensor, action_batch: torch.Tensor):
        s = self.state_net(state_batch)
        a = self.action_net(action_batch)
        s_exp = s.unsqueeze(1).expand(-1, action_batch.shape[1], -1)
        joint = torch.cat([s_exp, a], dim=-1)
        logits = self.policy_net(joint).squeeze(-1)
        values = self.value_head(s).squeeze(-1)
        return logits, values


@dataclass
class Transition:
    state: np.ndarray
    legal_action_feats: np.ndarray
    action: int
    log_prob: float
    value: float
    selected_move: object
    context: dict


class ModelPlayer:
    def __init__(self, model, training: bool = False, storage=None):
        self.model = model
        self.training = training
        self.storage = storage

    def _encode(self, infoset):
        state = encode_state(infoset)
        legal_actions = infoset["legal_actions"]
        action_feats = np.stack([encode_move(a, infoset) for a in legal_actions]).astype(np.float32)
        return state, legal_actions, action_feats

    def act(self, infoset):
        state, legal_actions, action_feats = self._encode(infoset)
        bomb_available = any((a is not None and (a if isinstance(a, Move) else Move(a)).type == "bomb") for a in legal_actions)

        with torch.no_grad():
            state_t = torch.from_numpy(state).float().unsqueeze(0).to(DEVICE)
            acts_t = torch.from_numpy(action_feats).float().unsqueeze(0).to(DEVICE)
            logits, values = self.model.score_actions(state_t, acts_t)
            dist = torch.distributions.Categorical(logits=logits[0])
            idx = dist.sample() if self.training else torch.argmax(logits[0])
            action_idx = int(idx.item())
            log_prob = float(dist.log_prob(idx).item())
            value = float(values[0].item())

        move = legal_actions[action_idx]
        if self.training and self.storage is not None:
            self.storage.append(Transition(
                state=state,
                legal_action_feats=action_feats,
                action=action_idx,
                log_prob=log_prob,
                value=value,
                selected_move=move,
                context={
                    "bomb_available": bomb_available,
                    "opp_card_count": infoset.get("opp_card_count", 5),
                    "current_pot": infoset.get("current_pot", 0),
                    "is_endgame": infoset.get("is_endgame", 0),
                },
            ))
        return move


class LegacyModelPlayer(ModelPlayer):
    def _encode(self, infoset):
        state = legacy_encoder.encode_state(infoset)
        legal_actions = infoset["legal_actions"]
        action_feats = np.stack([legacy_encoder.encode_move(a, infoset) for a in legal_actions]).astype(np.float32)
        return state, legal_actions, action_feats


class CompatModelPlayer(ModelPlayer):
    def _encode(self, infoset):
        state = compat_encoder.encode_state(infoset)
        legal_actions = infoset["legal_actions"]
        action_feats = np.stack([compat_encoder.encode_move(a, infoset) for a in legal_actions]).astype(np.float32)
        return state, legal_actions, action_feats


class LeaguePool:
    def __init__(self):
        self.all: List[nn.Module] = []
        self.recent = deque(maxlen=RECENT_POOL_SIZE)
        self.best: Optional[nn.Module] = None
        self.baseline: Optional[nn.Module] = None
        self.baseline_is_legacy = False
        self.baseline_encoder_kind = "current"
        self.exploiters: List[nn.Module] = []
        self.last_eval = {
            "baseline_wr": 0.0,
            "pool_wr": 0.0,
            "best_wr": 0.0,
            "frontier_wr": 0.0,
            "exploiter_wr": 0.0,
            "per_opp": [],
        }

    def set_baseline(self, model, legacy: bool = False, encoder_kind: Optional[str] = None):
        kind = encoder_kind if encoder_kind is not None else ("legacy" if legacy else "current")
        self.baseline = clone_eval_model(model)
        self.baseline_is_legacy = (kind == "legacy")
        self.baseline_encoder_kind = kind

    def add(self, model):
        snap = clone_eval_model(model)
        self.all.append(snap)
        if len(self.all) > LEAGUE_SIZE:
            self.all.pop(0)
        self.recent.append(snap)
        self.best = snap

    def recent_best(self):
        return self.best if self.best is not None else (self.recent[-1] if self.recent else None)

    def frontier(self):
        frontier = []
        if self.best is not None:
            frontier.append(self.best)
        frontier.extend(list(self.recent)[-FRONTIER_SIZE:])
        return dedup_models(frontier)

    def refresh_exploiters(self, top_k: int = EXPLOITER_POOL_SIZE):
        per_opp = self.last_eval.get("per_opp", [])
        if not per_opp:
            self.exploiters = []
            return
        ranked = sorted(per_opp, key=lambda x: x[1])
        self.exploiters = dedup_models([m for m, _ in ranked[:top_k]])


def dedup_models(models: List[nn.Module]) -> List[nn.Module]:
    seen = set()
    out = []
    for m in models:
        if m is None:
            continue
        ident = id(m)
        if ident not in seen:
            out.append(m)
            seen.add(ident)
    return out


class OpponentWrapper:
    def __init__(self, kind, player):
        self.kind = kind
        self.player = player


def clone_eval_model(model):
    clone = copy.deepcopy(model).to(DEVICE)
    clone.eval()
    return clone


def make_player_for_encoder_kind(model, encoder_kind: str = "current"):
    if encoder_kind == "legacy":
        return LegacyModelPlayer(model)
    if encoder_kind == "compat":
        return CompatModelPlayer(model)
    return ModelPlayer(model)


def make_baseline_player(pool: LeaguePool):
    if pool.baseline is None:
        raise ValueError("Baseline policy is not initialized.")
    return make_player_for_encoder_kind(pool.baseline, pool.baseline_encoder_kind)


def opponent_weights(ep: int, pool: LeaguePool):
    has_exploiters = bool(pool.exploiters)
    has_baseline = pool.baseline is not None
    if ep < 80:
        base = {"random": 0.12, "self": 0.18, "baseline": 0.55, "recent": 0.15, "recent_best": 0.0, "exploiter": 0.0}
    elif ep < 220:
        base = {"random": 0.04, "self": 0.16, "baseline": 0.35, "recent": 0.22, "recent_best": 0.15, "exploiter": 0.08}
    else:
        base = {"random": 0.02, "self": 0.10, "baseline": 0.20, "recent": 0.20, "recent_best": 0.22, "exploiter": 0.26}
    if not has_baseline:
        base["self"] += base["baseline"]
        base["baseline"] = 0.0
    if not has_exploiters:
        base["recent_best"] += base["exploiter"]
        base["exploiter"] = 0.0
    return base


def sample_opponent(pool: LeaguePool, model, ep: int):
    if not pool.all and pool.baseline is None:
        return OpponentWrapper("random", RandomPlayer())
    w = opponent_weights(ep, pool)
    r = random.random()
    for kind in ["random", "self", "baseline", "recent", "recent_best", "exploiter"]:
        prob = w[kind]
        if r < prob:
            if kind == "random":
                return OpponentWrapper("random", RandomPlayer())
            if kind == "self":
                return OpponentWrapper("self", ModelPlayer(model))
            if kind == "baseline" and pool.baseline is not None:
                return OpponentWrapper("baseline", make_baseline_player(pool))
            if kind == "recent" and pool.recent:
                return OpponentWrapper("recent", ModelPlayer(random.choice(list(pool.recent))))
            if kind == "recent_best" and pool.frontier():
                return OpponentWrapper("recent_best", ModelPlayer(random.choice(pool.frontier())))
            if kind == "exploiter" and pool.exploiters:
                return OpponentWrapper("exploiter", ModelPlayer(random.choice(pool.exploiters)))
        r -= prob
    if pool.exploiters:
        return OpponentWrapper("exploiter", ModelPlayer(random.choice(pool.exploiters)))
    if pool.frontier():
        return OpponentWrapper("recent_best", ModelPlayer(pool.recent_best()))
    if pool.baseline is not None:
        return OpponentWrapper("baseline", make_baseline_player(pool))
    return OpponentWrapper("random", RandomPlayer())


def assign_uniform_credit(rewards: List[float], start: int, end: int, amount: float):
    if end <= start:
        return
    per_step = amount / float(end - start)
    for idx in range(start, end):
        rewards[idx] += per_step


def compute_gae(rewards, values):
    advantages = []
    gae = 0.0
    values = values + [0.0]
    for t in reversed(range(len(rewards))):
        delta = rewards[t] + GAMMA * values[t + 1] - values[t]
        gae = delta + GAMMA * LAMBDA * gae
        advantages.insert(0, gae)
    returns = [a + v for a, v in zip(advantages, values[:-1])]
    return advantages, returns


def _capture_endgame_snapshot(env: GameEnv):
    if env.done or env.deck.size() != 0:
        return None
    return {
        "deck_cards": copy.deepcopy(env.deck.cards),
        "hands": copy.deepcopy(env.hands),
        "points": copy.deepcopy(env.points),
        "done": env.done,
        "played_cards": copy.deepcopy(env.played_cards),
        "played_rank_counts": copy.deepcopy(env.played_rank_counts),
        "last_player": env.last_player,
        "last_action_was_pass": env.last_action_was_pass,
        "pass_count": env.pass_count,
        "last_hand_points": env.last_hand_points,
        "last_hand_winner": env.last_hand_winner,
        "current_pot": env.current_pot,
        "face_up": copy.deepcopy(env.face_up),
        "current_player": env.current_player,
        "seed": env.seed,
    }


def _restore_endgame_snapshot(snapshot, players):
    env = GameEnv(players, seed=snapshot.get("seed"), verbose=False)
    env.players = players
    env.deck.cards = copy.deepcopy(snapshot["deck_cards"])
    env.hands = copy.deepcopy(snapshot["hands"])
    env.points = copy.deepcopy(snapshot["points"])
    env.done = snapshot["done"]
    env.played_cards = copy.deepcopy(snapshot["played_cards"])
    env.played_rank_counts = copy.deepcopy(snapshot["played_rank_counts"])
    env.last_player = snapshot["last_player"]
    env.last_action_was_pass = snapshot["last_action_was_pass"]
    env.pass_count = snapshot["pass_count"]
    env.last_hand_points = snapshot["last_hand_points"]
    env.last_hand_winner = snapshot["last_hand_winner"]
    env.current_pot = snapshot["current_pot"]
    env.face_up = copy.deepcopy(snapshot["face_up"])
    env.current_player = snapshot["current_player"]
    return env


def endgame_replay_prob(ep: int, buffer_size: int):
    if buffer_size < ENDGAME_REPLAY_MIN_BUFFER or ep < ENDGAME_REPLAY_START_EP:
        return 0.0
    ramp = min(1.0, (ep - ENDGAME_REPLAY_START_EP) / 900.0)
    return ENDGAME_REPLAY_MAX_PROB * ramp


def collect_rollout(model, pool, episode, endgame_buffer: Optional[Deque[dict]] = None):
    storage: List[Transition] = []
    rewards = []
    player_model = ModelPlayer(model, training=True, storage=storage)
    opp_wrap = sample_opponent(pool, model, episode)
    model_seat = random.randint(0, 1)
    players = [None, None]
    players[model_seat] = player_model
    players[1 - model_seat] = opp_wrap.player

    use_endgame_replay = False
    if endgame_buffer is not None and random.random() < endgame_replay_prob(episode, len(endgame_buffer)):
        snapshot = copy.deepcopy(random.choice(list(endgame_buffer)))
        env = _restore_endgame_snapshot(snapshot, players)
        use_endgame_replay = True
    else:
        env = GameEnv(players, verbose=False)
        env.reset()

    prev_margin = env.points[model_seat] - env.points[1 - model_seat]
    decisions_before = 0
    stats = Counter({
        "decisions": 0,
        "passes": 0,
        "bombs": 0,
        "bomb_opportunities": 0,
        "endgame_replay": int(use_endgame_replay),
        opp_wrap.kind: 1,
        f"seat_{model_seat}": 1,
    })

    while not env.done:
        if endgame_buffer is not None and env.deck.size() == 0:
            snapshot = _capture_endgame_snapshot(env)
            if snapshot is not None:
                endgame_buffer.append(snapshot)
                stats["endgame_snapshot"] += 1

        hand_start = decisions_before
        env.step()
        hand_end = len(storage)

        for i in range(hand_start, hand_end):
            rewards.append(0.0)
            stats["decisions"] += 1
            if storage[i].context.get("bomb_available", False):
                stats["bomb_opportunities"] += 1
            if storage[i].selected_move is None:
                stats["passes"] += 1
            else:
                mv = storage[i].selected_move if isinstance(storage[i].selected_move, Move) else Move(storage[i].selected_move)
                if mv.type == "bomb":
                    stats["bombs"] += 1

        new_margin = env.points[model_seat] - env.points[1 - model_seat]
        margin_delta = (new_margin - prev_margin) / POINT_SCALE
        prev_margin = new_margin
        if hand_end > hand_start:
            assign_uniform_credit(rewards, hand_start, hand_end, margin_delta)
            if env.done:
                terminal = TERMINAL_WIN_BONUS if new_margin > 0 else -TERMINAL_WIN_BONUS
                assign_uniform_credit(rewards, hand_start, hand_end, terminal)
        decisions_before = hand_end

    values = [d.value for d in storage]
    advantages, returns = compute_gae(rewards, values)
    return storage, advantages, returns, stats


def pad_action_sets(action_sets: List[np.ndarray]):
    batch = len(action_sets)
    max_actions = max(arr.shape[0] for arr in action_sets)
    action_dim = action_sets[0].shape[1]
    padded = np.zeros((batch, max_actions, action_dim), dtype=np.float32)
    mask = np.zeros((batch, max_actions), dtype=np.bool_)
    for i, arr in enumerate(action_sets):
        n = arr.shape[0]
        padded[i, :n] = arr
        mask[i, :n] = True
    return padded, mask


def train_step(model, optimizer, batch, entropy_coef):
    states, legal_action_feats, actions, old_log_probs, returns, advantages = batch
    states_t = torch.tensor(np.array(states), dtype=torch.float32, device=DEVICE)
    actions_t = torch.tensor(actions, dtype=torch.long, device=DEVICE)
    old_log_probs_t = torch.tensor(old_log_probs, dtype=torch.float32, device=DEVICE)
    returns_t = torch.tensor(returns, dtype=torch.float32, device=DEVICE)
    advantages_t = torch.tensor(advantages, dtype=torch.float32, device=DEVICE)
    advantages_t = (advantages_t - advantages_t.mean()) / (advantages_t.std() + 1e-8)

    padded_actions, action_mask = pad_action_sets(legal_action_feats)
    action_t = torch.tensor(padded_actions, dtype=torch.float32, device=DEVICE)
    mask_t = torch.tensor(action_mask, dtype=torch.bool, device=DEVICE)

    n = states_t.shape[0]
    idxs = np.arange(n)
    for _ in range(EPOCHS):
        np.random.shuffle(idxs)
        for start in range(0, n, MINIBATCH_SIZE):
            mb = idxs[start:start + MINIBATCH_SIZE]
            logits, values = model.score_actions(states_t[mb], action_t[mb])
            logits = logits.masked_fill(~mask_t[mb], -1e9)
            log_probs = torch.log_softmax(logits, dim=-1)
            probs = torch.softmax(logits, dim=-1)
            new_log_probs = log_probs.gather(1, actions_t[mb].unsqueeze(1)).squeeze(1)
            entropy = -(probs * log_probs).masked_fill(~mask_t[mb], 0.0).sum(dim=-1).mean()

            ratio = torch.exp(new_log_probs - old_log_probs_t[mb])
            surr1 = ratio * advantages_t[mb]
            surr2 = torch.clamp(ratio, 1 - EPS_CLIP, 1 + EPS_CLIP) * advantages_t[mb]
            policy_loss = -torch.min(surr1, surr2).mean()
            value_loss = nn.MSELoss()(values, returns_t[mb])
            loss = policy_loss + VALUE_COEF * value_loss - entropy_coef * entropy

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 0.5)
            optimizer.step()


def play_match(model, opponent_player):
    if random.random() < 0.5:
        env = GameEnv([ModelPlayer(model), opponent_player], verbose=False)
        idx = 0
    else:
        env = GameEnv([opponent_player, ModelPlayer(model)], verbose=False)
        idx = 1
    env.reset()
    while not env.done:
        env.step()
    return env.points[idx] > env.points[1 - idx]


def evaluate_random(model, games=RANDOM_EVAL_GAMES):
    return sum(play_match(model, RandomPlayer()) for _ in range(games)) / games


def evaluate_opponents(model, opponents: List[nn.Module], games_per_opp: int) -> Tuple[float, List[Tuple[nn.Module, float]]]:
    if not opponents:
        return 0.0, []
    per = []
    wins = 0
    total = 0
    for opp in dedup_models(opponents):
        wrapped = ModelPlayer(opp)
        ow = 0
        for _ in range(games_per_opp):
            res = play_match(model, wrapped)
            ow += int(res)
            wins += int(res)
            total += 1
        per.append((opp, ow / games_per_opp))
    return wins / max(1, total), per


def evaluate_best(model, best_model, games=RECENT_BEST_GAMES, encoder_kind: str = "current"):
    if best_model is None:
        return 0.0
    wrapped = make_player_for_encoder_kind(best_model, encoder_kind)
    wins = sum(play_match(model, wrapped) for _ in range(games))
    return wins / games


def evaluate_frontier(model, pool: LeaguePool):
    return evaluate_opponents(model, pool.frontier(), FRONTIER_EVAL_GAMES)[0]


def evaluate_exploiters(model, pool: LeaguePool):
    return evaluate_opponents(model, pool.exploiters, EXPLOITER_EVAL_GAMES)[0] if pool.exploiters else 0.0


def refresh_pool_stats(model, pool: LeaguePool):
    recent = list(pool.recent)
    baseline_wr = evaluate_best(model, pool.baseline, games=BASELINE_EVAL_GAMES, encoder_kind=pool.baseline_encoder_kind) if pool.baseline is not None else 0.0
    pool_wr, per_opp = evaluate_opponents(model, recent, POOL_EVAL_GAMES) if recent else (0.0, [])
    best_wr = evaluate_best(model, pool.recent_best(), games=RECENT_BEST_GAMES) if pool.recent_best() is not None else 0.0
    frontier_wr = evaluate_frontier(model, pool) if pool.all else 0.0
    pool.last_eval = {
        "baseline_wr": baseline_wr,
        "pool_wr": pool_wr,
        "best_wr": best_wr,
        "frontier_wr": frontier_wr,
        "exploiter_wr": pool.last_eval.get("exploiter_wr", 0.0),
        "per_opp": per_opp,
    }
    pool.refresh_exploiters()
    exploiter_wr = evaluate_exploiters(model, pool) if pool.exploiters else frontier_wr
    pool.last_eval["exploiter_wr"] = exploiter_wr
    return pool.last_eval


def robust_pool_score(per_opp: List[Tuple[nn.Module, float]]):
    if not per_opp:
        return 0.0
    wrs = sorted(wr for _, wr in per_opp)
    k = max(1, len(wrs) // 2)
    return float(np.mean(wrs[:k]))


def should_add_snapshot(model, pool: LeaguePool):
    if not pool.all:
        return True
    stats = refresh_pool_stats(model, pool)
    robust_wr = robust_pool_score(stats["per_opp"])
    baseline_gate = stats["baseline_wr"] >= 0.58 if pool.baseline is not None else True
    return (
        baseline_gate and
        stats["best_wr"] >= 0.56 and
        stats["frontier_wr"] >= 0.58 and
        stats["exploiter_wr"] >= 0.55 and
        stats["pool_wr"] >= 0.55 and
        robust_wr >= 0.50
    )


def composite_eval_score(random_wr: float, eval_stats: dict):
    return (
        0.35 * eval_stats.get("baseline_wr", 0.0) +
        0.25 * eval_stats.get("frontier_wr", 0.0) +
        0.20 * eval_stats.get("exploiter_wr", 0.0) +
        0.10 * eval_stats.get("best_wr", 0.0) +
        0.10 * random_wr
    )


def save_checkpoint(model, state_dim: int, action_dim: int, episode: int, path: str):
    torch.save({
        "model_state_dict": model.state_dict(),
        "state_dim": state_dim,
        "action_dim": action_dim,
        "hidden": getattr(model, "hidden", 320),
        "episode": episode,
    }, path)


def load_checkpoint(path: str):
    ckpt = torch.load(path, map_location=DEVICE)
    hidden = ckpt.get("hidden", 320)
    model = ActionConditionedPVNet(ckpt["state_dim"], ckpt["action_dim"], hidden=hidden).to(DEVICE)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    return model, ckpt


def load_legacy_checkpoint(path: str):
    ckpt = torch.load(path, map_location=DEVICE)
    hidden = ckpt.get("hidden", 256)
    model = LegacyActionConditionedPVNet(ckpt["state_dim"], ckpt["action_dim"], hidden=hidden).to(DEVICE)
    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()
    return model, ckpt


def load_exact_baseline_checkpoint(path: str):
    ckpt = torch.load(path, map_location=DEVICE)
    state_dict = ckpt["model_state_dict"]
    if "value_head.weight" in state_dict and "value_head.bias" in state_dict:
        hidden = ckpt.get("hidden", 256)
        model = LegacyActionConditionedPVNet(ckpt["state_dim"], ckpt["action_dim"], hidden=hidden).to(DEVICE)
        encoder_kind = "legacy"
    elif ckpt.get("state_dim") == 133 and ckpt.get("action_dim") == 49:
        hidden = ckpt.get("hidden", 320)
        model = ActionConditionedPVNet(ckpt["state_dim"], ckpt["action_dim"], hidden=hidden).to(DEVICE)
        encoder_kind = "compat"
    else:
        hidden = ckpt.get("hidden", 320)
        model = ActionConditionedPVNet(ckpt["state_dim"], ckpt["action_dim"], hidden=hidden).to(DEVICE)
        encoder_kind = "current"
    model.load_state_dict(state_dict)
    model.eval()
    return model, ckpt, encoder_kind


def load_checkpoint_flexible(path: str, state_dim: int, action_dim: int, hidden: int = 320):
    ckpt = torch.load(path, map_location=DEVICE)
    src_hidden = ckpt.get("hidden", hidden)
    model = ActionConditionedPVNet(state_dim, action_dim, hidden=hidden).to(DEVICE)
    target_sd = model.state_dict()
    src_sd = ckpt["model_state_dict"]
    migrated = []

    for key, src_tensor in src_sd.items():
        if key not in target_sd:
            continue
        tgt_tensor = target_sd[key]
        if src_tensor.shape == tgt_tensor.shape:
            target_sd[key] = src_tensor
            continue
        if src_tensor.ndim != tgt_tensor.ndim:
            continue
        patched = tgt_tensor.clone()
        slices = tuple(slice(0, min(a, b)) for a, b in zip(src_tensor.shape, tgt_tensor.shape))
        patched[slices] = src_tensor[slices]
        target_sd[key] = patched
        migrated.append((key, tuple(src_tensor.shape), tuple(tgt_tensor.shape)))

    model.load_state_dict(target_sd)
    model.eval()
    return model, ckpt, migrated, src_hidden


def initialize_model(state_dim: int, action_dim: int, init_checkpoint: Optional[str] = None):
    if init_checkpoint is None:
        model = ActionConditionedPVNet(state_dim, action_dim).to(DEVICE)
        return model, None

    if not os.path.exists(init_checkpoint):
        raise FileNotFoundError(f"Checkpoint not found: {init_checkpoint}")

    model, ckpt, migrated, src_hidden = load_checkpoint_flexible(init_checkpoint, state_dim, action_dim)
    metadata = {
        "path": init_checkpoint,
        "episode": ckpt.get("episode", "unknown"),
        "migrated": migrated,
        "src_hidden": src_hidden,
        "src_state_dim": ckpt.get("state_dim"),
        "src_action_dim": ckpt.get("action_dim"),
    }
    return model, metadata


def find_default_baseline(path: Optional[str]):
    if path is not None:
        return path
    if os.path.exists(DEFAULT_BASELINE_CHECKPOINT):
        return DEFAULT_BASELINE_CHECKPOINT
    return None


def maybe_load_exact_baseline(path: Optional[str]):
    if path is None:
        return None, None
    if not os.path.exists(path):
        raise FileNotFoundError(f"Baseline checkpoint not found: {path}")
    model, ckpt, encoder_kind = load_exact_baseline_checkpoint(path)
    meta = {
        "path": path,
        "episode": ckpt.get("episode", "unknown"),
        "state_dim": ckpt.get("state_dim"),
        "action_dim": ckpt.get("action_dim"),
        "legacy": encoder_kind == "legacy",
        "encoder_kind": encoder_kind,
    }
    return model, meta


def playtest(checkpoint_path: str = CHECKPOINT_BEST, bot_first: bool = False):
    model, ckpt = load_checkpoint(checkpoint_path)
    human = HumanPlayer()
    bot = ModelPlayer(model, training=False)
    players = [bot, human] if bot_first else [human, bot]
    env = GameEnv(players, verbose=True)
    env.reset()

    print(f"Loaded checkpoint: {checkpoint_path}")
    print(f"Episode saved: {ckpt.get('episode', 'unknown')}")

    step = 0
    while not env.done:
        print(f"\n=== STEP {step} ===")
        print("Points:", env.points)
        print("Deck size:", len(env.deck.cards))
        print("Current player:", env.current_player)
        env.step()
        step += 1

    print("\n=== GAME OVER ===")
    print("Final points:", env.points)


def main(init_checkpoint: Optional[str] = None, baseline_checkpoint: Optional[str] = None, episodes: int = 1000, rollouts_per_batch: int = ROLLOUTS_PER_BATCH):
    random.seed(0)
    np.random.seed(0)
    torch.manual_seed(0)

    dummy_env = GameEnv([RandomPlayer(), RandomPlayer()], verbose=False)
    dummy_infoset = dummy_env._get_infoset(None, None)
    state_dim = len(encode_state(dummy_infoset))
    action_dim = move_feature_dim()

    model, init_meta = initialize_model(state_dim, action_dim, init_checkpoint)
    optimizer = optim.Adam(model.parameters(), lr=LR)
    pool = LeaguePool()
    endgame_buffer: Deque[dict] = deque(maxlen=ENDGAME_REPLAY_BUFFER_SIZE)

    resolved_baseline = find_default_baseline(baseline_checkpoint)
    baseline_model, baseline_meta = maybe_load_exact_baseline(resolved_baseline)
    if baseline_model is not None:
        pool.set_baseline(baseline_model, legacy=baseline_meta["legacy"], encoder_kind=baseline_meta["encoder_kind"])
    else:
        pool.set_baseline(model)

    if init_meta is not None:
        print(
            f"Initialized from {init_meta['path']} | episode={init_meta['episode']} "
            f"| old_dims=({init_meta['src_state_dim']}, {init_meta['src_action_dim']}) "
            f"| new_dims=({state_dim}, {action_dim}) | migrated_tensors={len(init_meta['migrated'])}",
            flush=True,
        )
    if baseline_meta is not None:
        print(
            f"Using exact external baseline from {baseline_meta['path']} | episode={baseline_meta['episode']} "
            f"| dims=({baseline_meta['state_dim']}, {baseline_meta['action_dim']})",
            flush=True,
        )
    else:
        print("No external baseline checkpoint found; using frozen initialization as baseline.", flush=True)

    total_decisions = 0
    best_eval_score = float("-inf")
    for ep in range(episodes):
        entropy_coef = max(ENTROPY_END, ENTROPY_START * (0.9985 ** ep))

        if ep > 0 and ep % SNAPSHOT_EVAL_FREQ == 0:
            if len(pool.all) < 3 or should_add_snapshot(model, pool):
                pool.add(model)
                refresh_pool_stats(model, pool)
                added_snapshot = True
            else:
                added_snapshot = False
        else:
            added_snapshot = False
            if ep % EVAL_PRINT_FREQ == 0:
                refresh_pool_stats(model, pool)

        batch_storage, batch_adv, batch_ret = [], [], []
        stats = Counter()
        for _ in range(rollouts_per_batch):
            s, adv, ret, rollout_stats = collect_rollout(model, pool, ep, endgame_buffer=endgame_buffer)
            batch_storage += s
            batch_adv += adv
            batch_ret += ret
            stats.update(rollout_stats)

        states = [d.state for d in batch_storage]
        action_feats = [d.legal_action_feats for d in batch_storage]
        actions = [d.action for d in batch_storage]
        logp = [d.log_prob for d in batch_storage]
        train_step(model, optimizer, (states, action_feats, actions, logp, batch_ret, batch_adv), entropy_coef)

        total_decisions += stats["decisions"]
        pass_rate = stats["passes"] / max(1, stats["decisions"])
        bomb_rate = stats["bombs"] / max(1, stats["decisions"])
        bomb_avail_use = stats["bombs"] / max(1, stats["bomb_opportunities"])

        if ep % 10 == 0:
            print(
                f"Episode {ep} | Avg Return: {np.mean(batch_ret):.2f} | Decisions: {total_decisions} "
                f"| Pass: {pass_rate:.2f} | Bomb: {bomb_rate:.2f} | BombAvailUse: {bomb_avail_use:.2f} "
                f"| EGReplay: {stats['endgame_replay']} | EGBuffer: {len(endgame_buffer)}",
                flush=True,
            )
        if ep % EVAL_PRINT_FREQ == 0:
            save_checkpoint(model, state_dim, action_dim, ep, CHECKPOINT_LATEST)
            wr_r = evaluate_random(model)
            eval_stats = pool.last_eval
            score = composite_eval_score(wr_r, eval_stats)
            if score > best_eval_score:
                save_checkpoint(model, state_dim, action_dim, ep, CHECKPOINT_BEST)
                best_eval_score = score
            mix = {k: stats[k] for k in ["random", "self", "baseline", "recent", "recent_best", "exploiter", "seat_0", "seat_1"] if stats[k] > 0}
            print(
                f"Eval | Random WR: {wr_r:.2f} | Baseline WR: {eval_stats['baseline_wr']:.2f} "
                f"| Pool WR: {eval_stats['pool_wr']:.2f} | Best WR: {eval_stats['best_wr']:.2f} "
                f"| Frontier WR: {eval_stats['frontier_wr']:.2f} | Exploiter WR: {eval_stats['exploiter_wr']:.2f} "
                f"| League Size: {len(pool.all)} | Added Snapshot: {added_snapshot} | BestScore: {best_eval_score:.3f}",
                flush=True,
            )
            print(f"Opponent mix: {mix}", flush=True)

    save_checkpoint(model, state_dim, action_dim, episodes - 1, CHECKPOINT_LATEST)


def parse_train_args(argv: List[str]):
    parser = argparse.ArgumentParser()
    parser.add_argument("init_checkpoint", nargs="?", default=None)
    parser.add_argument("--baseline-checkpoint", default=None)
    parser.add_argument("--episodes", type=int, default=1000)
    parser.add_argument("--rollouts", type=int, default=ROLLOUTS_PER_BATCH)
    return parser.parse_args(argv)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "playtest":
        checkpoint = sys.argv[2] if len(sys.argv) >= 3 else CHECKPOINT_BEST
        bot_first = len(sys.argv) >= 4 and sys.argv[3] == "bot_first"
        playtest(checkpoint, bot_first=bot_first)
    else:
        args = parse_train_args(sys.argv[1:])
        main(
            init_checkpoint=args.init_checkpoint,
            baseline_checkpoint=args.baseline_checkpoint,
            episodes=args.episodes,
            rollouts_per_batch=args.rollouts,
        )
