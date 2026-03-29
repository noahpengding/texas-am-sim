from __future__ import annotations

import csv
import os
import tarfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from collections.abc import Mapping
from typing import Sequence

from game import Card, card_from_str
from simulation import (
    CombinationStats,
    results_to_json_payload,
    run_hero_hole_cards_games,
    run_random_games,
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


@dataclass
class _AggregateCombinationStats:
    games: int = 0
    wins: int = 0
    losses: int = 0


def _merge_result_batch(
    aggregate: dict[tuple[str, str], _AggregateCombinationStats],
    batch_results: list[CombinationStats],
) -> None:
    for row in batch_results:
        current = aggregate.get(row.hole_cards)
        if current is None:
            aggregate[row.hole_cards] = _AggregateCombinationStats(
                games=row.games,
                wins=row.wins,
                losses=row.losses,
            )
            continue
        current.games += row.games
        current.wins += row.wins
        current.losses += row.losses


def _aggregate_to_results(
    aggregate: dict[tuple[str, str], _AggregateCombinationStats],
) -> list[CombinationStats]:
    rows: list[CombinationStats] = []
    for hole_cards in sorted(aggregate.keys()):
        values = aggregate[hole_cards]
        rows.append(
            CombinationStats(
                hole_cards=hole_cards,
                games=values.games,
                wins=values.wins,
                losses=values.losses,
            )
        )
    return rows


def _resolve_games_increment(games: int, games_increment: int | None) -> int:
    if games_increment is None:
        return games
    if games_increment < 1:
        raise ValueError("games_increment must be at least 1 when provided.")
    return min(games_increment, games)


def _batch_csv_path(output: str, batch_index: int) -> Path:
    target = Path(output)
    suffix = ".csv"
    stem = target.stem if target.suffix else target.name
    batch_name = f"{stem}_{batch_index}{suffix}"
    return target.with_name(batch_name)


def _write_csv_rows(rows: Sequence[Mapping[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    headers = list(rows[0].keys()) if rows else []
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        if headers:
            writer.writeheader()
            writer.writerows(rows)


def _archive_csv_files(csv_paths: list[Path], output: str) -> Path:
    target = Path(output)
    stem = target.stem if target.suffix else target.name
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_path = target.with_name(f"{stem}_{timestamp}.tar.gz")
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, "w:gz") as archive:
        for csv_path in csv_paths:
            archive.add(csv_path, arcname=csv_path.name)

    return archive_path


def run_simulation(
    players: int = 10,
    games: int = 1000,
    seed: int | None = None,
    output: str = "simulation_results.csv",
    workers: int = 0,
    community_cards: Sequence[str] | None = None,
    holding_cards: Sequence[str] | None = None,
    games_increment: int | None = None,
) -> object:
    if games < 1:
        raise ValueError("games must be at least 1.")

    effective_workers = workers if workers > 0 else (os.cpu_count() or 1)
    fixed_community_cards = _parse_card_array(
        community_cards,
        option_name="community_cards",
        max_cards=5,
    )
    parsed_holding_cards = _parse_holding_cards(holding_cards)
    batch_games = _resolve_games_increment(games=games, games_increment=games_increment)
    payload: object = []
    csv_outputs: list[Path] = []

    completed_games = 0
    batch_index = 0

    if parsed_holding_cards is None:
        aggregate: dict[tuple[str, str], _AggregateCombinationStats] = {}
        while completed_games < games:
            current_batch_games = min(batch_games, games - completed_games)
            batch_seed = None if seed is None else seed + batch_index
            batch_results = run_random_games(
                players=players,
                games=current_batch_games,
                seed=batch_seed,
                workers=effective_workers,
                community_cards=fixed_community_cards,
            )
            _merge_result_batch(aggregate, batch_results)

            completed_games += current_batch_games

            cumulative_results = _aggregate_to_results(aggregate)
            payload = results_to_json_payload(
                results=cumulative_results,
                players=players,
                games=completed_games,
                seed=seed,
                workers=effective_workers,
            )
            csv_rows = payload if isinstance(payload, list) else []
            batch_output = _batch_csv_path(output, batch_index)
            _write_csv_rows(rows=csv_rows, output_path=batch_output)
            csv_outputs.append(batch_output)
            print(
                f"Wrote {batch_output} at {completed_games}/{games} games "
                f"using {effective_workers} workers"
            )
            batch_index += 1

        record_count = len(aggregate)
    else:
        total_wins = 0
        total_losses = 0

        while completed_games < games:
            current_batch_games = min(batch_games, games - completed_games)
            batch_seed = None if seed is None else seed + batch_index
            batch_payload = run_hero_hole_cards_games(
                players=players,
                games=current_batch_games,
                hero_hole_cards=(parsed_holding_cards[0], parsed_holding_cards[1]),
                seed=batch_seed,
                workers=effective_workers,
                community_cards=fixed_community_cards,
            )
            total_wins += int(batch_payload["wins"])
            total_losses += int(batch_payload["losses"])

            completed_games += current_batch_games

            payload = {
                "wins": total_wins,
                "losses": total_losses,
                "total_games": completed_games,
                "winning_rate": (total_wins / completed_games) if completed_games else 0.0,
            }
            batch_output = _batch_csv_path(output, batch_index)
            _write_csv_rows(rows=[payload], output_path=batch_output)
            csv_outputs.append(batch_output)
            print(
                f"Wrote {batch_output} at {completed_games}/{games} games "
                f"using {effective_workers} workers"
            )
            batch_index += 1

        record_count = 1

    archive_path = _archive_csv_files(csv_paths=csv_outputs, output=output)
    target = Path(output)
    stem = target.stem if target.suffix else target.name
    output_summary = str(target.with_name(f"{stem}_<batch-index>.csv"))
    print(f"Wrote {record_count} record(s) to {output_summary} using {effective_workers} workers")
    print(f"Archived {len(csv_outputs)} CSV file(s) to {archive_path}")
    return payload


def main() -> None:
    run_simulation(
        players=10,
        games=100000,
        seed=123,
        output="out/large_simulation_results.csv",
        workers=0,
        community_cards=None,
        holding_cards=None,
        games_increment=10000,
    )


if __name__ == "__main__":
    main()
