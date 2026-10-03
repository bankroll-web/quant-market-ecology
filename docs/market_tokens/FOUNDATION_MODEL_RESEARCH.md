# Larger models for Bitcoin market tokens: researched integration options

The aim remains Bitcoin event tokenization and market ecology. Model size is a comparison variable, not a profitability certificate. No larger pretrained model has been installed, trained or promoted in this research step.

| Candidate | Primary source | Fit to our data and current status |
|---|---|---|
| TradeFM | https://arxiv.org/abs/2602.23784 and https://arxiv.org/html/2602.23784v1 | Close conceptual fit for trade-flow token learning; equity data and proprietary pretraining corpus. We have not verified a downloadable checkpoint. |
| LOBS5 | https://arxiv.org/abs/2309.00638 and https://github.com/peernagy/LOBS5 | Autoregressive tokenized message learning with structured state-space layers. Different source/message semantics need an adapter; not installed. |
| LOBERT | https://arxiv.org/abs/2511.12563 | Encoder-style representation learning combining message tokens with continuous price/volume/time. A conceptual comparator, not a plug-in for our vocabulary. |
| Kronos | https://github.com/shiyu-coder/Kronos | Pretrained candlestick tokenizer/model. Public base is 102.3M parameters; listed large is 499.2M and not open in the official table. Retain only a candle benchmark under the user's event-first preference. |

TradeFM's authors describe a 524M-parameter decoder trained on 10.7 billion training tokens, with scale-invariant event features, grouped-query attention and rotary positions. Their largest training setup uses three 80GB A100 GPUs. The paper reports simulator fidelity and geographic transfer; that does not establish profitable Bitcoin execution. Adoptable ideas are normalized market features, explicit tail categories, broad self-supervised learning and deterministic simulation constraints. Our five-hour corpus is not comparable in breadth. Training the published model from scratch is not a free CPU experiment; this research does not purchase compute or claim access to its proprietary data.

LOBS5 demonstrates message-level sequence modeling with state-space layers, using a source representation different from aggregated D09 liquidity intervals. Preserve unknown order/participant semantics rather than inventing IDs to satisfy an external model interface. A longer sequence model cannot repair feed misalignment.

LOBERT motivates comparing discretized tokens with continuous feature representations. A hybrid input could retain numeric tail detail that quantile bins lose, but this is a proposed experiment, not an implemented LOBERT replica. Preserve causal masking when adapting bidirectional representation learning for forecasting; do not let later messages enter a prediction.

Kronos pretrained weights require their corresponding tokenizer. Replacing it with our custom event IDs does not preserve learned token meanings. Its published input is OHLC(V); it will not directly consume our event language. No conclusion that the largest accessible model is the best Bitcoin predictor is justified by parameter counts.

## Concrete development order

1. Complete receipt-time repair identified in d09_trial/RECEIPT_FINDINGS.md: feature availability, processing/watermarks, decision-time price anchors and future-only labels.
2. Replicate on additional contiguous days with raw trades/books, metadata and source hashes. Reserve a new period before inspecting it.
3. Compare fixed-budget baseline and neural architectures on equal inputs. Include token-only versus hybrid numeric inputs, small versus larger models, and pretrained versus from-scratch initialization where a compatible checkpoint is actually available. Record every trial and use dependence-aware score uncertainty.
4. Run feature ablations only on development folds. Do not select features by repeatedly inspecting the final period.
5. Evaluate an executable policy with fees, slippage, latency, queue assumptions and inventory constraints. A model that improves token likelihood or volatility error may still be unprofitable. Survival rules must evaluate net conserved equity, including capital transfers, estate balances and liquidation costs.

Completed in this step: primary-source research and actual raw-trade receipt reconciliation, with two targeted tests. Deferred: pretrained downloads, architecture scaling fits, forward evaluation, receipt-corrected retraining and a validated profitable strategy. The existing laboratory stays unqualified for automatic orders.
