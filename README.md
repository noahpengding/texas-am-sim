# Texas Hold'em Monte Carlo Simulator

This project simulates Texas Hold'em outcomes with:

- 2 hole cards per player
- 5 community cards
- 10 players by default
- Standard poker hand ranking comparison (best 5 of 7 cards)

The simulation runs full games. In each game:

1. Every player is dealt 2 random cards (no replacement).
2. 5 random community cards are dealt (no replacement).
3. Winners are determined by standard Texas Hold'em ranking.
4. For every player, only the 2 hole cards are recorded and aggregated.

Optional behavior:

- You can provide fixed community cards with `community_cards` as an array of card strings.
- If fewer than 5 cards are provided, the remaining community cards are generated randomly.
- If omitted, all 5 community cards are generated randomly.
- You can provide current holding cards with `holding_cards` as an array.
- If `holding_cards` is omitted, output stays grouped by all observed hole-card combinations.
- If `holding_cards` contains exactly 2 cards, output is one summary dictionary: `wins`, `losses`, `total_games`, `winning_rate`.
- If `holding_cards` contains only 1 card, the program raises an error.

Instead of printing a table, the program writes CSV snapshot files with grouped records:

- `card_1`
- `card_2`
- `wins`
- `losses`
- `games`
- `winning_rate`

## Run with uv

Run default simulation values:

```bash
uv run main.py
```

To call with parameters, use the function from Python:

```bash
uv run python -c "from main import run_simulation; run_simulation(players=10, games=5000, workers=8, seed=42, output='out/results.csv')"
```

`workers=0` means automatic worker count from CPU cores. You can also set an explicit value, e.g. `workers=8`.

`games_increment` controls incremental CSV snapshots. If set, each batch writes a new file named like `output_0.csv`, `output_1.csv`, etc. At the end, all generated CSV snapshot files are packed into a timestamped `.tar.gz` archive.

```bash
uv run python -c "from main import run_simulation; run_simulation(players=10, games=5000, workers=8, seed=42, games_increment=1000, output='out/results_incremental.csv')"
```

## Examples

```bash
uv run python -c "from main import run_simulation; run_simulation(players=10, games=5000, workers=8, seed=42, community_cards=['AH','KD','QC'], output='out/results_fixed_board.csv')"
```

```bash
uv run python -c "from main import run_simulation; run_simulation(players=10, games=5000, workers=8, seed=42, holding_cards=['AS','KH'], output='out/results_hero_only.csv')"
```

## Performance notes

- The simulator uses `ProcessPoolExecutor` for true parallel execution across CPU cores.
- On Python 3.14 free-threaded/no-GIL builds, threads can also scale for CPU-heavy tasks, but this project currently uses multi-process execution for predictable performance and compatibility.

## Files

- `game.py`: card model and hand comparison logic
- `simulation.py`: game simulation and aggregation
- `main.py`: command-line entrypoint for CSV snapshots and archive output
