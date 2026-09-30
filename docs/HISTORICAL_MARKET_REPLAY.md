# Historical market replay milestone

The offline observer in `src/simulation/market_replay.py` puts real BTCUSDT price, spread, net aggressive flow and visible depth on a shared **receipt-time** timeline for four selected hours (25 May 12/18 UTC and 26 May 15/21 UTC). It supports hour selection, a second slider, play/pause and a 120-second zoom. This is a development milestone, not the final user manual or a live feed.

The diagnostic book replay now emits post-update best quotes, midpoint, spread, top imbalance and depth in addition to its existing pre-update fields. The reconstruction rules, count-model inputs and episode counters are unchanged. The observer uses the last emitted verified post-update observation inside each second. It displays no carried-forward book state for a second without an observation, and chart lines break at missing seconds or episode changes.

Trades are grouped into half-open receipt seconds, with buyer-maker trades counted as aggressive sells. Trade totals span the whole recorded second; they can include trades outside verified book episodes. A book point inside a second does **not** certify the whole second. Verified consecutive-update exposure is split over second boundaries and displayed as a fraction of one second. Displayed quantity additions and reductions are aggregate near-touch changes, not known maker orders or identified cancellations.

The quality panel shows maximum book/trade timestamp ages in the second. Receipt minus exchange timestamp includes processing and clock differences. The ≤250 ms flag is the exploratory freshness rule from the [flow response study](REAL_FLOW_PRICE_RESPONSE.md), not a proof of synchronized clocks or zero delay. Visible gaps and delay flags must be considered before interpreting apparent flow/price relations.

Reproduce from the supplied raw files (Python with `pyarrow` and `zstandard`):

```bash
python -m src.simulation.book_changes BOOK_FILES --out data/processed/replay_states
python -m src.simulation.market_replay --states-dir data/processed/replay_states --raw-dir RAW_FOLDER --out data/processed/market_replay.html
python -m unittest discover -s tests -p 'test_simulation*.py'
```

`BOOK_FILES` means the four named raw order-book files listed in [the new-hour audit](NEW_HOURS_BOOK_CHANGE_AUDIT.md). `RAW_FOLDER` must contain their matching trade files. Wait for reconstruction to finish before building the observer. Existing tapes without the new `post_*` fields must be regenerated.

Verification checks exposure partitioning, receipt-boundary trade assignment, no carried-forward prices, rejection of overlapping exposure, and agreement of regenerated tapes with the earlier audit fields/counters. No frozen experiment definition or fitted maker behavior was changed. Next development: use this synchronized inspection surface to examine timing alignment and design a regression baseline, with separate training/test periods and a clear distinction between contemporaneous explanation and future response.
