import numpy as np
from game import Move

RANKS = [3,4,5,6,7,8,9,10,11,12,13,14,17,20,30]
RANK_TO_IDX = {r: i for i, r in enumerate(RANKS)}
POINT_VALUES = {5: 5, 10: 10, 13: 10}

MOVE_TYPES = ["none", "single", "pair", "triple", "straight", "bomb"]
MOVE_TO_IDX = {m: i for i, m in enumerate(MOVE_TYPES)}


def move_feature_dim():
    return len(MOVE_TYPES) + 9 + len(RANKS)


def encode_move(move, infoset=None):
    vec = np.zeros(move_feature_dim(), dtype=np.float32)
    base = 0

    if move is None:
        vec[MOVE_TO_IDX["none"]] = 1.0
        base = len(MOVE_TYPES)
        if infoset is not None:
            vec[base + 0] = 1.0 if infoset.get("has_control", 0) else 0.0
            vec[base + 1] = 1.0 if infoset.get("opp_about_to_win", 0) else 0.0
            vec[base + 2] = infoset.get("opp_card_count", 5) / 5.0
            vec[base + 3] = infoset.get("current_pot", 0) / 40.0
            vec[base + 4] = infoset.get("point_diff", 0) / 50.0
            vec[base + 5] = 1.0 if infoset.get("is_endgame", 0) else 0.0
            vec[base + 6] = 0.0
            vec[base + 7] = 0.0
            vec[base + 8] = 1.0
        return vec

    m = move if isinstance(move, Move) else Move(move)
    vec[MOVE_TO_IDX[m.type]] = 1.0
    base = len(MOVE_TYPES)

    pts = sum(POINT_VALUES.get(c.rank, 0) for c in m.cards)
    vec[base + 0] = len(m.cards) / 5.0
    vec[base + 1] = pts / 40.0
    vec[base + 2] = (m.strength[0] / 30.0) if m.type != "bomb" else (m.strength[0] / 4.0)
    vec[base + 3] = 1.0 if m.type == "bomb" else 0.0
    vec[base + 4] = 1.0 if (len(m.cards) == 1 and m.cards[0].rank >= 13) else 0.0

    if infoset is not None:
        hand_size = max(1, infoset.get("hand_size", len(m.cards)))
        vec[base + 5] = 1.0 if len(m.cards) == hand_size else 0.0
        vec[base + 6] = 1.0 if infoset.get("opp_about_to_win", 0) else 0.0
        vec[base + 7] = infoset.get("current_pot", 0) / 40.0
        vec[base + 8] = infoset.get("opp_card_count", 5) / 5.0
    else:
        vec[base + 5] = 0.0
        vec[base + 6] = 0.0
        vec[base + 7] = 0.0
        vec[base + 8] = 0.0

    offset = len(MOVE_TYPES) + 9
    for c in m.cards:
        vec[offset + RANK_TO_IDX[c.rank]] += 1.0
    return vec


def encode_state(infoset):
    hand = infoset["hand"]
    played = infoset["played_cards"]
    unseen = infoset["unseen_counts"]

    hand_counts = np.zeros(len(RANKS), dtype=np.float32)
    for c in hand:
        hand_counts[RANK_TO_IDX[c.rank]] += 1

    played_counts = np.zeros(len(RANKS), dtype=np.float32)
    for c in played:
        played_counts[RANK_TO_IDX[c.rank]] += 1

    unseen_counts = np.array(unseen, dtype=np.float32)

    structure = np.array([
        np.sum(hand_counts == 1),
        np.sum(hand_counts == 2),
        np.sum(hand_counts == 3),
        np.sum(hand_counts == 4),
    ], dtype=np.float32)

    control = np.array([
        float(infoset["last_action_was_pass"]),
        infoset["pass_count"] / 2.0,
        infoset["opp_card_count"] / 5.0,
    ], dtype=np.float32)

    global_state = np.array([
        infoset["deck_size"] / 54.0,
        infoset["hand_size"] / 5.0,
        infoset["last_hand_points"] / 40.0,
        infoset.get("current_pot", 0) / 40.0,
        infoset["self_points"] / 100.0,
        infoset["opp_points"] / 100.0,
    ], dtype=np.float32)

    last_move = encode_move(infoset["last_move"], infoset)

    hand_type = np.zeros(len(MOVE_TYPES), dtype=np.float32)
    if infoset["hand_type"] is None:
        hand_type[MOVE_TO_IDX["none"]] = 1.0
    else:
        hand_type[MOVE_TO_IDX[infoset["hand_type"]]] = 1.0

    extras = np.array([
        float(infoset["can_empty_hand"]),
        infoset["num_move_types"] / 5.0,
        float(infoset["has_control"]),
        float(infoset["opp_about_to_win"]),
        float(infoset["is_endgame"]),
        infoset["point_diff"] / 50.0,
        float(infoset.get("last_hand_winner_is_self", 0)),
    ], dtype=np.float32)

    return np.concatenate([
        hand_counts,
        played_counts,
        unseen_counts,
        structure,
        control,
        global_state,
        last_move,
        hand_type,
        extras,
    ]).astype(np.float32)
