from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from game import Card, GameEnv, Move, RandomPlayer
from policy_loader import LoadedPolicy


def card_key(card: Card) -> Tuple[int, Optional[str]]:
    return (card.rank, card.suit)


def rank_text(rank: int) -> str:
    mapping = {11: "J", 12: "Q", 13: "K", 14: "A", 17: "2", 20: "SJ", 30: "BJ"}
    return mapping.get(rank, str(rank))


def suit_symbol(suit: Optional[str]) -> str:
    return {"H": "♥", "D": "♦", "C": "♣", "S": "♠", None: ""}.get(suit, "")


def card_label(card: Card) -> str:
    if card.rank == 20:
        return "SJ"
    if card.rank == 30:
        return "BJ"
    return f"{rank_text(card.rank)}{suit_symbol(card.suit)}"


def move_text(move) -> str:
    if move is None:
        return "PASS"
    cards = move.cards if isinstance(move, Move) else move
    m = move if isinstance(move, Move) else Move(move)
    joined = " ".join(card_label(c) for c in cards)
    return f"{m.type.upper()}  {joined}"


class BotPlayer:
    def __init__(self, policy: LoadedPolicy):
        self.policy = policy

    def act(self, infoset):
        return self.policy.choose_action(infoset)["move"]


@dataclass
class WebMatchController:
    policy: LoadedPolicy
    bot_first: bool = False
    seed: Optional[int] = None
    bot: BotPlayer = field(init=False)
    human_seat: int = field(init=False, default=0)
    bot_seat: int = field(init=False, default=1)
    env: Optional[GameEnv] = field(init=False, default=None)
    hand_type: Optional[str] = field(init=False, default=None)
    last_move: Optional[Move] = field(init=False, default=None)
    log: List[str] = field(init=False, default_factory=list)
    human_wins: int = field(init=False, default=0)
    bot_wins: int = field(init=False, default=0)
    last_result_counted: bool = field(init=False, default=False)
    game_id: str = field(init=False, default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self):
        self.bot = BotPlayer(self.policy)
        self.reset(initial=True)

    def _seat_name(self, seat: int) -> str:
        return "you" if seat == self.human_seat else "bot"

    def reset(self, initial: bool = False):
        self.env = GameEnv([RandomPlayer(), RandomPlayer()], seed=self.seed, verbose=False)
        starter_seat = self.env.current_player
        if self.bot_first:
            self.bot_seat = starter_seat
            self.human_seat = 1 - starter_seat
        else:
            self.human_seat = starter_seat
            self.bot_seat = 1 - starter_seat
        self.hand_type = None
        self.last_move = None
        self.log = ["Begin", "Bot starts" if self.bot_first else "You start"]
        self.last_result_counted = False
        self.game_id = uuid.uuid4().hex
        if not initial:
            self.autoplay_until_human()

    def current_infoset(self, concrete_for_human: bool = False):
        use_concrete = concrete_for_human and self.env.current_player == self.human_seat
        return self.env._get_infoset(self.hand_type, self.last_move, concrete_same_rank_choices=use_concrete)

    def is_human_turn(self) -> bool:
        return (not self.env.done) and self.env.current_player == self.human_seat

    def is_bot_turn(self) -> bool:
        return (not self.env.done) and self.env.current_player == self.bot_seat

    def legal_actions(self, concrete_for_human: bool = False):
        return self.current_infoset(concrete_for_human=concrete_for_human)["legal_actions"]

    def _apply_endgame_bonus_and_penalty(self, winner: int):
        loser = 1 - winner
        loser_penalty = self.env._count_points(self.env.hands[loser])
        self.env.points[winner] += 20
        self.env.points[loser] -= loser_penalty
        self.env.current_pot = 0
        self.env.done = True
        self.env.current_player = winner
        self.log.append(f"End bonus: {self._seat_name(winner)} (+20)")
        self.log.append(f"Remaining hand penalty: {self._seat_name(loser)} (-{loser_penalty})")

    def _finalize_hand(self, winner: int):
        self.env.points[winner] += self.env.current_pot
        self.env.last_hand_points = self.env.current_pot
        self.env.last_hand_winner = winner
        self.log.append(f"Hand winner: {self._seat_name(winner)} (+{self.env.current_pot})")

        if self.env.deck.size() == 0 and len(self.env.hands[winner]) == 0:
            self.log.append(f"{self._seat_name(winner)} empties hand and ends the game.")
            self._apply_endgame_bonus_and_penalty(winner)
        else:
            self.env.current_pot = 0
            if not self.env.done:
                self.env._draw_phase(winner)
                if self.env._check_done():
                    self.env.done = True
            self.env.current_player = winner

        self.hand_type = None
        self.last_move = None
        self.env.last_player = None
        self.env.last_action_was_pass = False
        self.env.pass_count = 0

    def apply_action(self, action):
        if self.env.done:
            return
        p = self.env.current_player
        infoset = self.current_infoset(concrete_for_human=(p == self.human_seat))
        legal_actions = infoset["legal_actions"]
        if action not in legal_actions:
            raise ValueError("Illegal action selected.")

        if action is None:
            self.log.append(f"{self._seat_name(p)} PASS")
            self.env.last_action_was_pass = True
            self.env.pass_count += 1
            winner = self.env.last_player
            if winner is None:
                raise RuntimeError("Pass with no previous leader is invalid.")
            self._finalize_hand(winner)
            self._count_finished_game_if_needed()
            return

        move = Move(action)
        if self.hand_type is None:
            self.hand_type = move.type

        gained = self.env._count_points(action)
        self.env.current_pot += gained
        actor = self._seat_name(p)
        verb = "play" if actor == "you" else "plays"
        self.log.append(f"{actor} {verb} {move_text(action)} (+{gained})")

        self.env.last_player = p
        self.env.last_action_was_pass = False
        self.env.pass_count = 0
        self.last_move = move

        self.env._remove_cards(p, action)
        for c in action:
            self.env.played_cards.append(c)
            self.env.played_rank_counts[c.rank] += 1

        if self.env.deck.size() == 0 and len(self.env.hands[p]) == 0:
            winner = p
            self.env.points[winner] += self.env.current_pot
            self.env.last_hand_points = self.env.current_pot
            self.env.last_hand_winner = winner
            self.log.append(f"{self._seat_name(winner)} empties hand and ends the game.")
            self._apply_endgame_bonus_and_penalty(winner)
            self._count_finished_game_if_needed()
            return

        self.env.current_player = 1 - p

    def step_bot_once(self) -> bool:
        if not self.is_bot_turn() or self.env.done:
            return False
        infoset = self.current_infoset()
        action = self.bot.act(infoset)
        self.apply_action(action)
        return True

    def autoplay_until_human(self, max_actions: int = 400) -> int:
        acted = 0
        while not self.env.done and acted < max_actions and self.is_bot_turn():
            self.step_bot_once()
            acted += 1
        self._count_finished_game_if_needed()
        return acted

    def _count_finished_game_if_needed(self):
        if not self.env.done or self.last_result_counted:
            return
        human_points = self.env.points[self.human_seat]
        bot_points = self.env.points[self.bot_seat]
        if human_points > bot_points:
            self.human_wins += 1
        elif bot_points > human_points:
            self.bot_wins += 1
        self.last_result_counted = True

    def human_play_by_index(self, action_index: int):
        if not self.is_human_turn() or self.env.done:
            raise ValueError("It is not the human turn.")
        legal = self.legal_actions(concrete_for_human=True)
        if action_index < 0 or action_index >= len(legal):
            raise IndexError("Action index out of range.")
        self.apply_action(legal[action_index])
        self.autoplay_until_human()

    def _serialize_card(self, card: Card) -> Dict[str, object]:
        return {
            "rank": card.rank,
            "suit": card.suit,
            "label": card_label(card),
            "key": f"{card.rank}:{card.suit or ''}",
            "color": "red" if card.suit in {"H", "D"} else "black",
        }

    def _serialize_action(self, action, idx: int) -> Dict[str, object]:
        if action is None:
            return {
                "index": idx,
                "is_pass": True,
                "type": "pass",
                "cards": [],
                "label": "PASS",
                "key": "PASS",
            }
        move = action if isinstance(action, Move) else Move(action)
        cards = move.cards if isinstance(action, Move) else action
        return {
            "index": idx,
            "is_pass": False,
            "type": move.type,
            "cards": [self._serialize_card(c) for c in cards],
            "label": move_text(action),
            "key": "|".join(sorted(f"{c.rank}:{c.suit or ''}" for c in cards)),
        }

    def _result_text(self) -> str:
        if not self.env.done:
            return ""
        human_points = self.env.points[self.human_seat]
        bot_points = self.env.points[self.bot_seat]
        if human_points > bot_points:
            return "Final Result: You win"
        if bot_points > human_points:
            return "Final Result: Bot wins"
        return "Final Result: Tie game"

    def state_payload(self) -> Dict[str, object]:
        env = self.env
        human_hand = sorted(env.hands[self.human_seat], key=lambda c: (c.rank, c.suit or ""))
        legal_actions = self.legal_actions(concrete_for_human=True) if self.is_human_turn() and not env.done else []
        serialized_legal = [self._serialize_action(a, idx) for idx, a in enumerate(legal_actions)]
        playable_keys = sorted({card["key"] for action in serialized_legal if not action["is_pass"] for card in action["cards"]})

        return {
            "game_id": self.game_id,
            "bot_first": self.bot_first,
            "status": f"You {env.points[self.human_seat]} · Bot {env.points[self.bot_seat]} · Pot {env.current_pot}",
            "scores": {
                "you": env.points[self.human_seat],
                "bot": env.points[self.bot_seat],
                "pot": env.current_pot,
            },
            "wins": {
                "you": self.human_wins,
                "bot": self.bot_wins,
            },
            "turn": "you" if self.is_human_turn() else "bot" if self.is_bot_turn() else "game_over",
            "hand_type": self.hand_type or "open",
            "deck_size": env.deck.size(),
            "opponent_card_count": len(env.hands[self.bot_seat]),
            "human_hand": [self._serialize_card(c) for c in human_hand],
            "legal_actions": serialized_legal,
            "playable_card_keys": playable_keys,
            "last_move": None if self.last_move is None else self._serialize_action(self.last_move, -1),
            "result": self._result_text(),
            "done": env.done,
            "log": self.log[-250:],
            "meta": {
                "policy_path": self.policy.path,
                "encoder": self.policy.encoder_spec.name,
                "state_dim": self.policy.encoder_spec.state_dim,
                "action_dim": self.policy.encoder_spec.action_dim,
                "value_head_kind": self.policy.value_head_kind,
                "saved_episode": self.policy.checkpoint.get("episode", "unknown"),
            },
        }


class SessionStore:
    def __init__(self, policy: LoadedPolicy):
        self.policy = policy
        self.sessions: Dict[str, WebMatchController] = {}

    def create(self, bot_first: bool = False, seed: Optional[int] = None) -> WebMatchController:
        controller = WebMatchController(policy=self.policy, bot_first=bot_first, seed=seed)
        controller.autoplay_until_human()
        self.sessions[controller.game_id] = controller
        return controller

    def get(self, session_id: str) -> WebMatchController:
        if session_id not in self.sessions:
            raise KeyError("Unknown session id.")
        return self.sessions[session_id]
