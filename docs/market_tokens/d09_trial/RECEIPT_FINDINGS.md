# Receipt-time correction to the D09 experiment

The prior report stated that the joined frozen tapes lacked receipt timestamps. That statement was too broad: D09B contains received_time_ns, and tokenizer_v1.load_hours retains it. Plain D09 lacks the latest receipt of all trades contributing to each interval. This audit reconstructs that provenance directly from the uploaded raw trades under the canonical (t0,t1] event-time rule.

All trade counts and signed-flow sums match across 258,917 frozen intervals. Of those, 2,873 (1.11%) include at least one contributing trade received after the closing book update. The worst extra delay is 7,613.61ms. This means the complete feature bundle cannot always be used when the book update arrives.

| Hour UTC | Late-trade intervals | Fraction | Maximum extra delay, ms |
|---|---:|---:|---:|
| May 25 04 | 201 | 0.85% | 245.15 |
| May 25 12 | 291 | 0.52% | 656.90 |
| May 25 18 | 187 | 0.33% | 575.07 |
| May 26 15 | 1,882 | 3.70% | 7,613.61 |
| May 26 21 | 312 | 0.44% | 591.71 |

At 167 sampled endpoints in the May 26 15-hour recording, the ten-event future book endpoint had already arrived when all contributing context features became available. This is a targeted warning about the event-time-to-live gap. The receipt audit restarts endpoint stride within each hour, so it does not enumerate precisely the same endpoint phase as the previous concatenated model comparison. Earlier forecast results remain historical event-time development results; they are not upgraded or silently rewritten.

Future decisions must use the maximum actual feature receipt across the context, plus a documented processing/watermark policy. Price-return anchors must use the valid book available at that decision, not the earlier interval mid. Targets must lie after that decision. Same-episode continuity, feed gaps, out-of-order arrivals, trade-set completeness and feature staleness still require checks. Max receipt is offline provenance; it does not provide an online guarantee that no later contributing trade exists.

The script audit_d09_receipts.py implements canonical interval receipt reconstruction, records raw source hashes and checks counts/flows. Two tests verify exact-t1 membership, max receipt and explicit no-trade provenance. No paid resources, new neural fit or live deployment occurred. RECEIPT_AUDIT.json includes further future-event and zero-quantity diagnostics. Real-time adapter repair and retraining are still required; this is the audit that identifies their boundary.
