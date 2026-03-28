from __future__ import annotations

import os
from typing import Sequence

from game import Card, card_from_str
from simulation import (
    results_to_json_payload,
    run_hero_hole_cards_games,
    run_random_games,
    write_results_json,
)


def _parse_card_array(
    values: Sequence[str] | None,
    *,
    option_name: str,
    max_cards: int,
) -> tuple[Card, ...]:
    if values is None:
        return tuple()

    if len(values) > max_cards:
        raise ValueError(f"{option_name} supports at most {max_cards} cards.")

    cards: list[Card] = []
    for item in values:
        cards.append(card_from_str(item))

    if len(set(cards)) != len(cards):
        raise ValueError(f"{option_name} must not contain duplicates.")

    return tuple(cards)


def _parse_holding_cards(values: Sequence[str] | None) -> tuple[Card, ...] | None:
    if values is None:
        return None
    if len(values) == 1:
        raise ValueError("holding_cards with one card is invalid. Provide exactly two cards.")
    if len(values) != 2:
        raise ValueError("holding_cards must contain exactly two cards when provided.")
    cards = _parse_card_array(values, option_name="holding_cards", max_cards=2)
    return cards


def run_simulation(
    players: int = 10,
    games: int = 1000,
    seed: int | None = None,
    output: str = "simulation_results.json",
    workers: int = 0,
    community_cards: Sequence[str] | None = None,
    holding_cards: Sequence[str] | None = None,
) -> object:
    effective_workers = workers if workers > 0 else (os.cpu_count() or 1)
    fixed_community_cards = _parse_card_array(
        community_cards,
        option_name="community_cards",
        max_cards=5,
    )
    parsed_holding_cards = _parse_holding_cards(holding_cards)

    if parsed_holding_cards is None:
        results = run_random_games(
            players=players,
            games=games,
            seed=seed,
            workers=effective_workers,
            community_cards=fixed_community_cards,
        )
        payload = results_to_json_payload(
            results=results,
            players=players,
            games=games,
            seed=seed,
            workers=effective_workers,
        )
        record_count = len(results)
    else:
        payload = run_hero_hole_cards_games(
            players=players,
            games=games,
            hero_hole_cards=(parsed_holding_cards[0], parsed_holding_cards[1]),
            seed=seed,
            workers=effective_workers,
            community_cards=fixed_community_cards,
        )
        record_count = 1

    write_results_json(payload=payload, output_path=output)
    print(f"Wrote {record_count} record(s) to {output} using {effective_workers} workers")
    return payload


def main() -> None:
    run_simulation(
        players=10,
        games=1000000,
        seed=123,
        output="large_simulation_results.json",
        workers=0,
        community_cards=None,
        holding_cards=None,
    )


if __name__ == "__main__":
    main()
