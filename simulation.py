from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import json
from dataclasses import dataclass
import os
from pathlib import Path
from random import Random
import secrets
from tqdm import tqdm

from game import Card, best_hand_rank, card_sort_key, cards_to_str, create_deck


@dataclass(frozen=True)
class CombinationStats:
    hole_cards: tuple[str, str]
    games: int
    wins: int
    losses: int

    @property
    def winning_rate(self) -> float:
        if self.games == 0:
            return 0.0
        return self.wins / self.games


def _canonical_hole_cards(hole_cards: tuple[Card, Card]) -> tuple[Card, Card]:
    hole_sorted = tuple(sorted(hole_cards, key=card_sort_key))
    return hole_sorted[0], hole_sorted[1]


def _simulate_games_chunk(
    players: int,
    games: int,
    seed: int,
    fixed_community_cards: tuple[Card, ...],
) -> dict[tuple[Card, Card], dict[str, int]]:
    rng = Random(seed)
    deck = create_deck()
    available_deck = [card for card in deck if card not in fixed_community_cards]
    generated_count = 5 - len(fixed_community_cards)
    stats: dict[tuple[Card, Card], dict[str, int]] = {}

    for _ in tqdm(range(games)):
        cards_needed = players * 2 + generated_count
        dealt = rng.sample(available_deck, cards_needed)

        hole_cards_per_player: list[tuple[Card, Card]] = []
        for i in range(players):
            hole_cards_per_player.append((dealt[i * 2], dealt[i * 2 + 1]))
        generated_community_cards = tuple(
            dealt[players * 2 + i] for i in range(generated_count)
        )
        community_cards = (*fixed_community_cards, *generated_community_cards)

        ranks = [best_hand_rank([*hole, *community_cards]) for hole in hole_cards_per_player]
        best_rank = max(ranks)
        winners = {index for index, rank in enumerate(ranks) if rank == best_rank}

        for player_index, hole_cards in enumerate(hole_cards_per_player):
            key = _canonical_hole_cards(hole_cards)
            if key not in stats:
                stats[key] = {"games": 0, "wins": 0, "losses": 0}

            stats[key]["games"] += 1
            if player_index in winners:
                stats[key]["wins"] += 1
            else:
                stats[key]["losses"] += 1

    return stats


def _simulate_hero_chunk(
    players: int,
    games: int,
    seed: int,
    hero_hole_cards: tuple[Card, Card],
    fixed_community_cards: tuple[Card, ...],
) -> tuple[int, int]:
    rng = Random(seed)
    deck = create_deck()

    excluded_cards = set(hero_hole_cards) | set(fixed_community_cards)
    available_deck = [card for card in deck if card not in excluded_cards]
    generated_count = 5 - len(fixed_community_cards)

    wins = 0
    for _ in range(games):
        cards_needed = (players - 1) * 2 + generated_count
        dealt = rng.sample(available_deck, cards_needed)

        opponents_hole_cards: list[tuple[Card, Card]] = []
        for i in range(players - 1):
            opponents_hole_cards.append((dealt[i * 2], dealt[i * 2 + 1]))

        generated_community_cards = tuple(
            dealt[(players - 1) * 2 + i] for i in range(generated_count)
        )
        community_cards = (*fixed_community_cards, *generated_community_cards)

        hero_rank = best_hand_rank([*hero_hole_cards, *community_cards])
        opponent_ranks = [best_hand_rank([*opponent_hole, *community_cards]) for opponent_hole in opponents_hole_cards]

        best_rank = max([hero_rank, *opponent_ranks])
        if hero_rank == best_rank:
            wins += 1

    losses = games - wins
    return wins, losses


def _split_games(total_games: int, workers: int) -> list[int]:
    base = total_games // workers
    remainder = total_games % workers
    return [base + (1 if i < remainder else 0) for i in range(workers)]


def _merge_stats(
    target: dict[tuple[Card, Card], dict[str, int]],
    source: dict[tuple[Card, Card], dict[str, int]],
) -> None:
    for key, values in source.items():
        if key not in target:
            target[key] = {"games": 0, "wins": 0, "losses": 0}
        target[key]["games"] += values["games"]
        target[key]["wins"] += values["wins"]
        target[key]["losses"] += values["losses"]


def run_random_games(
    players: int,
    games: int,
    seed: int | None = None,
    workers: int | None = None,
    community_cards: tuple[Card, ...] | None = None,
) -> list[CombinationStats]:
    if players < 2:
        raise ValueError("At least two players are required.")
    if players > 10:
        raise ValueError("This simulation assumes at most 10 players.")
    if games < 1:
        raise ValueError("At least one game is required.")
    if workers is not None and workers < 1:
        raise ValueError("workers must be at least 1 when provided.")

    fixed_community_cards = community_cards or tuple()
    if len(fixed_community_cards) > 5:
        raise ValueError("At most 5 community cards can be provided.")
    if len(set(fixed_community_cards)) != len(fixed_community_cards):
        raise ValueError("Provided community cards must be unique.")

    worker_count = workers or (os.cpu_count() or 1)
    worker_count = max(1, min(worker_count, games))

    game_splits = _split_games(games, worker_count)
    game_splits = [count for count in game_splits if count > 0]
    chunk_seeds = [secrets.randbelow(2**63) for _ in game_splits]

    stats: dict[tuple[Card, Card], dict[str, int]] = {}

    if len(game_splits) == 1:
        partial = _simulate_games_chunk(
            players=players,
            games=game_splits[0],
            seed=chunk_seeds[0],
            fixed_community_cards=fixed_community_cards,
        )
        _merge_stats(stats, partial)
    else:
        with ProcessPoolExecutor(max_workers=len(game_splits)) as executor:
            futures = [
                executor.submit(
                    _simulate_games_chunk,
                    players,
                    chunk_games,
                    chunk_seed,
                    fixed_community_cards,
                )
                for chunk_games, chunk_seed in zip(game_splits, chunk_seeds, strict=True)
            ]
            for future in as_completed(futures):
                _merge_stats(stats, future.result())

    results: list[CombinationStats] = []
    for hole_cards, values in sorted(stats.items()):
        hole_str = cards_to_str(hole_cards)
        results.append(
            CombinationStats(
                hole_cards=(hole_str[0], hole_str[1]),
                games=values["games"],
                wins=values["wins"],
                losses=values["losses"],
            )
        )

    return results


def run_hero_hole_cards_games(
    players: int,
    games: int,
    hero_hole_cards: tuple[Card, Card],
    seed: int | None = None,
    workers: int | None = None,
    community_cards: tuple[Card, ...] | None = None,
) -> dict[str, float | int]:
    if players < 2:
        raise ValueError("At least two players are required.")
    if players > 10:
        raise ValueError("This simulation assumes at most 10 players.")
    if games < 1:
        raise ValueError("At least one game is required.")
    if workers is not None and workers < 1:
        raise ValueError("workers must be at least 1 when provided.")

    if len(set(hero_hole_cards)) != 2:
        raise ValueError("Holding cards must contain exactly two different cards.")

    fixed_community_cards = community_cards or tuple()
    if len(fixed_community_cards) > 5:
        raise ValueError("At most 5 community cards can be provided.")
    if len(set(fixed_community_cards)) != len(fixed_community_cards):
        raise ValueError("Provided community cards must be unique.")
    if set(hero_hole_cards) & set(fixed_community_cards):
        raise ValueError("Holding cards and community cards must not overlap.")

    worker_count = workers or (os.cpu_count() or 1)
    worker_count = max(1, min(worker_count, games))

    game_splits = _split_games(games, worker_count)
    game_splits = [count for count in game_splits if count > 0]
    chunk_seeds = [secrets.randbelow(2**63) for _ in game_splits]

    total_wins = 0
    total_losses = 0

    if len(game_splits) == 1:
        wins, losses = _simulate_hero_chunk(
            players=players,
            games=game_splits[0],
            seed=chunk_seeds[0],
            hero_hole_cards=hero_hole_cards,
            fixed_community_cards=fixed_community_cards,
        )
        total_wins += wins
        total_losses += losses
    else:
        with ProcessPoolExecutor(max_workers=len(game_splits)) as executor:
            futures = [
                executor.submit(
                    _simulate_hero_chunk,
                    players,
                    chunk_games,
                    chunk_seed,
                    hero_hole_cards,
                    fixed_community_cards,
                )
                for chunk_games, chunk_seed in zip(game_splits, chunk_seeds, strict=True)
            ]
            for future in as_completed(futures):
                wins, losses = future.result()
                total_wins += wins
                total_losses += losses

    return {
        "wins": total_wins,
        "losses": total_losses,
        "total_games": games,
        "winning_rate": total_wins / games,
    }


def results_to_json_payload(
    results: list[CombinationStats],
    players: int,
    games: int,
    seed: int | None,
    workers: int,
) -> list[dict[str, object]]:
    del players, games, seed, workers
    return [
        {
            "card_1": row.hole_cards[0],
            "card_2": row.hole_cards[1],
            "wins": row.wins,
            "losses": row.losses,
            "games": row.games,
            "winning_rate": row.winning_rate,
        }
        for row in results
    ]


def write_results_json(payload: object, output_path: str | Path) -> None:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
