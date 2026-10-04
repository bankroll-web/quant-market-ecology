# Why audited quote segments end

Completed attribution of all 1,698 censored attempts from the prior real-data label audit. No model fitting, gap tolerance changes or live deployment.

2,189 qualified segments across five previously inspected recordings. Median duration 1,431.6 ms; first quartile 610.7 ms, third quartile 3,155.5 ms, maximum 70,315.3 ms. One-second labels plus entry latency and coverage requirements cannot be obtained near many segment ends.

## Exclusive cause combinations for censored attempts

| Observed gate failure at next row | Attempts |
|---|---:|
| Receipt gap >250ms and event age >250ms | 1,010 |
| Event age >250ms alone | 310 |
| Next post-event state cannot be confirmed | 377 |
| Next post-event state and depth/imbalance confirmation unavailable | 1 |
| Total | 1,698 |

Event age accounts for 1,320 / 1,698 = 77.74% of these attempt endings, with 1,010 also failing receipt-gap bounds. Post-state confirmation accounts for the remaining 378. Categories explain the audited continuity gate; they are not raw exchange sequence-ID loss diagnoses. Row/post-state confirmation relies on the following reconstructed row, so boundary or reconstruction issues may exclude a quote even when the received message itself exists.

No model was retrained. Timing tolerance was not relaxed. All prior rejected attempts were matched to their continuous segment endpoint exactly. Full per-segment and per-attempt cause records saved; source hashes inherited from the receipt adapter.

## What this resolves

The historical experiment is fragmented primarily by the 250ms freshness/receipt gate, with additional post-state confirmation boundaries. This provides a concrete explanation for limited horizon coverage and selective censoring. It does not establish a malfunction in the current Kraken live observer or show what the price did across invalid spans. Overlap weights cannot restore those missing outcomes.

## Next implementation boundary

Use raw source snapshots/update IDs to distinguish delays with an intact book sequence from genuine sequence gaps, and derive post-event features directly from the reconstructed current book where possible. Maintain separate flags for book sequence validity, receive freshness, and outcome coverage. A live model can use the state that was genuinely available locally even if its exchange timestamp is old, but that is a different documented information policy; it cannot be substituted into the existing benchmark after seeing results and called confirmation.

Historical missing paths remain censored. Compare alternative policies only as declared development experiments, retaining the original audit. Fresh contiguous recordings and actual execution assumptions remain necessary before strategy promotion.

## Reproduce

```sh
python audit_segment_endings.py
```

Requires the frozen tape, uploaded raw trade files and prior label-diagnostics attempts. Two consistency assertions check the rejected-attempt count and exact segment endpoint for every rejection. These are diagnostic consistency checks, not profitability tests.
