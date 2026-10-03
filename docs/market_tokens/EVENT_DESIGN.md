# Event language design, version 1

Implemented in src/simulation/event_token_design.py. This is a reusable encoder and validation boundary, not an integrated event forecaster or live signal. It supplements the existing displayed-book encoder and daily transformer; it does not replace their results or weights.

## Implemented representation

Each event emits seven typed string tokens: scale, event type, side, relative price, log size, log inter-receipt gap, estimated participant cluster. String tokens are an intermediate schema; a training-fitted dictionary must map them to embedding IDs before neural training. Unknown fields remain explicit. No absolute price token is emitted.

Relative price is 10,000 log(event price / reference mid). The reference mid must be observed at or before event receipt, ideally the latest valid pre-event book. Size uses log(1 + base-asset quantity). Quantity units must be normalized across instruments; spot quantities and futures contract counts cannot be mixed silently. Time gap uses log(1 + seconds between receipts), then training-only quantile bins. Event-time and receipt-time must both be retained; the receipt gap describes observed arrival timing, not necessarily matching-engine timing. The first gap is missing. Episodes reset context. Out-of-training-range values get explicit under/over tokens.

fit rejects any event received after the declared training cutoff. encode rejects future reference timestamps, future events, non-increasing receipts and cross-episode previous events. Equal-timestamp batches currently require an upstream stable sequence number/order adapter rather than synthetic timestamp changes. Events require a valid positive reference mid; upstream reconstruction must invalidate crossed/gapped books before supplying events.

Types: trade, add, cancel, book_change, unknown. Add/cancel labels require actual message semantics and sequence reconstruction. Aggregated size decreases are not automatically cancellations; increases are not verified individual adds. Historical displayed-book changes therefore use book_change. Trade aggressor side and resting-book side have separate categorical values.

Participants default to unknown. A cluster tag must have a model-fit availability timestamp at or before decision time. The caller must fit clustering/scalers on training only and retain its provenance. The tag denotes an estimated behavioral cluster, never verified retail, institution or market maker. No clustering model has been trained in this integration.

## Multiple scales

available_scales joins the latest completed and received tick/minute/daily/regime frame at a decision time. It excludes future arrivals and unfinished aggregates, including today's final daily candle. Calendar period end and receipt timestamps are mandatory. Frame values and scale-specific tokenizers are supplied by upstream adapters; this change does not yet aggregate raw events into all scales.

Daily returns, relative spreads and volatility already avoid absolute price tokens in the daily model. Its quote-volume level can still drift between regimes: keep and ablate volume normalization choices on development data, then freeze before fresh evaluation. Existing weights are not compatible with a changed vocabulary without retraining.

## Model and learning contract

Start with causal decoder-style event learning. The earlier daily model uses a causally masked TransformerEncoder computational block; it is not a full autoregressive order-message simulator. Cross-asset self-supervised pretraining followed by BTC fine-tuning remains the intended comparison, with training availability enforced per asset and derivatives source.

Use separate output distributions for forward return, realized volatility and signed aggressor-flow direction at fixed horizons. Targets must close strictly after decisions and be fully known before a training cutoff. Report proper scoring rules and calibration, not only direction accuracy. Missing derivative fields get missingness tags, never zero-valued pretend observations.

Mamba is a future long-sequence comparator, not implemented or trained here. Its selective state-space approach targets efficient long sequences; market performance must still be measured: https://arxiv.org/abs/2312.00752 . Compare equal data, horizons and tuning budget against gradient boosting, linear/logistic models and unconditional priors. Feature removal is selected using development folds; repeated removal on the final evaluation would leak selection information. Include adverse outcomes and range-exceedance diagnostics.

## Simulator and hybrid contract

No thousands-of-path rollout is trustworthy merely because it produces plausible charts. Before using neural rollouts, quantify return-tail behavior at multiple horizons, volatility autocorrelation, signed-flow autocorrelation, spreads/depth, response/impact curves, event frequencies and interarrival distributions against held-out real data. Compute uncertainty using contiguous blocks and multiple seeds. Fat tails, volatility clustering and flow memory are necessary diagnostics, not sufficient proof of a realistic executable market.

Generated messages must preserve positive sizes, non-crossed books, sequence validity and conservation constraints. The existing market-maker/agent simulator should enforce fills, inventory and accounting, while a validated learned environment supplies state transitions. Do not optimize a policy in an unvalidated simulator: policies can exploit invalid fills or transitions. Cost, measured slippage, processing latency and inventory constraints must also survive replay on real observations.

promotion_gate refuses qualification unless timing/tokenizer audits, held-out fidelity, tail/clustering/memory checks, executable cost/latency replay, equal-data baseline comparison, feature ablation, a trial registry, multiple-testing adjustment and fresh forward evidence all pass. This helper checks supplied evidence flags; it does not calculate those measurements or constitute an automatic certification. It never enables orders.

## Trial accounting and deflated Sharpe

Record every architecture, seed, tokenizer, threshold, horizon, checkpoint, calibration choice and evaluated period before running new trials. The previous transformer comparison contains four neural fits, one logistic fit, an ensemble, a prior and a hold baseline; 30 checkpoint epochs per neural fit and four temperature candidates were examined on validation. Three cost assumptions are reported sensitivities. This is not a complete lifetime experiment registry for the project, so a defensible project-wide effective trial count is currently unknown.

Do not invent that count or report a deflated Sharpe probability from it. DSR accounts for selection and non-normal returns, but effective trials and dependence require explicit assumptions. Serial dependence also requires appropriate inference beyond blindly treating observations as independent. Primary reference: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf . Current transformer results remain unqualified without DSR; there is no positive claimed strategy to promote.

## Data needed to complete the integration

Contiguous real book updates and trades with sequence IDs, event/receipt timestamps, valid-book reconstruction and instrument size units. Existing eight recorded hours support encoder tests, not years of event pretraining. Funding, open interest, liquidation and option-chain/surface observations need their own receipt/publication times and historical coverage. Deribit option data do not identify institutions; gamma exposure requires explicit signed-position assumptions.

Not completed in this change: raw-feed adapters for this schema, numeric event vocabulary, participant clustering, minute/regime aggregators, event transformer/Mamba training, multi-output heads, derivative ingestion, neural rollouts, fidelity measurements, full trial registry/DSR calculation, hybrid policy training or live deployment. Six targeted encoder/boundary tests passed. The first concrete deliverable is the causally constrained token schema; subsequent layers must consume real available data rather than fabricated labels.
