# Censoring and overlap audit on real quote labels

Status: diagnostic only; no new training or live deployment. Uploaded originals retained separately and unmodified. Integrated copies at repository root.

## Real-data replay

Replayed the exact quote-barrier recipe on five audited, previously inspected recordings. All 4,206 survivors matched prior decision times and labels. All 5,904 attempts saved, including censored outcomes. Original observed status maps to labeled for the uploaded report. Exact integer nanosecond endpoints retained as nullable integers rather than floating timestamps.

1,698 attempts censored (28.76%): 1,591 missing deadline coverage and 107 missing entry. Every censored attempt lacks a continuous segment reaching the one-second deadline. These are segment-boundary/coverage failures under the current continuity gate; not proof the current Kraken service is malfunctioning. Historical unavailable paths cannot be reconstructed or safely replaced with neutral labels.

The diagnostic covers attempted decisions after 20 valid events, at one-second spacing inside qualified segments. It excludes invalid rows and absent recording periods before an attempt is made, so 28.76% is not an uptime estimate. Maximum consecutive failures within a segment is one. Raw sorted failure runs across recordings must not be interpreted automatically as outages.

## Volatility selection

Past-only volatility is standard deviation of the last 20 observed midpoint log changes, including the change received by the decision, in bps. It never includes the label future. It is event-scale volatility, not HAR or clock-time realized volatility.

Most values are zero; five quantile buckets collapse to one, so the original quantile trend detector cannot assess the trend. Extra zero/positive split:

| Past-volatility group | Attempts | Censored | Rate | Nominal Wilson 95% interval |
|---|---:|---:|---:|---|
| Zero | 5,543 | 1,550 | 27.96% | 26.80%-29.16% |
| Positive | 361 | 148 | 41.00% | 36.04%-46.14% |

This is a selection warning: moving periods are more often lost under the qualification/horizon design. Intervals do not adjust for serial dependence or multiple comparisons and are not a causal test. No claim of a statistically independent volatility effect. Full-sample diagnostic bins must not be reused for model features.

## Overlap

Closed purge intervals are represented for the half-open uniqueness utility as [decision,label_available+1ns). Mean uniqueness is approximately 0.9999999993; summed overlap-equivalent mass approximately 4,206. These are not a statistical effective sample size or 4,206 independent market observations.

The strict nonoverlapping greedy subset retains 2,425 labels. This apparently large reduction alongside almost-unit weights arises from exact touching receipt boundaries: +1ns makes touching endpoints overlap for strict purging, although their duration contribution is negligible. Temporal/autocorrelation and shared regimes still affect either subset. No claim the subset is statistically independent.

Original effective_sample_size function name retained for compatibility; its documentation now calls its output overlap-equivalent mass. It does not estimate variance-based ESS. Training weights must be computed only inside each training fold, not from validation/evaluation event intervals. Saved all-label weights are diagnostic only; no model used them.

## Changes and verification

12 supplied tests passed. Added a constant-volatility regression case: 13 tests now pass. Censoring tool handles constant volatility as one explicit group instead of failing on empty quantile categories. No predictive fitting or replay retuning.

```sh
python run_label_diagnostics.py
python -m unittest discover -s tests -p test_label_diagnostics.py
```

Requires the existing frozen/quote/trade files and requirements-receipt-benchmark.txt. Full attempts, uniqueness and sparse-subset flags, reasons, source hashes and diagnostics are saved here.

## Decision

Do not promote or retrain a trading model on survivors as if they represent the whole feed. First improve contiguous-data coverage or investigate the strict continuity exclusions using raw source IDs and receipts. Merely extending the permitted gap, filtering out failures, or adding overlap weights does not recover missing price paths or correct selective censoring. This audit cannot fix a live-feed fault it has not established.
