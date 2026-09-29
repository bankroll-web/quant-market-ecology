# Four new BTCUSDT hours: book-change diagnostic audit

This is a **new evaluation** of the frozen-on-00-UTC, nine-state *simulation diagnostic* in `configs/simulation_v1_book_change_rates.json`. The previously held-out 2026-05-25 04 UTC hour was not used to change its states, shrinkage or cutoffs. Neither were the four hours below. Lower Poisson negative log likelihood (NLL) per verified exposure second is better. A displayed level decrease is not an identified maker cancellation, and this count likelihood is not a price-impact or profit score.

| BTCUSDT Futures UTC hour | Valid states | Verified exposure (s) | Conditional NLL/s | Constant NLL/s | Conditional minus constant | Result |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2026-05-25 04 (earlier holdout) | 23,749 | 636.15 | 935.11 | 908.65 | +26.46 | Worse |
| 2026-05-25 12 | 55,811 | 1,504.53 | 898.488 | 898.356 | +0.132 | Slightly worse |
| 2026-05-25 18 | 57,499 | 1,565.25 | 774.475 | 777.754 | -3.279 | Better |
| 2026-05-26 15 | 51,067 | 1,369.68 | 2,247.474 | 2,292.509 | -45.035 | Better |
| 2026-05-26 21 | 71,608 | 1,923.70 | 932.326 | 901.019 | +31.307 | Worse |

The conditional model wins two of the four new hours and loses two; the earlier 04 UTC holdout also lost. Activity and NLL scale vary greatly across hours. This is **mixed evidence**, not a validated state-dependent maker process. Do not tune thresholds on these holdouts and do not wire the fitted table into the maker agents. The current simulator's cancellation and replenishment fractions remain explicit scenario assumptions.

## Reconstruction checks and provenance

The same `src/simulation/book_changes.py` episode-aware replay produced these counters. Exposure excludes invalid gaps and the first bridge of each episode. No frozen D06, D07 or experiment definition was edited.

| Hour | Valid bridges | Invalid bridges | Stale updates | Continuous updates | Within-episode intervals |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-05-25 12 | 234 | 8 | 645 | 55,577 | 55,555 |
| 2026-05-25 18 | 103 | 3 | 295 | 57,396 | 57,366 |
| 2026-05-26 15 | 215 | 7 | 718 | 50,852 | 50,845 |
| 2026-05-26 21 | 143 | 8 | 389 | 71,465 | 71,429 |

Input order-book SHA-256:

- `BTCUSDT_orderbook_2026-05-25_12(1).parquet`: `d6ca20c84acf58204deee2c4a4d77170bf7b4c06252592398f99040b85a4b788`
- `BTCUSDT_orderbook_2026-05-25_18(1).parquet`: `5da73308012697bd98d11a064515d3723da1164f374dca361f5fab2f60fc4df5`
- `BTCUSDT_orderbook_2026-05-26_15.parquet`: `9b94141910e590ad8329204c6b11e2812e52da56dc2e4c98e4e9ce5882865c8e`
- `BTCUSDT_orderbook_2026-05-26_21.parquet`: `2c4087341935d71efb0aba5b8ba1a68158ffd499cae547e499b6fd3a255bfec6`

The re-uploaded 2026-05-25 00/04 order books and trades were byte-identical to the earlier samples (SHA-256 prefixes `6c252e43e31abc3f`, `9b2a0a4113b3973a`, `17e184557837f279`, `dd29b20050291e73`). The 2026-05-26 03/09 trade hours have no matching book files in this upload. Trades were **not** used to produce the book-change likelihood scores in this note.

Matching raw trade files do show differing activity; these counts are descriptive and do not identify participant type:

| UTC hour | Raw trade rows | Mean trade size (BTC) | Median trade size (BTC) | 99th percentile size (BTC) |
| --- | ---: | ---: | ---: | ---: |
| 2026-05-25 12 | 65,031 | 0.03927 | 0.002 | 0.723 |
| 2026-05-25 18 | 34,550 | 0.03543 | 0.002 | 0.714 |
| 2026-05-26 15 | 346,798 | 0.04664 | 0.001 | 0.799 |
| 2026-05-26 21 | 51,018 | 0.03799 | 0.002 | 0.684 |

The 26 May 15 UTC hour has much more trade activity than the other three. This is a reason to examine regime dependence and event-size distributions rather than adopting one constant trade-arrival rate.

## Reproduction and next test

Given the named raw book files, run `python -m src.simulation.book_changes FILES --out data/processed/book_changes_new`, then call `score(rows(OUTPUT_CSV), model)` from `src.simulation.book_change_rates` using the committed JSON model. Run each completed output after replay exits; a CSV being written is not a valid holdout.

Next, estimate actual size-conditioned price response with tightly matched book/trade receipt times and valid episodes, then test it on **different days**, including zeros and uncertainty across independent hours. A one-second signed-flow association is not causal impact: aggressive flow can react to price, book and trade messages arrive with different latency, and most quiet windows have no midpoint change. Validate time alignment before using it to set the simulated agents' size or impact parameters. For continuous intraday recovery across the existing 00–04 gap, matching depth and trades for 2026-05-25 01–03 UTC are still needed.
