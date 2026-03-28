from __future__ import annotations

from collections import Counter
from itertools import combinations

# Rank values follow standard poker ordering where Ace is high.
RANKS = tuple(range(2, 15))
SUITS = ("C", "D", "H", "S")
RANK_TO_LABEL = {
    14: "A",
    13: "K",
    12: "Q",
    11: "J",
    10: "T",
    9: "9",
    8: "8",
    7: "7",
    6: "6",
    5: "5",
    4: "4",
    3: "3",
    2: "2",
}
LABEL_TO_RANK = {label: rank for rank, label in RANK_TO_LABEL.items()}

# A card is represented as (rank, suit), e.g. (14, "S") for Ace of Spades.
Card = tuple[int, str]
# HandRank format: (category, tie_breakers)
# category order:
# 8 straight flush, 7 four-kind, 6 full-house, 5 flush,
# 4 straight, 3 three-kind, 2 two-pair, 1 pair, 0 high-card
HandRank = tuple[int, tuple[int, ...]]


def create_deck() -> list[Card]:
    return [(rank, suit) for suit in SUITS for rank in RANKS]


def card_to_str(card: Card) -> str:
    rank, suit = card
    return f"{RANK_TO_LABEL[rank]}{suit}"


def card_from_str(value: str) -> Card:
    token = value.strip().upper()
    if len(token) < 2:
        raise ValueError(f"Invalid card format: {value}")

    suit = token[-1]
    rank_token = token[:-1]

    if suit not in SUITS:
        raise ValueError(f"Invalid suit in card: {value}")

    if rank_token == "10":
        rank_token = "T"

    if rank_token not in LABEL_TO_RANK:
        raise ValueError(f"Invalid rank in card: {value}")

    return LABEL_TO_RANK[rank_token], suit


def cards_to_str(cards: tuple[Card, ...] | list[Card]) -> tuple[str, ...]:
    return tuple(card_to_str(card) for card in cards)


def card_sort_key(card: Card) -> tuple[int, str]:
    return card[0], card[1]


def _straight_high(ranks: set[int]) -> int | None:
    # Wheel straight: A-2-3-4-5 is represented with high card 5.
    if {14, 2, 3, 4, 5}.issubset(ranks):
        return 5

    for high in range(14, 5 - 1, -1):
        needed = {high - i for i in range(5)}
        if needed.issubset(ranks):
            return high

    return None


def evaluate_five(cards: tuple[Card, ...]) -> HandRank:
    ranks = [card[0] for card in cards]
    suits = [card[1] for card in cards]

    rank_counter = Counter(ranks)
    # Sort by count desc then rank desc for deterministic tie-break ordering.
    rank_groups = sorted(rank_counter.items(), key=lambda item: (item[1], item[0]), reverse=True)
    group_counts = sorted(rank_counter.values(), reverse=True)

    is_flush = len(set(suits)) == 1
    straight_high = _straight_high(set(ranks))

    if is_flush and straight_high is not None:
        return 8, (straight_high,)

    if group_counts == [4, 1]:
        four_rank = rank_groups[0][0]
        kicker = rank_groups[1][0]
        return 7, (four_rank, kicker)

    if group_counts == [3, 2]:
        trip_rank = rank_groups[0][0]
        pair_rank = rank_groups[1][0]
        return 6, (trip_rank, pair_rank)

    if is_flush:
        return 5, tuple(sorted(ranks, reverse=True))

    if straight_high is not None:
        return 4, (straight_high,)

    if group_counts == [3, 1, 1]:
        trip_rank = rank_groups[0][0]
        kickers = sorted((rank for rank, count in rank_groups[1:] if count == 1), reverse=True)
        return 3, (trip_rank, *kickers)

    if group_counts == [2, 2, 1]:
        pair_ranks = sorted((rank for rank, count in rank_groups if count == 2), reverse=True)
        kicker = next(rank for rank, count in rank_groups if count == 1)
        return 2, (pair_ranks[0], pair_ranks[1], kicker)

    if group_counts == [2, 1, 1, 1]:
        pair_rank = next(rank for rank, count in rank_groups if count == 2)
        kickers = sorted((rank for rank, count in rank_groups if count == 1), reverse=True)
        return 1, (pair_rank, *kickers)

    return 0, tuple(sorted(ranks, reverse=True))


def best_hand_rank(seven_cards: tuple[Card, ...] | list[Card]) -> HandRank:
    if len(seven_cards) != 7:
        raise ValueError("Texas Hold'em evaluation requires exactly 7 cards.")

    best_rank: HandRank | None = None
    for combo in combinations(seven_cards, 5):
        current = evaluate_five(combo)
        if best_rank is None or current > best_rank:
            best_rank = current

    if best_rank is None:
        raise RuntimeError("Failed to evaluate hand rank.")

    return best_rank
