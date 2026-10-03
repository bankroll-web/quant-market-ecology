# Frozen ecology replication: two additional historical periods

Completed 3 October 2026 (South Africa). **The liquidity reinforcement association replicated in both additional recordings; the frozen explanatory regression failed severely in one.** This separates a repeated observation from a transferable quantitative calibration.

## What was frozen

The first study's 25 May 00:00 pressure threshold, thin-depth cutoff, all three ridge fits, normalization, observation windows, freshness rule and bootstrap procedures were retained. No fitting, threshold search, event exclusion chosen from outcomes, or policy promotion occurred. Baseline commit: `cd587f84e104c2149f50ebd1ab71fb103b0c1160`. The executable replication checks the baseline JSON's SHA-256 and both observation/reconstruction source-file hashes before running.

These 03:00 and 09:00 recordings come from the same historical two-day archive. They add two periods outside the six-recording study, **not new contiguous days**. Other earlier project work may have inspected them; they are not certified untouched final tests. They are also earlier than some existing comparison hours, although later than the 25 May training hour.

## Source integrity and observation boundary

The 03:00 book was recovered from its saved original Parquet. The 09:00 book was recovered as a 255,620,367-byte legacy CSV and streamed into Parquet. Nanosecond timestamps were read directly as int64; update IDs written with decimal `.0` notation were parsed as exact decimals and safely cast to integers. This preserves the supplied CSV representation, but cannot restore precision or provenance lost before the CSV was created. Structural footer/row-count checks and the same sequence replay were applied. Previously computed feature files were not used.

The two source trade files have no duplicate IDs, backward receipt steps or missing-ID gaps. They contain **266 zero-price/zero-quantity NA payload records**. The study rejected **79 otherwise eligible windows containing those records**. Source hashes, reconstruction counts, conversion provenance and timing quantiles are in [summary.json](mechanics_replication/summary.json).

The final sample contains **2,289 approximately one-second windows**, with **2,032** satisfying the additional 250 ms message-age restriction. Accepted durations total **38.68 minutes**, spread across discontinuous verified segments.

| Period, UTC | Accepted windows | Fresh windows | Reconstructed book intervals |
|---|---:|---:|---:|
| 2026-05-26_03 | 1173 | 1082 | 49,143 |
| 2026-05-26_09 | 1116 | 950 | 50,898 |

## Repeated ecology observation

Condition on the **original frozen high-pressure threshold**. A positive directional midpoint response means movement with aggressive trading pressure. Displayed reinforcement means bid additions/ask reductions during buy pressure, or ask additions/bid reductions during sell pressure. Opposition reverses those signs. These are anonymous displayed changes, not identified market-maker actions. Reductions cannot be separated into cancellations and executions.

| Period | Reinforces: n / mean bps | Opposes: n / mean bps | Difference, exploratory 95% interval | Fresh-only difference, 95% interval |
|---|---:|---:|---|---|
| 2026-05-26_03 | 173 / 0.448 | 57 / 0.192 | 0.255 [0.075, 0.421] | 0.187 [0.061, 0.328] |
| 2026-05-26_09 | 119 / 0.356 | 39 / 0.060 | 0.297 [0.155, 0.416] | 0.202 [0.062, 0.311] |

Both positive contrasts exclude zero under the one-minute block bootstrap and remain positive with intervals excluding zero under 30-second and 120-second blocks and the freshness subset. Confidence intervals use 1,000 draws, preserve shared block resamples between groups, and are exploratory rather than multiple-comparison adjusted. Group sizes, trading magnitude, volatility and hidden liquidity are not matched. A same-window conditional association does not establish a causal liquidity effect or a trading edge.

| Period | Price moves with pressure when liquidity reinforces | When liquidity opposes | High-pressure midpoint unchanged |
|---|---:|---:|---:|
| 2026-05-26_03 | 58.4% | 31.6% | 45.2% |
| 2026-05-26_09 | 52.1% | 20.5% | 52.5% |

## Frozen regression failure and its mechanism

These fits explain a response already observed during the same window; they do not forecast future price. Best-quote OFI includes quote movement. Negative R² indicates performance worse than the evaluation period's realized constant mean.

| Period | Trade-only R² | Book-only R² | Joint R² | Fresh book-only R² |
|---|---:|---:|---:|---:|
| 2026-05-26_03 | -0.528 | -12.728 | -8.545 | -33.728 |
| 2026-05-26_09 | 0.117 | 0.533 | 0.527 | 0.650 |

At 03:00, the worst 1% of windows account for **98.6% of the book-only fit's squared error**. Normalized OFI has standard deviation **15.34**, versus **3.49** in training. In the largest-error window, initial average best-quote depth is **0.226 BTC**; accumulated OFI divided by this small initial queue is **-462.99**. The fixed linear calibration assigns a **-39.76 bps** move, while the observed move is **-0.947 bps**. That window passes the freshness test.

This is a demonstrated **extrapolation/normalization failure**: a small initial queue can create an extreme ratio while liquidity evolves within the window. It does not show that the observed book is meaningless. The diagnostic was added after inspecting the failure; no extreme windows were removed and no replacement fit was selected. A future bounded or nonlinear response model, dynamic depth treatment and robust calibration require a separate frozen comparison on additional data.

## Subsequent price response

| Period | Five-second outcomes available / missing | Next-five-second aligned mean bps, exploratory 95% interval |
|---|---:|---|
| 2026-05-26_03 | 151 / 79 | 0.098 [-0.030, 0.239] |
| 2026-05-26_09 | 61 / 97 | 0.052 [-0.093, 0.226] |

Both overall high-pressure five-second intervals cross zero. The reinforcing-liquidity subgroup at 03:00 has a positive exploratory interval, but subgroup inspection, missing paths and absent execution costs preclude calling it a validated trade. Future price responses condition on verified observable book paths; censoring may bias the distributions.

## Consequence for development

Across the original six periods and these two additions, the reinforcement mean contrast is positive in all eight, with exploratory one-minute intervals excluding zero in four. These are dependent observations from only two days, not eight independent replications across market regimes.

Keep the observational ecology layer: trading pressure, opposing/reinforcing displayed liquidity, depth, price reaction and confidence. **Do not promote the frozen linear impact model into live trading or use it as a universal simulator calibration.** The next calibration experiment should specify bounded response/dynamic-depth hypotheses before evaluating them on new contiguous same-venue days. A simulator should reproduce joint reaction distributions and transition behavior, with explicit anonymous-role assumptions; this comparison does not complete that simulator.

No live policy, real-money trading or cross-venue transfer was enabled. The earlier [full ecology study](ECOLOGY_PRICE_MECHANICS.md) contains the definitions, primary research sources and foundational limitations. Full distributions and diagnostics are saved per hour in [mechanics_replication](mechanics_replication).

## Reproduce

```bash
python -m src.simulation.csv_book_to_parquet <original-09-book.csv> <books-dir>/BTCUSDT_orderbook_2026-05-26_09.parquet
python -m src.simulation.book_changes <original-03-book.parquet> <books-dir>/BTCUSDT_orderbook_2026-05-26_09.parquet --out data/processed/mechanics_replication_states
python -m src.simulation.ecology_mechanics_replication --baseline docs/price_mechanics/summary.json --books-dir <books-dir> --trades-dir <trade-originals> --states-dir data/processed/mechanics_replication_states --out data/processed/mechanics_replication
python tools/report_mechanics_replication.py --source data/processed/mechanics_replication/report.json --out docs/mechanics_replication
python -m unittest discover -s tests -p 'test_simulation*.py'
```

Place the original 03:00 Parquet in books-dir as well as the converted 09:00 file. CSV conversion requires pyarrow; analysis also requires numpy and zstandard. Source bytes are not redistributed. Tests additionally verify one-nanosecond timestamp precision, integral decimal IDs, rejection of fractional IDs and altered-baseline rejection.

