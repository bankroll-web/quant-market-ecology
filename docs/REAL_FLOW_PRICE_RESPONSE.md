# Real trades and price response: timing sensitivity

Four uploaded BTCUSDT Futures hours now have a reproducible receipt-time flow/price diagnostic. It uses the same valid-episode book-change tapes as the new-hour audit. No frozen research definitions or simulation parameters were changed.

## What is measured

Starting at a valid pre-update book observation, take the next observation at least one second later inside the same verified episode. Reject endpoints more than 250 ms after the target. Sum aggressive buy and sell BTC received in the half-open interval `[start,end)`. Buyer-maker trades are aggressive sells; other trades are aggressive buys. Flow windows do not overlap. Retain windows with absolute net flow at least 1 BTC. A net buy's return is `+10,000*log(mid_end/mid_start)`; a net sell's return is its negative. Zero midpoint changes remain in the average.

Forward returns use the **end** of the flow window as the price/time origin, at 1 and 5 seconds later. They must remain in the same valid episode and meet the endpoint tolerance. Future flow is not used to select a window. Forward returns can overlap, so their row count is not an independent sample size. The midpoint is a reconstructed pre-update state, not a trade execution price. This is descriptive response, not identified causal impact or realized profit.

## Message timing

Receipt-minus-exchange timestamp differences include transmission, capture processing and any clock offset; they do not isolate exchange execution latency. None of these files has a negative age or duplicate trade ID. Tail delays are substantial:

| UTC hour | Book median age ms | Book 95th percentile ms | Trade median age ms | Trade 95th percentile ms |
| --- | ---: | ---: | ---: | ---: |
| 2026-05-25 12 | 116.6 | 394.4 | 116.8 | 560.8 |
| 2026-05-25 18 | 116.8 | 328.1 | 117.2 | 354.7 |
| 2026-05-26 15 | 148.7 | 4,240.1 | 148.5 | 2,304.0 |
| 2026-05-26 21 | 117.0 | 425.1 | 117.7 | 348.2 |

For sensitivity, a second sample rejects a whole flow window if **any** contributing trade or book observation has age outside 0–250 ms. A forward horizon additionally requires fresh book observations throughout its path. The 250 ms age threshold and 1 BTC net-flow cutoff are exploratory choices; they were not selected by optimizing the return results and have not passed independent validation. Freshness selects a different, often quieter market sample. Do not interpret its difference from the full sample as a pure latency effect.

## Results

| UTC hour | All: eligible flow windows | All: during-window mean bps | Fresh: eligible flow windows | Fresh: during-window mean bps | Fresh: next-1s windows | Fresh: next-1s mean bps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-05-25 12 | 160 | 0.394 | 75 | 0.212 | 51 | 0.047 |
| 2026-05-25 18 | 91 | 0.338 | 42 | 0.174 | 27 | 0.011 |
| 2026-05-26 15 | 557 | 0.597 | 96 | 0.367 | 42 | 0.051 |
| 2026-05-26 21 | 188 | 0.475 | 66 | 0.199 | 48 | 0.048 |

Price and net aggressive flow tend to move together **during** the selected windows. The subsequent fresh one-second average is much smaller. Fresh five-second samples have only 7–19 eligible windows per hour, which is too little to claim a reliable recovery curve. No significance or tradability claim is made; these four selected hours cover only two days, and the same-window relation is endogenous. Delayed messages strongly affect sample selection, especially in the busy 26 May 15 hour.

## Reproduce and view

After producing the four book-change tapes described in [the new-hour audit](NEW_HOURS_BOOK_CHANGE_AUDIT.md), run:

```bash
python -m src.simulation.flow_response_audit --changes-dir data/processed/book_changes_new --raw-dir RAW_FOLDER --out data/processed/flow_response_v2
python -m unittest discover -s tests -p 'test_simulation*.py'
```

Open `data/processed/flow_response_v2/real_flow_price.html`. Switch between during-window, next-1-second and next-5-second views; always read the corresponding window counts. The JSON records input hashes, message ages, and both sample definitions; CSVs retain each measured window. Python requires `pyarrow` and `zstandard` for the raw files.

Next: examine update cadence, exchange-time versus receipt-time alignment, and additional independent days before fitting impact/recovery rules to the simulator. The existing data suffices for this diagnostic. Historical options data is still needed to replace hypothetical gamma scenarios with measured option exposures; dealer signed positioning remains a separate assumption.
