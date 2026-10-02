# Live market ecology laboratory

Open https://market-ecology-live-observer.onrender.com/ecology.html after deployment. The original order-book observer remains at the root. Both are read-only: there is no order submission, account connection or live learning.

## What you can see

1. Real BTCUSDT USD-M midpoint, sequence-checked displayed liquidity and freshness. A stale or invalid book pauses experiments and resets the rolling volatility sample.
2. Independent frozen-book interventions every second: 0.1 BTC buy, 10 BTC buy/sell, 50% uniform liquidity withdrawal, and a buy followed by an assumed long/short-gamma hedge. Filled/unfilled quantities, VWAP and midpoint changes show how much known displayed liquidity supports the order. An exhausted side makes the midpoint unknown.
3. A 30-second synthetic participant simulation initialized every 10 seconds from the current book. Compare baseline, maker-B withdrawal and assumed short-gamma paths on the same seeded arrival tape. The participant table reports final inventories, cash and marked wealth for the baseline.
4. An illustrative 60-second zero-drift GBM Monte Carlo range after 61 consecutive fresh one-second observations. This range is not a calibrated forecast interval or trading signal.

The orange frozen-book line is a sequence of separate counterfactual experiments. It is not an actual or simulated continuous market path. The separate participant chart is a synthetic simulated path initialized at the timestamp displayed below it. Missing observations must not be read as zero impact.

## Mathematics, units and assumptions

**Displayed-book walking:** for an order Q, consume best eligible levels in price order. At each level i, filled quantity is min(remaining Q, displayed q_i). VWAP is sum(p_i q_filled_i)/sum(q_filled_i). No order modifies the observer's real book. Quantities use Decimal arithmetic. Impact is the change in best-bid/best-ask midpoint, reported as USDT and 10,000*(new midpoint/old midpoint-1) bps. There is no recovery, latency, replenishment or hidden liquidity in this immediate experiment.

**One-round hedge:** ΔH = -Γ ΔS, in BTC, for Γ in BTC/USDT. Long gamma sells after a rise; short gamma buys. Γ=±0.05 is an explicit scenario assumption. The hedge walks the already-consumed clone and can be partially filled. This is not measured GEX. Open interest alone does not identify dealer position signs.

**Participant rollout:** use the existing integer FIFO matching engine, with assumed 0.10 USDT ticks and 0.01 BTC lots. Initialize at most 20 levels per side; round bid prices down and ask prices up, floor quantities to lots and report discarded fractional quantities. The inherited orders belong to `anonymous_background`; their true owners and queue priority are unknown. Synthetic makers A/B post two levels, two lots per level, with inventory capacity ±20 lots, counted before quoting. Requoting loses priority. Inventory skew is clipped floor(q/5) ticks, shifting the quote center away from inventory. This is a baseline heuristic, not an optimal HJB solution. The anchor stays fixed at the initial book midpoint; background liquidity does not replenish. Maker B cancels quotes at seconds 10–19 in the withdrawal branch. Retail and institution roles are assigned by the simulation and cannot be inferred from live L2.

**Clustered arrivals:** reuse the paper-inspired Ogata generator: λ_i(t)=μ+sum_j sum_{u<t} α_ij exp(-β(t-u)). Assumptions: μ=1.2 events/second/type, diagonal α=0.5/second, off-diagonal α=0.1/second, β=1.5/second. Kernel spectral radius=0.4<1. Retail events carry 1–5 lots. Seed=71. The simulated institution buys 100 lots at second 10 and sells 100 lots at second 20. Each branch uses identical arrivals. Parameters are not fitted to the live feed.

**Rollout hedge and accounting:** gamma branches hedge the per-second price change once, quantized to lots and capped at ±0.50 BTC dealer inventory. Maker fees are 1 bp and taker fees 2 bps, both assumptions. W=cash+inventory_BTC*initial_anchor_USDT. Across all participants inventory sums to zero and cash/marked wealth sum to negative paid fees. Marked wealth is not realized exit profit: no terminal liquidation, funding, margin or leverage is modeled. Displayed maker fills are simulated queue fills, never historical fills. When liquidity is insufficient, orders may remain unfilled.

**Monte Carlo:** sample midpoint once per receipt-clock second; reset on stale/invalid observations or a missing sampled second. Keep up to 301 prices. Estimate unbiased variance of consecutive log returns; σ has units 1/sqrt(second). Draw 1,000 terminal scenarios with antithetic standard-normal samples (seed 731): S_T=S_0 exp(-σ²T/2+σ sqrt(T) Z), T=60 seconds. Display empirical 5th and 95th percentiles. Expected price is S_0 by assumption, not an estimated directional forecast. Constant volatility, continuous prices and Gaussian returns omit jumps, liquidation cascades, regime changes and volatility clustering; no empirical interval coverage has been validated.

**Option pricing utility:** `live_ecology.black_scholes` provides European call/put prices, spot delta and gamma with explicit positive spot, strike, expiry in years and annualized volatility, plus annualized continuously compounded rate. It assumes no yield. It is a reference model, not a model for Bitcoin's fundamental spot value. It is not applied automatically to perpetuals, inverse options or unknown contract payoffs. For a linear option on one BTC, signed contracts times contract multiplier times option gamma gives BTC/USDT hedge sensitivity. Actual option chains, expiry/settlement terms, volatility surfaces and signed-position assumptions are needed before coupling observed options to this live book. Stochastic/local volatility, jumps and option Monte Carlo remain future candidates requiring data/model selection; they are not claimed implemented here.

## Supplied books and papers

The existing [paper integration map](LEARNING_MODEL_INTEGRATION.md) and [source manifest](LEARNING_PAPER_MANIFEST.json) remain the source inventory. This extension reuses FIFO matching/accounting and stationary Hawkes flow from those modules; it adds live initialization and visible experiments. The multi-level RL sandbox, historical regression, historical replay and hypothetical gamma study remain available. Their results do not turn into a live strategy simply because live data is connected.

- Weak consistency / price-time priority: matching direction and conservation are tested; invented queues do not reconstruct actual exchange queues.
- Multi-level market making / RL: inventory capacity, baseline quoting and accounting apply in rollouts. The frozen tabular policy remains unpromoted after its previous benchmark losses. Actor-critic and deep sets have not been implemented in this integration.
- Hawkes / impulse control: clustered flow is reused, with assumed stable parameters. Ten-type event fitting, cancellation intensities and queue dynamics require additional data/calibration.
- Option market making: signed hedge feedback is an explicit assumed scenario. No observed dealer inventory, surface calibration or measured GEX is claimed.
- Macro bubbles and closing auctions remain separate; continuous BTC depth data does not supply a closing auction or long macro series.
- The salmon marketing paper remains excluded from financial matching mechanics.

## What data is needed next

The depth-only live stream cannot distinguish cancellations from executions or identify participant classes. Add synchronized aggregate trade prints and venue instrument metadata before fitting flow/size/fee models. Preserve a complete contiguous paired book/trade day, then collect additional days for fitting and untouched later evaluation. Capture persistence is still needed: Render's free filesystem is ephemeral and its service can sleep. A browser view is not durable research data collection.

For an options branch, provide a timestamped option chain (bid/ask, strike, expiry, underlying, contract multiplier/payoff/settlement), volatility surface or enough quotes to fit one, and explicit signed-position scenarios. Do not provide account secrets. None of these blocks the current assumed-gamma experiments.

## Validation and running

Run `python -m unittest discover -s tests -p 'test_simulation*.py'` with pyarrow/zstandard available for historical tests. Current integration: 42 tests pass, including immutable book clones, fill conservation, exhaustion, thinning, hedge signs/partial fills, option put-call parity, reproducible rollouts, fee/wealth conservation, inventory caps and stale-window resets. Dashboard JavaScript syntax was checked. These checks validate mechanics, not market realism or predictive accuracy.

Run the existing observer command; it now writes `ecology.html` and atomic `ecology.json` alongside `index.html`, `state.json` and `capture.jsonl`. `--replay configs/live_observer_fixture.jsonl` supplies a fabricated fixture for offline checks; replay is not live validation. Production Docker requires only aiohttp; these additional modules use the standard library and existing pure-Python matching/Hawkes modules.

Provider cooldown: HTTP 418/429 publishes unavailable state and does not reconnect until the Retry-After duration has elapsed, with conservative fallback minimums of 300/60 seconds. See Binance [general API rate-limit documentation](https://developers.binance.com/en/docs/products/derivatives-trading-portfolio-margin-pro/general-info). A successful web deployment does not imply the feed is currently available.

## Live-display freshness fix

The production dashboard accepts synchronized observations whose receipt/event age and silence are each at most 2,000 ms; it labels ages above the strict 250 ms research threshold as `live_delayed`. `research_usable` remains false for these delayed observations. This is a human-facing display allowance, not an improved latency claim or approval to train/execute a policy on delayed data. Illustrative book interventions/rollouts and rolling Monte Carlo use the display allowance and retain their research limitations. Negative clock age, sequence gaps, provider cooldowns and observations older than 2 seconds still hide current features and pause experiments. HTTP responses prohibit caching. The default DepthObserver used by strict tests/replay retains 250 ms.

## Active cloud market source

Production now explicitly uses public Kraken BTC/USD **spot**, because the Binance cloud connection reported a 131,503-second HTTP 418 cooldown. No Binance restriction is bypassed and no alternative Binance hostname or proxy is used. Binance futures and Kraken spot are distinct markets; BTC/USD quotes are USD, not USDT, and do not measure perpetual funding, basis or Binance liquidity. The UI identifies provider, instrument, product, currency and validation method. All new scenario/accounting quote units follow the active market currency; existing standalone historical Binance files remain Binance-specific.

The Kraken adapter subscribes to the public v2 book channel at depth 100, obtains the snapshot on the same socket, applies absolute quantities and zero deletions in received order, truncates to subscribed depth and checks CRC32 of the best ten levels on every book message. Decimal parsing preserves trailing precision. A checksum mismatch clears the book and reconnects for a new snapshot. The update counter is local, **not an exchange sequence ID**; `sequence_valid` is null and `book_validated` identifies the checksum check. This checksum protects the top ten levels, not the entire 100-level book. Missing timestamps hide prices until a timestamped update. Reconnects back off up to 60 seconds; no API credentials or REST requests are needed.

Sources: [Kraken public book API](https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/book) and [official checksum guide](https://docs.kraken.com/exchange/guides/websockets/book-checksum-v2). Tests include the official expected CRC32 value, deletion, mismatch/recovery, truncation and absent timestamps. The Docker command selects `--provider kraken`; standalone CLI defaults to Binance unless a provider is specified.

The cloud Kraken subscription is limited to 100 levels per side and display output is coalesced to four writes/second. Every received book update is still applied and checksum-checked. This reduces CPU/disk backlog on the free instance; larger orders may exhaust known liquidity sooner and then return unknown price impact rather than fabricated depth.
