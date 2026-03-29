from __future__ import annotations

import argparse
import math
import random
import tkinter as tk
from tkinter import messagebox
from typing import Dict, List, Optional, Sequence, Tuple

from game import Card, GameEnv, Move, RandomPlayer
from policy_loader import LoadedPolicy, load_policy, smoke_test_checkpoint

BOT_THINK_MS = 350
CARD_W = 100
CARD_H = 140
CARD_LIFT_PAD_TOP = 18
CARD_LIFT_PAD_BOTTOM = 10
CARD_WIDGET_H = CARD_H + CARD_LIFT_PAD_TOP + CARD_LIFT_PAD_BOTTOM
CARD_SPACING = 108
OPP_SPACING = 108
TABLE_GREEN = "#0d3f31"
TABLE_DARK = "#081d17"
TABLE_GLOW = "#1f6d56"
PANEL_BG = "#10291f"
PANEL_ALT = "#153528"
LIGHT_TEXT = "#f9f2d7"
MUTED_TEXT = "#c9bea0"
ACCENT = "#f4c75b"
ACCENT_DARK = "#b88928"
PLAYABLE_BORDER = "#84ef9b"
SELECTED_BORDER = "#ffd76e"
INACTIVE_BORDER = "#45614f"
RED_SUIT = "#c74343"
BLACK_SUIT = "#1c1c1c"
CARD_FACE = "#fff9ec"
CARD_BACK = "#21395e"
CARD_BACK_ALT = "#314f7e"
BUTTON_TEXT = "#101010"
BUTTON_DISABLED_TEXT = "#6b6b6b"
BUTTON_DISABLED_BG = "#cec5b5"
PASS_BG = "#d96b6b"
PASS_ACTIVE_BG = "#c85e5e"
CLEAR_BG = "#91a090"
CLEAR_ACTIVE_BG = "#7f8d7e"
PIXEL_EDGE = "#2e1d0b"
SHADOW = "#000000"

FONT_TITLE = "Trebuchet MS"
FONT_UI = "Trebuchet MS"
FONT_CARD = "Helvetica"
FONT_MONO = "Menlo"

SUIT_SYMBOLS = {
    "H": "♥",
    "D": "♦",
    "C": "♣",
    "S": "♠",
    None: "",
}
RANK_LABELS = {
    11: "J",
    12: "Q",
    13: "K",
    14: "A",
    17: "2",
    20: "SJ",
    30: "BJ",
}
PIP_COUNTS = {
    3: 3,
    4: 4,
    5: 5,
    6: 6,
    7: 7,
    8: 8,
    9: 9,
    10: 10,
    14: 1,
    17: 2,
}


def card_key(card: Card) -> Tuple[int, Optional[str]]:
    return (card.rank, card.suit)



def rank_text(rank: int) -> str:
    return RANK_LABELS.get(rank, str(rank))



def card_text(card: Card) -> str:
    if card.rank == 20:
        return "SJ"
    if card.rank == 30:
        return "BJ"
    return f"{rank_text(card.rank)}{SUIT_SYMBOLS.get(card.suit, '')}"



def suit_color(card: Card) -> str:
    return RED_SUIT if card.suit in {"H", "D"} else BLACK_SUIT



def format_move(move) -> str:
    if move is None:
        return "PASS"
    cards = move.cards if isinstance(move, Move) else move
    m = move if isinstance(move, Move) else Move(move)
    card_texts = " ".join(card_text(c) for c in cards)
    return f"{m.type.upper():8s}  {card_texts}"


def format_move_browser(move) -> str:
    if move is None:
        return "PASS"
    cards = move.cards if isinstance(move, Move) else move
    m = move if isinstance(move, Move) else Move(move)
    card_texts = " ".join(card_text(c) for c in cards)
    return f"{m.type.upper()}  {card_texts}"



def hex_to_rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))



def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb



def blend(a: str, b: str, t: float) -> str:
    ra = hex_to_rgb(a)
    rb = hex_to_rgb(b)
    out = tuple(max(0, min(255, round(ra[i] * (1 - t) + rb[i] * t))) for i in range(3))
    return rgb_to_hex(out)



def pip_positions(count: int) -> List[Tuple[float, float, int]]:
    # x, y are normalized center positions; rotation flips lower-half pips upside down.
    layouts = {
        1: [(0.50, 0.50, 0)],
        2: [(0.50, 0.30, 0), (0.50, 0.70, 180)],
        3: [(0.50, 0.24, 0), (0.50, 0.50, 0), (0.50, 0.76, 180)],
        4: [(0.35, 0.30, 0), (0.65, 0.30, 0), (0.35, 0.70, 180), (0.65, 0.70, 180)],
        5: [(0.35, 0.28, 0), (0.65, 0.28, 0), (0.50, 0.50, 0), (0.35, 0.72, 180), (0.65, 0.72, 180)],
        6: [(0.35, 0.25, 0), (0.65, 0.25, 0), (0.35, 0.50, 0), (0.65, 0.50, 0), (0.35, 0.75, 180), (0.65, 0.75, 180)],
        7: [(0.35, 0.22, 0), (0.65, 0.22, 0), (0.50, 0.38, 0), (0.35, 0.50, 0), (0.65, 0.50, 0), (0.35, 0.76, 180), (0.65, 0.76, 180)],
        8: [(0.35, 0.20, 0), (0.65, 0.20, 0), (0.35, 0.37, 0), (0.65, 0.37, 0), (0.35, 0.63, 180), (0.65, 0.63, 180), (0.35, 0.80, 180), (0.65, 0.80, 180)],
        9: [(0.35, 0.18, 0), (0.65, 0.18, 0), (0.35, 0.34, 0), (0.65, 0.34, 0), (0.50, 0.50, 0), (0.35, 0.66, 180), (0.65, 0.66, 180), (0.35, 0.82, 180), (0.65, 0.82, 180)],
        10: [(0.34, 0.22, 0), (0.66, 0.22, 0), (0.34, 0.36, 0), (0.66, 0.36, 0), (0.34, 0.50, 0), (0.66, 0.50, 0), (0.34, 0.64, 180), (0.66, 0.64, 180), (0.34, 0.78, 180), (0.66, 0.78, 180)],
    }
    return layouts.get(count, [(0.50, 0.50, 0)])


def draw_card_back(canvas, x: float, y: float, w: float, h: float, *, title_font=None, symbol_font=None, footer_font=None):
    scale = min(w / CARD_W, h / CARD_H)
    cut_outer = max(6, round(10 * scale))
    cut_inner = max(5, round(8 * scale))
    outer_outline = "#9bb8ea"
    inner_fill = blend(CARD_BACK_ALT, CARD_BACK, 0.15)
    inner_outline = blend("#8fb7ff", CARD_BACK, 0.35)

    def pixel_panel(x1, y1, x2, y2, cut, **kwargs):
        points = [
            x1 + cut, y1,
            x2 - cut, y1,
            x2, y1 + cut,
            x2, y2 - cut,
            x2 - cut, y2,
            x1 + cut, y2,
            x1, y2 - cut,
            x1, y1 + cut,
        ]
        canvas.create_polygon(points, smooth=False, **kwargs)

    pixel_panel(x, y, x + w, y + h, cut_outer, fill=CARD_BACK, outline=outer_outline, width=max(1, round(2 * scale)))
    pad_x = max(8, round(8 * scale))
    pad_y = max(10, round(8 * scale))
    pixel_panel(x + pad_x, y + pad_y, x + w - pad_x, y + h - pad_y, cut_inner, fill=inner_fill, outline=inner_outline, width=max(1, round(1 * scale)))

    bar_w = max(8, round(11 * scale))
    bar_gap = max(10, round(16 * scale))
    group_w = 3 * bar_w + 2 * bar_gap
    start_x = x + (w - group_w) / 2
    band_top = y + max(18, round(27 * scale))
    band_bottom = y + h - max(18, round(27 * scale))
    for band in range(3):
        x1 = start_x + band * (bar_w + bar_gap)
        canvas.create_rectangle(x1, band_top, x1 + bar_w, band_bottom, fill=blend(CARD_BACK_ALT, "#ffffff", 0.06), outline="")

    title_font = title_font or (FONT_TITLE, max(8, round(10 * scale)), 'bold')
    symbol_font = symbol_font or (FONT_CARD, max(12, round(15 * scale)), 'bold')
    footer_font = footer_font or (FONT_UI, max(8, round(10 * scale)), 'bold')
    canvas.create_text(x + w / 2, y + h / 2 + -8 * scale, text='♠ ♥ ♣ ♦', fill='#f5efe1', font=symbol_font)
    canvas.create_text(x + w / 2, y + h / 2 + 16 * scale, text='5 · 10 · K', fill='#d4deff', font=footer_font)



class BotPlayer:
    def __init__(self, policy: LoadedPolicy):
        self.policy = policy

    def act(self, infoset):
        return self.policy.choose_action(infoset)["move"]


class MatchController:
    def __init__(self, checkpoint_path: str, bot_first: bool = False, seed: Optional[int] = None):
        self.policy = load_policy(checkpoint_path)
        self.bot_first = bot_first
        self.seed = seed
        self.bot = BotPlayer(self.policy)
        self.human_seat = 0
        self.bot_seat = 1
        self.env: Optional[GameEnv] = None
        self.hand_type = None
        self.last_move = None
        self.log: List[str] = []
        self.human_wins = 0
        self.bot_wins = 0
        self.reset()

    def _seat_name(self, seat: int) -> str:
        return "you" if seat == self.human_seat else "bot"

    def set_bot_first(self, bot_first: bool):
        self.bot_first = bot_first
        self.reset()

    def reset(self):
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
        self.log = []
        face_up = f"Begin"
        starter = "Bot starts" if self.bot_first else "You start"
        self.log.extend([face_up, starter])

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
            return

        move = Move(action)
        if self.hand_type is None:
            self.hand_type = move.type

        gained = self.env._count_points(action)
        self.env.current_pot += gained
        actor = self._seat_name(p)
        verb = "play" if actor == "you" else "plays"
        self.log.append(f"{actor} {verb} {format_move(action)} (+{gained})")

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
            return

        self.env.current_player = 1 - p

    def step_bot_once(self) -> bool:
        if not self.is_bot_turn() or self.env.done:
            return False
        infoset = self.current_infoset()
        action = self.bot.act(infoset)
        self.apply_action(action)
        return True

    def autoplay_nonhuman_turns(self, fallback_random_for_human: bool = False, max_actions: int = 400) -> int:
        acted = 0
        while not self.env.done and acted < max_actions:
            if self.is_bot_turn():
                self.step_bot_once()
                acted += 1
                continue
            if fallback_random_for_human:
                infoset = self.current_infoset()
                action = random.choice(infoset["legal_actions"])
                self.apply_action(action)
                acted += 1
                continue
            break
        return acted


class CardWidget(tk.Canvas):
    def __init__(self, master, card: Card, command, face_up: bool = True):
        super().__init__(
            master,
            width=CARD_W,
            height=CARD_WIDGET_H,
            bg=master.cget("bg"),
            highlightthickness=0,
            bd=0,
        )
        self.card = card
        self.command = command
        self.face_up = face_up
        self.is_playable = False
        self.is_selected = False
        self.is_hovered = False
        self.float_offset = 0.0
        self.target_offset = 0.0
        self.anim_job = None
        self.configure(cursor="hand2" if command is not None else "arrow")
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self._redraw()

    def _on_click(self, _event):
        if self.command is not None:
            self.command(self.card)

    def _on_enter(self, _event):
        if self.command is None:
            return
        self.is_hovered = True
        self._animate_to(self._desired_offset())

    def _on_leave(self, _event):
        if self.command is None:
            return
        self.is_hovered = False
        self._animate_to(self._desired_offset())

    def set_state(self, playable: bool, selected: bool):
        self.is_playable = playable
        self.is_selected = selected
        self._animate_to(self._desired_offset(), immediate=True)

    def _desired_offset(self) -> float:
        offset = 0.0
        if self.is_selected:
            offset -= 6.0
        if self.is_hovered:
            offset -= 7.0
        return offset

    def _animate_to(self, target: float, immediate: bool = False):
        self.target_offset = target
        if immediate:
            self.float_offset = target
            self._redraw()
            return
        if self.anim_job is None:
            self.anim_job = self.after(16, self._tick_animation)

    def _tick_animation(self):
        delta = self.target_offset - self.float_offset
        if abs(delta) < 0.4:
            self.float_offset = self.target_offset
            self.anim_job = None
            self._redraw()
            return
        self.float_offset += delta * 0.35
        self._redraw()
        self.anim_job = self.after(16, self._tick_animation)

    def _redraw(self):
        self.delete("all")
        yoff = self.float_offset + CARD_LIFT_PAD_TOP
        shadow_depth = 8 if (self.is_hovered or self.is_selected) else 6
        self._pixel_panel(12, 14 + yoff + shadow_depth, CARD_W - 8, CARD_H - 4 + yoff + shadow_depth, 10, fill="#06130f", outline="")

        if not self.face_up:
            draw_card_back(self, 8, 8 + yoff, CARD_W - 16, CARD_H - 16)
            return

        outline = SELECTED_BORDER if self.is_selected else PLAYABLE_BORDER if self.is_playable else INACTIVE_BORDER
        line_width = 4 if self.is_selected else 3 if self.is_playable else 2
        inner_top = 8 + yoff
        inner_bottom = CARD_H - 8 + yoff
        self._pixel_panel(8, inner_top, CARD_W - 8, inner_bottom, 10, fill=CARD_FACE, outline=outline, width=line_width)
        self._pixel_panel(14, 14 + yoff, CARD_W - 14, CARD_H - 14 + yoff, 8, fill="", outline=blend(outline, CARD_FACE, 0.55), width=1)

        if self.is_playable:
            glow = blend(PLAYABLE_BORDER, CARD_FACE, 0.70)
            self._pixel_panel(11, 11 + yoff, CARD_W - 11, CARD_H - 11 + yoff, 9, fill="", outline=glow, width=1)

        color = suit_color(self.card)
        rank_label = rank_text(self.card.rank)
        suit_label = SUIT_SYMBOLS.get(self.card.suit, "")
        top_icon = suit_label if suit_label else "★"
        top_icon_color = color if suit_label else ACCENT_DARK
        self.create_text(22, 22 + yoff, text=rank_label, fill=color, font=(FONT_CARD, 14, "bold"))
        self.create_text(22, 40 + yoff, text=top_icon, fill=top_icon_color, font=(FONT_CARD, 13, "bold"))
        self.create_text(CARD_W - 22, CARD_H - 22 + yoff, text=rank_label, fill=color, font=(FONT_CARD, 14, "bold"), angle=180)
        self.create_text(CARD_W - 22, CARD_H - 40 + yoff, text=top_icon, fill=top_icon_color, font=(FONT_CARD, 13, "bold"), angle=180)

        if self.card.rank in {11, 12, 13}:
            self._draw_face_art(color, yoff)
        elif self.card.rank in {20, 30}:
            self._draw_joker_art(yoff)
        else:
            self._draw_pips(color, yoff)

    def _draw_pips(self, color: str, yoff: float):
        count = PIP_COUNTS.get(self.card.rank, 1)
        pip = SUIT_SYMBOLS.get(self.card.suit, "•")
        pip_font_size = 19 if count == 10 else 20
        for xn, yn, angle in pip_positions(count):
            x = 10 + xn * (CARD_W - 20)
            y = 10 + yn * (CARD_H - 20) + yoff
            self.create_text(x, y, text=pip, fill=color, font=(FONT_CARD, pip_font_size, "bold"), angle=angle)

    def _draw_face_art(self, color: str, yoff: float):
        suit = SUIT_SYMBOLS.get(self.card.suit, "")
        top = 36 + yoff
        bottom = CARD_H - 36 + yoff
        mid = (top + bottom) / 2
        frame_fill = blend(CARD_FACE, color, 0.08)
        frame_outline = blend(color, CARD_FACE, 0.38)
        self._pixel_panel(28, top, CARD_W - 28, bottom, 9, fill=frame_fill, outline=frame_outline, width=2)
        self._pixel_panel(36, top + 8, CARD_W - 36, bottom - 8, 7, fill=blend(CARD_FACE, ACCENT, 0.08), outline="", width=1)
        self.create_line(38, mid - 18, CARD_W - 38, mid - 18, fill=blend(frame_outline, CARD_FACE, 0.2), width=2)
        self.create_line(38, mid + 18, CARD_W - 38, mid + 18, fill=blend(frame_outline, CARD_FACE, 0.2), width=2)
        self.create_polygon(37, mid, 47, mid - 20, 47, mid + 20, fill=blend(color, CARD_FACE, 0.25), outline="")
        self.create_polygon(CARD_W - 37, mid, CARD_W - 47, mid - 20, CARD_W - 47, mid + 20, fill=blend(color, CARD_FACE, 0.25), outline="")
        self.create_text(CARD_W / 2, top + 14, text=suit, fill=color, font=(FONT_CARD, 16, "bold"))
        emblem = "♞" if self.card.rank == 11 else "♛" if self.card.rank == 12 else "♚"
        self.create_text(CARD_W / 2, mid - 6, text=emblem, fill=ACCENT_DARK, font=(FONT_CARD, 24, "bold"))
        jewel_y = mid + 20
        jewel_fill = blend(color, CARD_FACE, 0.18)
        jewel_outline = blend(color, CARD_FACE, 0.35)
        if self.card.rank == 11:
            self.create_polygon(CARD_W / 2, jewel_y - 8, CARD_W / 2 + 10, jewel_y, CARD_W / 2, jewel_y + 8, CARD_W / 2 - 10, jewel_y,
                                fill=jewel_fill, outline=jewel_outline, width=2)
        elif self.card.rank == 12:
            self.create_oval(CARD_W / 2 - 8, jewel_y - 8, CARD_W / 2 + 8, jewel_y + 8, fill=jewel_fill, outline=jewel_outline, width=2)
            self.create_line(CARD_W / 2 - 14, jewel_y, CARD_W / 2 + 14, jewel_y, fill=jewel_outline, width=2)
        else:
            self.create_polygon(CARD_W / 2 - 12, jewel_y + 6, CARD_W / 2 - 6, jewel_y - 8, CARD_W / 2, jewel_y + 2,
                                CARD_W / 2 + 6, jewel_y - 8, CARD_W / 2 + 12, jewel_y + 6,
                                fill=jewel_fill, outline=jewel_outline, width=2)
        self.create_text(CARD_W / 2, bottom - 14, text=suit, fill=color, font=(FONT_CARD, 16, "bold"), angle=180)

    def _draw_joker_art(self, yoff: float):
        accent = "#7d5cff" if self.card.rank == 20 else "#2a2a2a"
        banner = "SMALL" if self.card.rank == 20 else "BIG"
        emblem = "✦" if self.card.rank == 20 else "✹"
        top = 36 + yoff
        bottom = CARD_H - 36 + yoff
        mid = (top + bottom) / 2
        frame_fill = blend(CARD_FACE, accent, 0.08)
        frame_outline = blend(accent, CARD_FACE, 0.38)
        self._pixel_panel(28, top, CARD_W - 28, bottom, 9, fill=frame_fill, outline=frame_outline, width=2)
        self._pixel_panel(36, top + 8, CARD_W - 36, bottom - 8, 7, fill=blend(CARD_FACE, ACCENT, 0.08), outline="", width=1)
        self.create_line(38, mid - 18, CARD_W - 38, mid - 18, fill=blend(frame_outline, CARD_FACE, 0.2), width=2)
        self.create_line(38, mid + 18, CARD_W - 38, mid + 18, fill=blend(frame_outline, CARD_FACE, 0.2), width=2)
        self.create_polygon(37, mid, 47, mid - 20, 47, mid + 20, fill=blend(accent, CARD_FACE, 0.25), outline="")
        self.create_polygon(CARD_W - 37, mid, CARD_W - 47, mid - 20, CARD_W - 47, mid + 20, fill=blend(accent, CARD_FACE, 0.25), outline="")
        self.create_text(CARD_W / 2, top + 14, text="JOKER", fill=accent, font=(FONT_CARD, 11, "bold"))
        self.create_text(CARD_W / 2, mid - 6, text=emblem, fill=ACCENT_DARK, font=(FONT_CARD, 24, "bold"))
        jewel_y = mid + 20
        jewel_fill = blend(accent, CARD_FACE, 0.18)
        jewel_outline = blend(accent, CARD_FACE, 0.35)
        if self.card.rank == 20:
            self.create_polygon(CARD_W / 2, jewel_y - 9, CARD_W / 2 + 11, jewel_y, CARD_W / 2, jewel_y + 9, CARD_W / 2 - 11, jewel_y,
                                fill=jewel_fill, outline=jewel_outline, width=2)
        else:
            self.create_oval(CARD_W / 2 - 9, jewel_y - 9, CARD_W / 2 + 9, jewel_y + 9, fill=jewel_fill, outline=jewel_outline, width=2)
            self.create_line(CARD_W / 2 - 15, jewel_y, CARD_W / 2 + 15, jewel_y, fill=jewel_outline, width=2)
        self.create_text(CARD_W / 2, bottom - 14, text=banner, fill=accent, font=(FONT_CARD, 11, "bold"), angle=180)

    def _pixel_panel(self, x1, y1, x2, y2, cut=8, **kwargs):
        points = [
            x1 + cut, y1,
            x2 - cut, y1,
            x2, y1 + cut,
            x2, y2 - cut,
            x2 - cut, y2,
            x1 + cut, y2,
            x1, y2 - cut,
            x1, y1 + cut,
        ]
        return self.create_polygon(points, smooth=False, **kwargs)


class DeckWidget(tk.Canvas):
    def __init__(self, master):
        super().__init__(master, width=176, height=220, bg=TABLE_GREEN, highlightthickness=0, bd=0)
        self.deck_size = 0
        self._redraw()

    def set_deck_size(self, deck_size: int):
        self.deck_size = deck_size
        self._redraw()

    def _redraw(self):
        self.delete("all")
        self.create_text(88, 16, text="DRAW PILE", fill=MUTED_TEXT, font=(FONT_TITLE, 10, "bold"))
        offsets = [(30, 56), (38, 48), (46, 40)]
        for x, y in offsets:
            draw_card_back(self, x, y, 86, 122, title_font=(FONT_TITLE, 8, 'bold'), symbol_font=(FONT_CARD, 11, 'bold'), footer_font=(FONT_UI, 7, 'bold'))
        badge_fill = blend(PANEL_ALT, CARD_FACE, 0.12)
        self._pixel_panel(30, 188, 146, 212, 6, fill=badge_fill, outline=ACCENT_DARK, width=2)
        self.create_text(88, 200, text=f"{self.deck_size} card{'s' if self.deck_size != 1 else ''}", fill=LIGHT_TEXT, font=(FONT_UI, 11, "bold"))

    def _pixel_panel(self, x1, y1, x2, y2, cut=6, **kwargs):
        points = [
            x1 + cut, y1,
            x2 - cut, y1,
            x2, y1 + cut,
            x2, y2 - cut,
            x2 - cut, y2,
            x1 + cut, y2,
            x1, y2 - cut,
            x1, y1 + cut,
        ]
        return self.create_polygon(points, smooth=False, **kwargs)


class FiveTenKGui:
    def __init__(self, root: tk.Tk, checkpoint_path: str, bot_first: bool = False):
        self.root = root
        self.controller = MatchController(checkpoint_path, bot_first=bot_first)
        self.pending_bot_job = None

        self.root.title("Five-Ten-K Cardroom")
        self.root.geometry("1440x900")
        self.root.configure(bg=TABLE_DARK)

        self.status_var = tk.StringVar()
        self.meta_var = tk.StringVar()
        self.turn_var = tk.StringVar()
        self.deck_var = tk.StringVar()
        self.last_move_var = tk.StringVar()
        self.selection_var = tk.StringVar()
        self.opponent_var = tk.StringVar()
        self.result_var = tk.StringVar()
        self.wins_var = tk.StringVar()
        self.starting_player_var = tk.StringVar(value="Bot" if bot_first else "Me")

        self.move_lookup: List[object] = []
        self.card_widgets: Dict[Tuple[int, Optional[str]], CardWidget] = {}
        self.selected_card_keys: List[Tuple[int, Optional[str]]] = []

        self.legal_listbox = None
        self.log_text = None
        self.human_cards_frame = None
        self.opp_cards_frame = None
        self.table_cards_frame = None
        self.play_button = None
        self.pass_button = None
        self.clear_button = None
        self.hint_label = None
        self.deck_widget = None
        self.section_patterns = []
        self.last_result_counted = False

        self._build_ui()
        self.refresh_view()
        self.schedule_bot_if_needed(initial=True)

    def _button_style(self, *, bg: str, activebg: str, fg: str = BUTTON_TEXT):
        return {
            "bg": bg,
            "fg": fg,
            "activebackground": activebg,
            "activeforeground": fg,
            "disabledforeground": BUTTON_DISABLED_TEXT,
            "relief": "flat",
            "bd": 0,
            "highlightthickness": 0,
            "cursor": "hand2",
        }

    def _apply_button_state(self, button: tk.Button, enabled: bool, *, bg: str, activebg: str, fg: str = BUTTON_TEXT):
        if enabled:
            button.configure(
                state="normal",
                bg=bg,
                fg=fg,
                activebackground=activebg,
                activeforeground=fg,
                disabledforeground=BUTTON_DISABLED_TEXT,
                cursor="hand2",
            )
        else:
            button.configure(
                state="disabled",
                bg=BUTTON_DISABLED_BG,
                fg=BUTTON_DISABLED_TEXT,
                disabledforeground=BUTTON_DISABLED_TEXT,
                activebackground=BUTTON_DISABLED_BG,
                activeforeground=BUTTON_DISABLED_TEXT,
                cursor="arrow",
            )

    def _panel(self, master, bg=PANEL_BG, border=ACCENT_DARK):
        frame = tk.Frame(master, bg=bg, highlightbackground=border, highlightthickness=2, bd=0)
        return frame

    def _static_panel(self, master, bg=PANEL_BG, border=ACCENT_DARK, border_width=2):
        outer = tk.Frame(master, bg=border, bd=0, highlightthickness=0)
        inner = tk.Frame(outer, bg=bg, bd=0, highlightthickness=0)
        inner.pack(fill="both", expand=True, padx=border_width, pady=border_width)
        return outer, inner

    def _build_ui(self):
        outer = tk.Frame(self.root, bg=TABLE_DARK)
        outer.pack(fill="both", expand=True, padx=14, pady=14)

        topbar = tk.Frame(outer, bg=TABLE_DARK)
        topbar.pack(fill="x", pady=(0, 12))

        title_stack = tk.Frame(topbar, bg=TABLE_DARK)
        title_stack.pack(side="left")
        tk.Label(title_stack, text="Laoban • 老板", bg=TABLE_DARK, fg=LIGHT_TEXT, font=(FONT_TITLE, 24, "bold")).pack(anchor="w")
        tk.Label(title_stack, text="5/10/K Cardroom", bg=TABLE_DARK, fg=MUTED_TEXT, font=(FONT_UI, 10)).pack(anchor="w", pady=(2, 0))

        controls_right = tk.Frame(topbar, bg=TABLE_DARK)
        controls_right.pack(side="right")
        chooser_frame = tk.Frame(controls_right, bg=TABLE_DARK)
        chooser_frame.pack(side="right", padx=(10, 0))
        tk.Label(chooser_frame, text="First move:", bg=TABLE_DARK, fg=MUTED_TEXT, font=(FONT_TITLE, 10, "bold")).pack(side="left", padx=(0, 6))
        start_menu = tk.OptionMenu(chooser_frame, self.starting_player_var, "Me", "Bot", command=self.on_starting_player_changed)
        start_menu.configure(
            bg=ACCENT,
            fg=BUTTON_TEXT,
            activebackground="#dfba43",
            activeforeground=BUTTON_TEXT,
            highlightthickness=0,
            bd=0,
            font=(FONT_UI, 10, "bold"),
            padx=8,
            pady=2,
            indicatoron=1,
        )
        start_menu["menu"].configure(bg=PANEL_ALT, fg=LIGHT_TEXT, activebackground=TABLE_GLOW, activeforeground=LIGHT_TEXT, font=(FONT_UI, 10))
        start_menu.pack(side="left")
        tk.Button(controls_right, text="New Game", command=self.new_game, font=(FONT_UI, 11, "bold"), padx=12, pady=6, **self._button_style(bg=ACCENT, activebg="#dfba43")).pack(side="right")

        policy = self.controller.policy
        meta_text = (
            f"Checkpoint: {policy.path}  |  encoder: {policy.encoder_spec.name}  |  dims: "
            f"{policy.encoder_spec.state_dim}/{policy.encoder_spec.action_dim}  |  value head: {policy.value_head_kind}  |  "
            f"saved episode: {policy.checkpoint.get('episode', 'unknown')}"
        )
        meta_panel = self._panel(outer, bg=PANEL_ALT, border=ACCENT_DARK)
        meta_panel.pack(fill="x", pady=(0, 12))
        tk.Label(meta_panel, text=meta_text, bg=PANEL_ALT, fg=MUTED_TEXT, wraplength=1380, justify="left", font=(FONT_UI, 10)).pack(fill="x", padx=12, pady=8)

        content = tk.Frame(outer, bg=TABLE_DARK)
        content.pack(fill="both", expand=True)

        table = self._panel(content, bg=TABLE_GREEN, border=ACCENT_DARK)
        table.pack(side="left", fill="both", expand=True, padx=(0, 12))

        self.table_bg = None

        sidebar_outer, sidebar = self._static_panel(content, bg=PANEL_BG, border=ACCENT_DARK)
        sidebar_outer.pack(side="left", fill="y")
        sidebar_outer.configure(width=380)
        sidebar_outer.pack_propagate(False)

        opp_section = tk.Frame(table, bg=TABLE_GREEN)
        opp_section.pack(fill="x", pady=(12, 4))
        self._attach_section_pattern(opp_section, kind="header")
        tk.Label(opp_section, text="Opponent", bg=TABLE_GREEN, fg=LIGHT_TEXT, font=(FONT_TITLE, 15, "bold")).pack()
        tk.Label(opp_section, textvariable=self.opponent_var, bg=TABLE_GREEN, fg=MUTED_TEXT, font=(FONT_UI, 11)).pack(pady=(3, 8))
        self.opp_cards_frame = tk.Frame(opp_section, bg=TABLE_GREEN, height=CARD_WIDGET_H + 8)
        self.opp_cards_frame.pack(fill="x", expand=True, pady=(0, 8), padx=28)

        center = tk.Frame(table, bg=TABLE_GREEN)
        center.pack(fill="both", expand=True, pady=(6, 10))
        self._attach_section_pattern(center, kind="center")

        table_mid = tk.Frame(center, bg=TABLE_GREEN)
        table_mid.pack(fill="both", expand=True, padx=12)
        table_mid.grid_columnconfigure(0, weight=0)
        table_mid.grid_columnconfigure(1, weight=1)
        table_mid.grid_columnconfigure(2, weight=0)
        table_mid.grid_rowconfigure(0, weight=1)

        left_mid = tk.Frame(table_mid, bg=TABLE_GREEN, width=200)
        self._attach_section_pattern(left_mid, kind="side")
        left_mid.grid(row=0, column=0, sticky="n", padx=(0, 18))
        left_mid.grid_propagate(False)
        self.deck_widget = DeckWidget(left_mid)
        self.deck_widget.pack(pady=(8, 2))

        stage_mid = tk.Frame(table_mid, bg=TABLE_GREEN)
        self._attach_section_pattern(stage_mid, kind="center")
        stage_mid.grid(row=0, column=1, sticky="nsew")
        status_chip = self._panel(stage_mid, bg=blend(TABLE_GREEN, "#143b2e", 0.45), border=ACCENT_DARK)
        status_chip.pack(padx=18, pady=(0, 10))
        tk.Label(status_chip, textvariable=self.status_var, bg=status_chip.cget("bg"), fg=LIGHT_TEXT, font=(FONT_UI, 13, "bold")).pack(padx=16, pady=(8, 4))
        tk.Label(status_chip, textvariable=self.turn_var, bg=status_chip.cget("bg"), fg=MUTED_TEXT, font=(FONT_UI, 11)).pack(padx=16, pady=(0, 2))
        tk.Label(status_chip, textvariable=self.wins_var, bg=status_chip.cget("bg"), fg=MUTED_TEXT, font=(FONT_UI, 11)).pack(padx=16, pady=(0, 8))
        stage_inner = tk.Frame(stage_mid, bg=TABLE_GREEN)
        stage_inner.pack(expand=True)
        tk.Label(stage_inner, textvariable=self.last_move_var, bg=TABLE_GREEN, fg=LIGHT_TEXT, font=(FONT_UI, 12)).pack(pady=(10, 8))
        self.table_cards_frame = tk.Frame(stage_inner, bg=TABLE_GREEN, width=5 * CARD_W + 4 * 12 + 24, height=CARD_WIDGET_H + 40)
        self.table_cards_frame.pack(pady=(0, 12))
        self.table_cards_frame.pack_propagate(False)
        tk.Label(stage_inner, textvariable=self.result_var, bg=TABLE_GREEN, fg=ACCENT, font=(FONT_TITLE, 13, "bold")).pack(pady=(0, 12))

        controls = tk.Frame(stage_inner, bg=TABLE_GREEN)
        controls.pack(pady=(10, 0))
        self.play_button = tk.Button(controls, text="Play Selected", command=self.play_selected_cards, font=(FONT_UI, 12, "bold"), padx=16, pady=7, **self._button_style(bg=ACCENT, activebg="#dfba43"))
        self.play_button.pack(side="left", padx=6)
        self.pass_button = tk.Button(controls, text="Pass", command=self.play_pass, font=(FONT_UI, 12, "bold"), padx=16, pady=7, **self._button_style(bg=PASS_BG, activebg=PASS_ACTIVE_BG))
        self.pass_button.pack(side="left", padx=6)
        self.clear_button = tk.Button(controls, text="Clear", command=self.clear_selection, font=(FONT_UI, 12, "bold"), padx=16, pady=7, **self._button_style(bg=CLEAR_BG, activebg=CLEAR_ACTIVE_BG))
        self.clear_button.pack(side="left", padx=6)

        tk.Label(stage_inner, textvariable=self.selection_var, bg=TABLE_GREEN, fg=LIGHT_TEXT, font=(FONT_UI, 11), wraplength=700).pack(pady=(12, 0))

        right_mid = tk.Frame(table_mid, bg=TABLE_GREEN, width=200)
        self._attach_section_pattern(right_mid, kind="side")
        right_mid.grid(row=0, column=2, sticky="n", padx=(18, 0))
        right_mid.grid_propagate(False)

        human_section = tk.Frame(table, bg=TABLE_GREEN)
        human_section.pack(fill="x", pady=(8, 12))
        self._attach_section_pattern(human_section, kind="footer")
        tk.Label(human_section, text="Your Hand", bg=TABLE_GREEN, fg=LIGHT_TEXT, font=(FONT_TITLE, 15, "bold")).pack(pady=(0, 8))
        self.human_cards_frame = tk.Frame(human_section, bg=TABLE_GREEN, height=CARD_WIDGET_H + 8)
        self.human_cards_frame.pack(fill="x", expand=True, padx=28)
        self.hint_label = tk.Label(
            human_section,
            text="Playable cards glow green. Hover lifts cards. Click exact cards to build a legal move.",
            bg=TABLE_GREEN,
            fg=MUTED_TEXT,
            font=(FONT_UI, 11),
        )
        self.hint_label.pack(pady=(8, 0))

        sidebar_header = tk.Label(sidebar, text="Move Browser", bg=PANEL_BG, fg=LIGHT_TEXT, font=(FONT_TITLE, 16, "bold"))
        sidebar_header.pack(anchor="w", padx=14, pady=(12, 6))
        move_hint = tk.Label(sidebar, text="Double-click any legal move here, or play directly from the card row below.", bg=PANEL_BG, fg=MUTED_TEXT, wraplength=340, justify="left", font=(FONT_UI, 10))
        move_hint.pack(anchor="w", padx=14, pady=(0, 10))

        legal_listbox_outer, legal_listbox_frame = self._static_panel(sidebar, bg="#f4efde", border=ACCENT_DARK)
        legal_listbox_outer.pack(fill="x", padx=10)
        self.legal_listbox = tk.Listbox(
            legal_listbox_frame,
            height=18,
            activestyle="none",
            exportselection=False,
            bg="#f4efde",
            fg="#1b1b1b",
            selectbackground="#2d5643",
            selectforeground="#fff8e7",
            font=(FONT_MONO, 12),
            bd=0,
            highlightthickness=0,
            selectborderwidth=0,
            relief="flat",
        )
        self.legal_listbox.pack(fill="x", padx=10, pady=8)
        self.legal_listbox.bind("<<ListboxSelect>>", self.on_move_list_select)
        self.legal_listbox.bind("<Double-Button-1>", self.on_move_list_double_click)

        log_title = tk.Label(sidebar, text="Action Log", bg=PANEL_BG, fg=LIGHT_TEXT, font=(FONT_TITLE, 16, "bold"))
        log_title.pack(anchor="w", padx=14, pady=(16, 6))
        log_text_outer, log_text_frame = self._static_panel(sidebar, bg="#f4efde", border=ACCENT_DARK)
        log_text_outer.pack(fill="both", expand=True, padx=10, pady=(0, 14))
        self.log_text = tk.Text(log_text_frame, wrap="word", state="disabled", bg="#f4efde", fg="#1b1b1b", height=24, bd=0, highlightthickness=0, relief="flat", font=(FONT_MONO, 10), padx=10, pady=8, spacing1=0, spacing2=0, spacing3=0)
        self.log_text.pack(fill="both", expand=True)

    def _attach_section_pattern(self, frame: tk.Frame, kind: str):
        return None

    def _redraw_pattern_canvas(self, canvas: tk.Canvas, kind: str):
        canvas.delete("all")
        w = max(200, canvas.winfo_width())
        h = max(140, canvas.winfo_height())
        dot_fill = blend(TABLE_GREEN, ACCENT, 0.13)
        dot_outline = blend(TABLE_GREEN, LIGHT_TEXT, 0.07)
        rail_fill = blend(TABLE_GREEN, ACCENT, 0.09)
        rail_edge = blend(TABLE_GREEN, ACCENT, 0.16)
        lattice_step = 76 if kind in {"center", "footer"} else 64
        y_start = 26 if kind == "header" else 18
        for row, y in enumerate(range(y_start, h, lattice_step)):
            offset = 0 if row % 2 == 0 else lattice_step // 2
            for x in range(24 + offset, w, lattice_step):
                r = 5 if kind != "header" else 4
                pts = [x, y-r, x+r, y, x, y+r, x-r, y]
                canvas.create_polygon(pts, fill=dot_fill, outline=dot_outline, width=1)
        if kind in {"center", "footer", "side"}:
            margin = 16
            span = min(140, max(70, w // 7))
            y_top = 18
            y_bot = h - 18
            for sign, yy in ((1, y_top), (-1, y_bot)):
                for x in range(margin + 16, w - margin, span):
                    pts = [x - 18, yy, x, yy + sign * 10, x + 18, yy]
                    canvas.create_line(*pts, fill=rail_edge, width=2)
                    pts2 = [x - 10, yy + sign * 6, x, yy + sign * 12, x + 10, yy + sign * 6]
                    canvas.create_line(*pts2, fill=rail_fill, width=2)
        if kind == "center":
            cx = w / 2
            cy = h / 2
            for rw, rh, t in ((220, 72, 0.08), (150, 48, 0.12)):
                canvas.create_polygon(
                    cx, cy-rh, cx+rw, cy, cx, cy+rh, cx-rw, cy,
                    fill="", outline=blend(TABLE_GREEN, ACCENT, t), width=2
                )
            for dx in (-120, -60, 60, 120):
                x = cx + dx
                canvas.create_polygon(x, cy-8, x+8, cy, x, cy+8, x-8, cy, fill=blend(TABLE_GREEN, ACCENT, 0.14), outline="")
        if kind == "header":
            y = h - 16
            for x in range(40, w - 40, 84):
                canvas.create_line(x - 18, y, x, y - 8, x + 18, y, fill=blend(TABLE_GREEN, ACCENT, 0.14), width=2)

    def _redraw_table_bg(self, _event=None):
        canvas = getattr(self, 'table_bg', None)
        if canvas is None:
            return
        canvas.delete('all')
        w = max(200, canvas.winfo_width())
        h = max(200, canvas.winfo_height())
        cx = w / 2
        cy = h / 2

        def pix_diamond(cx, cy, rx, ry, fill, outline=''):
            pts = [cx, cy - ry, cx + rx, cy, cx, cy + ry, cx - rx, cy]
            canvas.create_polygon(pts, fill=fill, outline=outline, smooth=False)

        def pix_oct(cx, cy, r, fill, outline=''):
            cut = r * 0.38
            pts = [
                cx - cut, cy - r, cx + cut, cy - r, cx + r, cy - cut, cx + r, cy + cut,
                cx + cut, cy + r, cx - cut, cy + r, cx - r, cy + cut, cx - r, cy - cut,
            ]
            canvas.create_polygon(pts, fill=fill, outline=outline, smooth=False)

        # subtle radial glow
        for frac, alpha in ((0.92, 0.08), (0.72, 0.12), (0.52, 0.17)):
            pix_oct(cx, cy, min(w, h) * 0.24 * frac, blend(TABLE_GREEN, ACCENT, alpha), outline='')

        # symmetric corner motifs
        motif_fill = blend(TABLE_GREEN, ACCENT, 0.10)
        motif_edge = blend(TABLE_GREEN, ACCENT, 0.18)
        for mx, my, sx, sy in [
            (130, 120, 1, 1), (w - 130, 120, -1, 1),
            (130, h - 120, 1, -1), (w - 130, h - 120, -1, -1),
        ]:
            pix_diamond(mx, my, 48, 48, motif_fill, outline=motif_edge)
            pix_diamond(mx, my, 28, 28, '', outline=blend(TABLE_GREEN, ACCENT, 0.22))
            for step in (74, 102):
                pix_diamond(mx + sx * step, my, 12, 12, motif_fill)
                pix_diamond(mx, my + sy * step, 12, 12, motif_fill)
                pix_diamond(mx + sx * step * 0.6, my + sy * step * 0.6, 9, 9, motif_fill)

        # central mirrored pixel lattice
        ring_fill = blend(TABLE_GREEN, ACCENT, 0.08)
        ring_edge = blend(TABLE_GREEN, ACCENT, 0.14)
        for dx in (-160, -96, -48, 48, 96, 160):
            pix_diamond(cx + dx, cy, 10, 10, ring_fill)
        for dy in (-120, -72, -36, 36, 72, 120):
            pix_diamond(cx, cy + dy, 10, 10, ring_fill)
        pix_oct(cx, cy, 72, '', outline=ring_edge)
        pix_oct(cx, cy, 108, '', outline=blend(TABLE_GREEN, ACCENT, 0.10))
        for off in (-84, 84):
            pix_diamond(cx + off, cy + off * 0.55, 14, 14, ring_fill)
            pix_diamond(cx - off, cy + off * 0.55, 14, 14, ring_fill)

    def on_starting_player_changed(self, *_args):
        bot_first = self.starting_player_var.get() == "Bot"
        if self.pending_bot_job is not None:
            self.root.after_cancel(self.pending_bot_job)
            self.pending_bot_job = None
        self.controller.set_bot_first(bot_first)
        self.last_result_counted = False
        self.selected_card_keys = []
        self.refresh_view()
        self.schedule_bot_if_needed(initial=True)

    def new_game(self):
        if self.pending_bot_job is not None:
            self.root.after_cancel(self.pending_bot_job)
            self.pending_bot_job = None
        self.controller.reset()
        self.last_result_counted = False
        self.selected_card_keys = []
        self.refresh_view()
        self.schedule_bot_if_needed(initial=True)

    def current_human_hand(self) -> List[Card]:
        return sorted(self.controller.env.hands[self.controller.human_seat], key=lambda c: (c.rank, c.suit or ""))

    def current_legal_actions(self):
        if not self.controller.is_human_turn() or self.controller.env.done:
            return []
        return self.controller.legal_actions(concrete_for_human=True)

    def legal_action_lookup(self) -> Dict[Tuple[Tuple[int, Optional[str]], ...], object]:
        lookup = {}
        for action in self.current_legal_actions():
            if action is None:
                continue
            key = tuple(sorted(card_key(c) for c in action))
            lookup[key] = action
        return lookup

    def playable_card_keys(self) -> set:
        playable = set()
        for action in self.current_legal_actions():
            if action is None:
                continue
            for c in action:
                playable.add(card_key(c))
        return playable

    def _prune_selection(self):
        hand_keys = {card_key(c) for c in self.current_human_hand()}
        self.selected_card_keys = [k for k in self.selected_card_keys if k in hand_keys]

    def toggle_card(self, card: Card):
        if not self.controller.is_human_turn() or self.controller.env.done:
            return
        key = card_key(card)
        if key in self.selected_card_keys:
            self.selected_card_keys = [k for k in self.selected_card_keys if k != key]
        else:
            self.selected_card_keys.append(key)
        self.refresh_view(listbox_preserve=True)

    def clear_selection(self):
        self.selected_card_keys = []
        if self.legal_listbox is not None:
            self.legal_listbox.selection_clear(0, tk.END)
        self.refresh_view(listbox_preserve=True)

    def selected_action(self):
        if not self.selected_card_keys:
            return None
        key = tuple(sorted(self.selected_card_keys))
        return self.legal_action_lookup().get(key)

    def selected_move_text(self) -> str:
        action = self.selected_action()
        if action is not None:
            return format_move(action)
        if not self.selected_card_keys:
            return "No cards selected."
        cards = " ".join(card_text(Card(rank, suit)) for rank, suit in self.selected_card_keys)
        return f"Selected cards do not form a legal move: {cards}"

    def move_for_index(self, idx: int):
        if idx < 0 or idx >= len(self.move_lookup):
            return None
        return self.move_lookup[idx]

    def on_move_list_select(self, _event=None):
        if not self.controller.is_human_turn() or self.controller.env.done:
            return
        selection = self.legal_listbox.curselection()
        if not selection:
            return
        action = self.move_for_index(int(selection[0]))
        if action is None:
            self.selected_card_keys = []
        else:
            self.selected_card_keys = list(tuple(sorted(card_key(c) for c in action)))
        self.refresh_view(listbox_preserve=True)

    def on_move_list_double_click(self, _event=None):
        if not self.controller.is_human_turn() or self.controller.env.done:
            return
        selection = self.legal_listbox.curselection()
        if not selection:
            return
        action = self.move_for_index(int(selection[0]))
        if action is None:
            self.play_pass()
        else:
            self.selected_card_keys = list(tuple(sorted(card_key(c) for c in action)))
            self.play_selected_cards()

    def play_pass(self):
        if not self.controller.is_human_turn() or self.controller.env.done:
            return
        if None not in self.current_legal_actions():
            messagebox.showinfo("Cannot pass", "Pass is not a legal action right now.")
            return
        self.controller.apply_action(None)
        self.selected_card_keys = []
        self.refresh_view()
        self.schedule_bot_if_needed()

    def play_selected_cards(self):
        if not self.controller.is_human_turn() or self.controller.env.done:
            return
        action = self.selected_action()
        if action is None:
            messagebox.showinfo("Illegal selection", "Pick cards that exactly match one of the legal moves.")
            return
        self.controller.apply_action(action)
        self.selected_card_keys = []
        self.refresh_view()
        self.schedule_bot_if_needed()

    def _rebuild_card_row(self, frame: tk.Frame, cards: Sequence[Card], clickable: bool, playable_keys: set, selected_keys: set, face_up: bool = True, spacing: int = CARD_SPACING):
        for child in frame.winfo_children():
            child.destroy()
        widgets: Dict[Tuple[int, Optional[str]], CardWidget] = {}
        count = len(cards)
        frame.update_idletasks()
        available = frame.winfo_width()
        if available <= 40:
            available = 980
        gutter = 12
        gap = 8
        top_headroom = 2
        bottom_padding = 4
        max_per_row = max(1, (available - 2 * gutter + gap) // (CARD_W + gap))
        rows = max(1, math.ceil(count / max_per_row))
        row_h = CARD_WIDGET_H + 6
        total_h = top_headroom + rows * row_h + bottom_padding
        frame.configure(height=total_h)
        board = tk.Frame(frame, bg=frame.cget("bg"), width=available, height=total_h)
        board.place(relx=0.5, y=0, anchor="n", width=available, height=total_h)

        for row_idx in range(rows):
            start = row_idx * max_per_row
            row_cards = cards[start:start + max_per_row]
            row_n = len(row_cards)
            row_width = row_n * CARD_W + max(0, row_n - 1) * gap
            x0 = max(gutter, (available - row_width) // 2)
            y = top_headroom + row_idx * row_h
            for col_idx, card in enumerate(row_cards):
                widget = CardWidget(board, card, command=self.toggle_card if clickable else None, face_up=face_up)
                x = x0 + col_idx * (CARD_W + gap)
                widget.place(x=x, y=y, width=CARD_W, height=CARD_WIDGET_H)
                if face_up:
                    key = card_key(card)
                    widget.set_state(playable=(key in playable_keys), selected=(key in selected_keys))
                    widgets[key] = widget
        return widgets

    def _render_table_cards(self):
        for child in self.table_cards_frame.winfo_children():
            child.destroy()
        last_cards = self.controller.last_move.cards if self.controller.last_move is not None else []
        if not last_cards:
            tk.Label(self.table_cards_frame, text="No active table move", bg=TABLE_GREEN, fg=MUTED_TEXT, font=(FONT_UI, 12, "italic")).pack(expand=True)
            return
        move_label = tk.Label(self.table_cards_frame, text=self.controller.last_move.type.upper(), bg=TABLE_GREEN, fg=ACCENT, font=(FONT_TITLE, 14, "bold"))
        move_label.pack(pady=(0, 8))
        gap = 12
        row_w = len(last_cards) * CARD_W + max(0, len(last_cards) - 1) * gap
        row = tk.Frame(self.table_cards_frame, bg=TABLE_GREEN, width=row_w, height=CARD_WIDGET_H + 2)
        row.pack()
        row.pack_propagate(False)
        for i, card in enumerate(last_cards):
            w = CardWidget(row, card, command=None, face_up=True)
            w.place(x=i * (CARD_W + gap), y=0, width=CARD_W, height=CARD_WIDGET_H)
            w.set_state(playable=False, selected=False)

    def refresh_view(self, listbox_preserve: bool = False):
        env = self.controller.env
        self._prune_selection()
        human_points = env.points[self.controller.human_seat]
        bot_points = env.points[self.controller.bot_seat]
        self.status_var.set(f"You {human_points}   ·   Bot {bot_points}   ·   Pot {env.current_pot}")
        turn_owner = "You" if self.controller.is_human_turn() else "Bot" if self.controller.is_bot_turn() else "Game Over"
        hand_type = self.controller.hand_type or "open"
        self.turn_var.set(f"Turn: {turn_owner}   ·   Hand type: {hand_type}")
        self.deck_var.set(f"{env.deck.size()} remaining")
        self.deck_widget.set_deck_size(env.deck.size())
        self.last_move_var.set(f"Last move: {format_move(self.controller.last_move) if self.controller.last_move is not None else 'None'}")
        self.opponent_var.set(f"Cards in hand: {len(env.hands[self.controller.bot_seat])}")

        if env.done:
            if human_points > bot_points:
                self.result_var.set("Final Result: You win")
                if not self.last_result_counted:
                    self.controller.human_wins += 1
                    self.last_result_counted = True
            elif human_points < bot_points:
                self.result_var.set("Final Result: Bot wins")
                if not self.last_result_counted:
                    self.controller.bot_wins += 1
                    self.last_result_counted = True
            else:
                self.result_var.set("Final Result: Tie game")
                self.last_result_counted = True
        else:
            self.result_var.set("")
            self.last_result_counted = False
        self.wins_var.set(f"Wins - You: {self.controller.human_wins}   ·   Bot: {self.controller.bot_wins}")

        human_hand = self.current_human_hand()
        playable_keys = self.playable_card_keys() if self.controller.is_human_turn() else set()
        selected_keys = set(self.selected_card_keys)
        self.card_widgets = self._rebuild_card_row(self.human_cards_frame, human_hand, clickable=True, playable_keys=playable_keys, selected_keys=selected_keys, face_up=True, spacing=CARD_SPACING)

        opp_count = len(env.hands[self.controller.bot_seat])
        opp_cards = [Card(-1, None) for _ in range(opp_count)]
        self._rebuild_card_row(self.opp_cards_frame, opp_cards, clickable=False, playable_keys=set(), selected_keys=set(), face_up=False, spacing=OPP_SPACING)

        self._render_table_cards()

        current_selection_index = self.legal_listbox.curselection()[0] if (listbox_preserve and self.legal_listbox.curselection()) else None
        self.legal_listbox.delete(0, tk.END)
        self.move_lookup = []
        if self.controller.is_human_turn() and not env.done:
            for action in self.current_legal_actions():
                self.move_lookup.append(action)
                self.legal_listbox.insert(tk.END, format_move_browser(action))
            if current_selection_index is not None and current_selection_index < len(self.move_lookup):
                self.legal_listbox.selection_set(current_selection_index)
        else:
            self.legal_listbox.insert(tk.END, "Waiting for bot..." if not env.done else "Game over")

        self.selection_var.set(self.selected_move_text())
        self._apply_button_state(self.play_button, self.controller.is_human_turn() and self.selected_action() is not None, bg=ACCENT, activebg="#dfba43")
        self._apply_button_state(self.pass_button, self.controller.is_human_turn() and None in self.current_legal_actions(), bg=PASS_BG, activebg=PASS_ACTIVE_BG)
        self._apply_button_state(self.clear_button, bool(self.selected_card_keys), bg=CLEAR_BG, activebg=CLEAR_ACTIVE_BG)

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", tk.END)
        self.log_text.insert(tk.END, "\n".join(self.controller.log[-250:]))
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _bot_step(self):
        self.pending_bot_job = None
        if self.controller.env.done:
            self.refresh_view()
            return
        if self.controller.is_bot_turn():
            acted = self.controller.autoplay_nonhuman_turns(fallback_random_for_human=False, max_actions=1)
            if acted == 0:
                return
            self.selected_card_keys = []
            self.refresh_view()
        if self.controller.is_bot_turn() and not self.controller.env.done:
            self.pending_bot_job = self.root.after(BOT_THINK_MS, self._bot_step)

    def schedule_bot_if_needed(self, initial: bool = False):
        if self.pending_bot_job is not None:
            self.root.after_cancel(self.pending_bot_job)
            self.pending_bot_job = None
        if self.controller.is_bot_turn() and not self.controller.env.done:
            delay = 120 if initial else BOT_THINK_MS
            self.pending_bot_job = self.root.after(delay, self._bot_step)


def run_gui(checkpoint_path: str, bot_first: bool = False):
    root = tk.Tk()
    app = FiveTenKGui(root, checkpoint_path=checkpoint_path, bot_first=bot_first)
    root.mainloop()
    return app


def headless_autoplay_smoke_test(checkpoint_path: str, games: int = 1):
    details = smoke_test_checkpoint(checkpoint_path)
    summaries = []
    for seed in range(games):
        controller = MatchController(checkpoint_path, bot_first=bool(seed % 2), seed=seed)
        total_actions = 0
        while not controller.env.done and total_actions < 800:
            acted = controller.autoplay_nonhuman_turns(fallback_random_for_human=True, max_actions=25)
            if acted <= 0:
                raise RuntimeError("Autoplay made no progress during smoke test.")
            total_actions += acted
        if not controller.env.done:
            raise RuntimeError("Headless autoplay did not finish the game.")
        summaries.append({
            "seed": seed,
            "human_points": controller.env.points[controller.human_seat],
            "bot_points": controller.env.points[controller.bot_seat],
            "winner": "human" if controller.env.points[controller.human_seat] > controller.env.points[controller.bot_seat] else (
                "bot" if controller.env.points[controller.human_seat] < controller.env.points[controller.bot_seat] else "tie"
            ),
            "log_entries": len(controller.log),
            "actions": total_actions,
        })
    return {"checkpoint": details, "games": summaries}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GUI playtester for Five-Ten-K checkpoints.")
    parser.add_argument("checkpoint", nargs="?", default="policy_latest.pt")
    parser.add_argument("--bot-first", action="store_true")
    parser.add_argument("--smoke-test", action="store_true", help="Run a headless checkpoint/controller smoke test and exit.")
    parser.add_argument("--games", type=int, default=1, help="Number of headless smoke-test games to run.")
    args = parser.parse_args()

    if args.smoke_test:
        result = headless_autoplay_smoke_test(args.checkpoint, games=max(1, args.games))
        print(result)
    else:
        run_gui(args.checkpoint, bot_first=args.bot_first)