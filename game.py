import random
from collections import Counter
from copy import deepcopy

# ======================
# Constants
# ======================

RANKS = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 17, 20, 30]
SUITS = ['H', 'D', 'C', 'S']
SUIT_ORDER = {'D': 0, 'C': 1, 'H': 2, 'S': 3}

SMALL_JOKER = 20
BIG_JOKER = 30

POINT_VALUES = {5: 5, 10: 10, 13: 10}

# Total count per rank (for unseen calculation)
RANK_TOTALS = {
    r: (1 if r in [SMALL_JOKER, BIG_JOKER] else 4)
    for r in RANKS
}

# Bomb quad rank order: 3 < 4 < ... < K < A < 2
BOMB_QUAD_RANK_ORDER = {
    3: 0,
    4: 1,
    5: 2,
    6: 3,
    7: 4,
    8: 5,
    9: 6,
    10: 7,
    11: 8,   # J
    12: 9,   # Q
    13: 10,  # K
    14: 11,  # A
    17: 12,  # 2
}

# ======================
# Card
# ======================

class Card:
    def __init__(self, rank, suit=None):
        self.rank = rank
        self.suit = suit

    def __repr__(self):
        if self.rank == SMALL_JOKER:
            return "X"
        if self.rank == BIG_JOKER:
            return "D"
        return f"{self.rank}{self.suit}"

    def __eq__(self, other):
        return isinstance(other, Card) and self.rank == other.rank and self.suit == other.suit

    def __hash__(self):
        return hash((self.rank, self.suit))

# ======================
# Deck
# ======================

class Deck:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.cards = self._build()
        self.rng.shuffle(self.cards)

    def _build(self):
        cards = []
        for r in RANKS:
            if r in [SMALL_JOKER, BIG_JOKER]:
                cards.append(Card(r))
            else:
                for s in SUITS:
                    cards.append(Card(r, s))
        return cards

    def draw(self):
        return self.cards.pop() if self.cards else None

    def size(self):
        return len(self.cards)

# ======================
# Move
# ======================

class Move:
    def __init__(self, cards):
        self.cards = sorted(cards, key=lambda c: c.rank)
        self.type = None
        self.strength = None
        self.length = len(cards)
        self._analyze()

    def _analyze(self):
        ranks = [c.rank for c in self.cards]
        count = Counter(ranks)

        # Joker bomb
        if set(ranks) == {SMALL_JOKER, BIG_JOKER} and len(ranks) == 2:
            self.type = "bomb"
            self.strength = (4, 0)
            return

        # Four of a kind
        if 4 in count.values():
            quad_rank = next(rank for rank, cnt in count.items() if cnt == 4)
            self.type = "bomb"
            self.strength = (3, BOMB_QUAD_RANK_ORDER[quad_rank])
            return

        # 5-10-K bomb
        if sorted(ranks) == [5, 10, 13]:
            suited = len(set(c.suit for c in self.cards)) == 1
            self.type = "bomb"
            if suited:
                suit = self.cards[0].suit
                self.strength = (2, SUIT_ORDER[suit])
            else:
                self.strength = (1, 0)
            return

        # Normal
        if len(self.cards) == 1:
            self.type = "single"
            self.strength = (ranks[0],)

        elif len(self.cards) == 2 and len(count) == 1:
            self.type = "pair"
            self.strength = (ranks[0],)

        elif len(self.cards) == 3 and len(count) == 1:
            self.type = "triple"
            self.strength = (ranks[0],)

        elif self._is_straight(ranks):
            self.type = "straight"
            self.strength = (max(ranks), 5)

    def _is_straight(self, ranks):
        if len(ranks) != 5:
            return False
        ranks = sorted(ranks)
        if any(r >= 15 for r in ranks):
            return False
        return all(ranks[i] + 1 == ranks[i + 1] for i in range(4))

# ======================
# Move Generator
# ======================

class MoveGenerator:
    def __init__(self, hand):
        self.hand = sorted(hand, key=lambda c: (c.rank, c.suit or ''))

    def generate_all(self, concrete_same_rank_choices=False):
        moves = []

        # singles
        for c in self.hand:
            moves.append([c])

        # group by rank
        rank_map = {}
        for c in self.hand:
            rank_map.setdefault(c.rank, []).append(c)

        # pairs/triples/quads
        for cards in rank_map.values():
            if concrete_same_rank_choices:
                if len(cards) >= 2:
                    moves.extend(self._combinations(cards, 2))
                if len(cards) >= 3:
                    moves.extend(self._combinations(cards, 3))
                if len(cards) >= 4:
                    moves.extend(self._combinations(cards, 4))
            else:
                if len(cards) >= 2:
                    moves.append(cards[:2])
                if len(cards) >= 3:
                    moves.append(cards[:3])
                if len(cards) >= 4:
                    moves.append(cards[:4])

        # 5-10-K bombs
        for combo in self._combinations(self.hand, 3):
            if set(c.rank for c in combo) == {5, 10, 13}:
                moves.append(combo)

        # joker bomb
        jokers = [c for c in self.hand if c.rank in [SMALL_JOKER, BIG_JOKER]]
        if len(jokers) == 2:
            moves.append(jokers)

        # straights (length 5)
        unique = sorted(set(c.rank for c in self.hand if c.rank < 15))
        for i in range(len(unique) - 4):
            seq = unique[i:i + 5]
            if all(seq[k] + 1 == seq[k + 1] for k in range(4)):
                move = []
                used = set()
                for r in seq:
                    for c in self.hand:
                        if c.rank == r and c not in used:
                            move.append(c)
                            used.add(c)
                            break
                moves.append(move)

        return moves

    def _combinations(self, arr, k):
        if k == 0:
            return [[]]
        if len(arr) < k:
            return []
        res = []
        for i in range(len(arr)):
            for tail in self._combinations(arr[i + 1:], k - 1):
                res.append([arr[i]] + tail)
        return res

# ======================
# Game Environment
# ======================

class GameEnv:
    def __init__(self, players, seed=None, verbose=True):
        self.players = players
        self.seed = seed
        self.verbose = verbose
        self.reset()

    def reset(self):
        self.deck = Deck(self.seed)
        self.hands = {0: [], 1: []}
        self.points = {0: 0, 1: 0}
        self.done = False

        # tracking
        self.played_cards = []
        self.played_rank_counts = {r: 0 for r in RANKS}

        self.last_player = None
        self.last_action_was_pass = False
        self.pass_count = 0

        self.last_hand_points = 0
        self.last_hand_winner = None
        self.current_pot = 0

        # deal
        for _ in range(5):
            for p in [0, 1]:
                self.hands[p].append(self.deck.draw())

        self.face_up = {p: random.choice(self.hands[p]) for p in [0, 1]}
        self.current_player = 0 if self.face_up[0].rank > self.face_up[1].rank else 1

    def play_hand(self):
        hand_type = None
        last_move = None
        last_player = None
        pot = 0
        self.current_pot = 0

        self.last_player = None
        self.last_action_was_pass = False
        self.pass_count = 0

        while True:
            concrete_choice = self._player_wants_concrete_same_rank_choices(self.current_player)
            infoset = self._get_infoset(hand_type, last_move, concrete_same_rank_choices=concrete_choice)
            action = self.players[self.current_player].act(infoset)

            assert action in infoset["legal_actions"]
            if not concrete_choice:
                action = self._resolve_same_rank_action(self.current_player, action)

            if action is None:
                if self.verbose:
                    print(f"Player {self.current_player} PASS")

                self.last_action_was_pass = True
                self.pass_count += 1

            else:
                move = Move(action)

                if hand_type is None:
                    hand_type = move.type

                self.last_player = self.current_player
                self.last_action_was_pass = False
                self.pass_count = 0

                last_move = move
                last_player = self.current_player

                gained = self._count_points(action)
                pot += gained
                self.current_pot = pot

                if self.verbose:
                    print(f"Player {self.current_player} plays {[str(c) for c in action]} (+{gained})")

                self._remove_cards(self.current_player, action)

                for c in action:
                    self.played_cards.append(c)
                    self.played_rank_counts[c.rank] += 1

                if self.deck.size() == 0 and len(self.hands[self.current_player]) == 0:
                    winner = self.current_player
                    loser = 1 - winner
                    loser_penalty = self._count_points(self.hands[loser])
                    if self.verbose:
                        print(f"Player {winner} emptied hand with no cards left to draw.")
                        print(f"Hand winner: Player {winner} (+{pot})")
                        print(f"End bonus: Player {winner} (+20)")
                        print(f"Remaining hand penalty: Player {loser} (-{loser_penalty})")

                    self.points[winner] += pot
                    self.points[winner] += 20
                    self.points[loser] -= loser_penalty
                    self.last_hand_points = pot
                    self.last_hand_winner = winner
                    self.current_pot = 0
                    self.done = True
                    return winner

            if self.pass_count == 1:
                break

            self.current_player = 1 - self.current_player

        if self.verbose:
            print(f"Hand winner: Player {last_player} (+{pot})")

        self.points[last_player] += pot
        self.last_hand_points = pot
        self.last_hand_winner = last_player
        self.current_pot = 0

        return last_player

    def step(self):
        winner = self.play_hand()

        if self.done:
            self.current_player = winner
            return

        self._draw_phase(winner)

        if self._check_done():
            self.done = True

        self.current_player = winner

    def _draw_phase(self, winner):
        order = [winner, 1 - winner]

        while self.deck.size() > 0:
            all_full = True
            for p in order:
                if len(self.hands[p]) < 5 and self.deck.size() > 0:
                    self.hands[p].append(self.deck.draw())
                    all_full = False
            if all_full:
                break

    def _remove_cards(self, player, cards):
        for c in cards:
            self.hands[player].remove(c)

    def _same_rank_candidates(self, player, rank, k):
        cards = [c for c in self.hands[player] if c.rank == rank]
        if len(cards) < k:
            return []
        return MoveGenerator(cards)._combinations(cards, k)

    def _preserved_510k_score(self, remaining_cards):
        suit_ranks = {}
        for c in remaining_cards:
            if c.suit is None:
                continue
            suit_ranks.setdefault(c.suit, set()).add(c.rank)
        full = sum(1 for s in SUITS if {5, 10, 13}.issubset(suit_ranks.get(s, set())))
        partial = sum(len(suit_ranks.get(s, set()) & {5, 10, 13}) for s in SUITS)
        return (full, partial)

    def _resolve_same_rank_action(self, player, action):
        if action is None or len(action) not in (2, 3):
            return action
        ranks = {c.rank for c in action}
        if len(ranks) != 1:
            return action
        rank = next(iter(ranks))
        candidates = self._same_rank_candidates(player, rank, len(action))
        if len(candidates) <= 1:
            return action

        best = None
        best_score = None
        for cand in candidates:
            remaining = list(self.hands[player])
            for c in cand:
                remaining.remove(c)
            score = self._preserved_510k_score(remaining)
            suit_signature = tuple(sorted((c.suit or '') for c in cand))
            total_suit_order = sum(SUIT_ORDER.get(c.suit, -1) for c in cand)
            key = (score[0], score[1], -total_suit_order, suit_signature)
            if best_score is None or key > best_score:
                best_score = key
                best = cand
        return best if best is not None else action

    def _player_wants_concrete_same_rank_choices(self, player_idx):
        return bool(getattr(self.players[player_idx], "wants_concrete_same_rank_choices", False))

    def _count_points(self, cards):
        return sum(POINT_VALUES.get(c.rank, 0) for c in cards)

    def _check_done(self):
        # Immediate no-draw endgame resolution is handled in play_hand().
        return self.done

    def get_legal_actions(self, player, hand_type, last_move, concrete_same_rank_choices=False):
        mg = MoveGenerator(self.hands[player])
        moves = mg.generate_all(concrete_same_rank_choices=concrete_same_rank_choices)
        legal = []

        for m in moves:
            move = Move(m)

            if hand_type is None:
                legal.append(m)

            else:
                if move.type == "bomb":
                    if last_move is None or last_move.type != "bomb" or move.strength > last_move.strength:
                        legal.append(m)

                elif last_move is not None and last_move.type == "bomb":
                    continue

                elif move.type == hand_type:
                    if move.type == "straight":
                        if move.length == last_move.length and move.strength > last_move.strength:
                            legal.append(m)
                    else:
                        if move.strength > last_move.strength:
                            legal.append(m)

        if hand_type is not None:
            legal.append(None)

        return legal

    def _compute_unseen_counts(self, player):
        unseen = []
        hand_counts = {r: 0 for r in RANKS}

        for c in self.hands[player]:
            hand_counts[c.rank] += 1

        for r in RANKS:
            unseen.append(
                RANK_TOTALS[r] - hand_counts[r] - self.played_rank_counts[r]
            )

        return unseen

    def _get_infoset(self, hand_type, last_move, concrete_same_rank_choices=False):
        p = self.current_player
        opp = 1 - p

        legal = self.get_legal_actions(p, hand_type, last_move, concrete_same_rank_choices=concrete_same_rank_choices)

        return {
            "hand": deepcopy(self.hands[p]),
            "legal_actions": legal,
            "last_move": last_move,
            "hand_type": hand_type,
            "points": deepcopy(self.points),
            "deck_size": self.deck.size(),

            # core RL
            "played_cards": deepcopy(self.played_cards),
            "last_player": self.last_player,
            "last_action_was_pass": self.last_action_was_pass,
            "pass_count": self.pass_count,
            "opp_card_count": len(self.hands[opp]),

            # richer RL features
            "last_move_strength": last_move.strength if last_move else None,
            "has_control": int(self.last_player == p or self.last_player is None),
            "opp_about_to_win": int(len(self.hands[opp]) <= 2),
            "is_endgame": int(self.deck.size() == 0),
            "point_diff": self.points[p] - self.points[opp],
            "self_points": self.points[p],
            "opp_points": self.points[opp],
            "last_hand_winner_is_self": int(self.last_hand_winner == p) if self.last_hand_winner is not None else 0,

            # existing high-impact
            "unseen_counts": self._compute_unseen_counts(p),
            "hand_size": len(self.hands[p]),
            "can_empty_hand": any(a is not None and len(a) == len(self.hands[p]) for a in legal),
            "num_move_types": len(set(Move(a).type for a in legal if a is not None)),

            "last_hand_points": self.last_hand_points,
            "last_hand_winner": self.last_hand_winner,
            "current_pot": self.current_pot,
        }

# ======================
# Players
# ======================

class RandomPlayer:
    def act(self, infoset):
        return random.choice(infoset["legal_actions"])

class HumanPlayer:
    wants_concrete_same_rank_choices = True

    def act(self, infoset):
        hand = infoset["hand"]
        legal = infoset["legal_actions"]

        print("\nYour hand:")
        for i, c in enumerate(hand):
            print(f"{i}: {c}")

        print("\nLegal moves:")
        for i, move in enumerate(legal):
            if move is None:
                print(f"{i}: PASS")
            else:
                print(f"{i}: {[str(c) for c in move]}")

        while True:
            try:
                choice = int(input("Choose move index: "))
                if 0 <= choice < len(legal):
                    return legal[choice]
            except:
                pass
            print("Invalid choice.")

if __name__ == "__main__":
    print("=== Five-Ten-K Playtest ===")

    env = GameEnv([HumanPlayer(), RandomPlayer()], verbose=True)

    step = 0
    while not env.done:
        print(f"\n=== STEP {step} ===")
        print("Points:", env.points)
        print("Deck:", env.deck.size())
        print("Current player:", env.current_player)

        env.step()
        step += 1

    print("\nGame Over")
    print(env.points)
