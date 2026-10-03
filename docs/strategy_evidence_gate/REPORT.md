# Strategy evidence gate

Implemented a reusable research screening gate after the historical trade-flow experiment. This is a retrospective diagnosis of that experiment and a prospective convention for future experiments; it is not a newly validated strategy. The original report and results remain unchanged.

## Diagnosis

All 18 validation candidates were checked. The only positive candidate traded twice. All candidates with at least 30 validation trades had negative net validation returns at the assumed 6 bps friction. The previous selector chose the largest validation mean without a minimum sample requirement. This was a selection weakness, not evidence of tradable skill.

## New screen

Require at least 30 validation trades, at least seven active validation days, positive mean net validation return, a positive lower daily-bootstrap confidence bound, and direction log loss below the constant baseline. Missing evidence rejects the candidate. Thirty trades and seven days are explicit screening conventions; they do not guarantee effective sample size or profitability. Dependence, multiple trials and regime coverage still require assessment.

The old run did not retain validation active days or validation daily confidence intervals for every candidate. The screen marks these missing rather than fabricating them. Even ignoring those missing fields, no candidate clears both the trade-count and positive-return conditions.

Zero of 18 candidates passes. WAIT remains. Passing a screen permits further independent evaluation only; qualified and orders_enabled remain false. This module is a research utility, not a deployed live-observer change or a broker connection.

## Next experimental boundary

June-August 2024 has been inspected and is development material now. Do not tune against it and claim an untouched test. A future recipe should register its economic hypothesis and selection rules before opening a distinct evaluation period. More expressive models must still beat numeric baselines. Priority is identifying whether flow pressure behaves differently when participation is unusually high or low, using causal trailing normalization and separate development data. Do not infer participant identity from these aggregates.

## Run

```sh
python strategy_evidence_gate.py
python -m unittest discover -s tests -p test_strategy_evidence_gate.py
```

Four tests passed: lucky single trade rejected, baseline failure rejected, missing uncertainty rejected, and a passing screen does not authorize orders. Full rejection reasons are in RESULTS.json and prospective rules in RULES.json.
