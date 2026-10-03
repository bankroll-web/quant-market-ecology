# Buying pressure under busy and quiet activity

Status: fixed hypothesis tested; no supported trading edge, no live orders or promotion.

## What was tested

Primary question: at 15 minutes, is the price response in the direction of strong trade pressure different during busy versus quiet activity? Pressure is the 15-minute signed taker volume fraction; strong means absolute fraction above 0.20. Activity is 15-minute mean trade count divided by the strictly prior 1440-minute mean. Busy is above 1.5; quiet below 2/3. Fixed choices, not tuned.

June-July 2024 is development; August is diagnostic validation already inspected. September 2024 is a separate evaluation month newly used by this recipe, but prior project daily research may have inspected these dates, so this is not claimed globally untouched. The specification was written locally before calculation, not externally preregistered.

Four checksum-verified Binance BTCUSDT spot archives cover 122 days / 175,680 contiguous minutes. Minute trade aggregates, not order-book data. Participant identity, book liquidity and receive-time metadata are absent. Features use completed data only. Hourly decisions, delayed entry at the open one complete minute after the feature minute ends, and later open exits are proxies rather than executable fills. Labels cannot cross period boundaries.

## Primary September result

32 strong-pressure busy observations over 22 active days; 147 quiet observations over 30 days. Signed return means across observations are +0.288 bps busy and -0.227 bps quiet. Signed return aligns the price move with buying or selling pressure; this is a research response measure, not a short-trading policy.

Equal-day busy minus quiet difference on 22 paired days: +4.766 bps, nominal day-bootstrap 95% interval [-8.385, +20.700]. It includes zero. No reliable busy-versus-quiet effect is established. Unequal event counts and the different equal-day estimand explain why this is not the difference of pooled observation means. No causal interpretation.

## Fixed long/flat rule

Buy only when positive pressure exceeds 0.20 and busy activity exceeds 1.5; hold 15 minutes. This rule was fixed before September calculation. 18 trades on 14 active days; only three positive days at the primary cost.

| Assumed total round-trip friction | Sum of net trade returns | Mean over 30 calendar days |
|---|---:|---:|
| 6 bps | -203.220 bps | -6.774 bps/day |
| 12 bps | -311.220 bps | -10.374 bps/day |
| 20 bps | -455.220 bps | -15.174 bps/day |

At 6 bps, the nominal bootstrap interval for mean daily return is [-13.214, -0.689] bps/day. Loss occurs even before costs: gross sum about -95.220 bps. The summed log-bps convention uses equal unit notional per trade and is not an account-equity return or realistic position-sizing backtest.

Reject this rule. Do not reverse it after seeing September and claim the reverse is validated. No ML fitting here: information content is tested before adding model complexity. Tokenization remains part of the broader laboratory, but these results do not justify adding activity context as an established profitable token.

## Full comparisons

5- and 60-minute analyses are exploratory secondary comparisons; nominal confidence intervals are not adjusted for multiple testing.

| Period | Horizon | Paired days | Equal-day busy minus quiet bps | 95% interval |
|---|---:|---:|---:|---|
| development | 15 | 38 | -4.480 | [-13.554693740449034, 5.735828168444249] |
| diagnostic_validation | 15 | 17 | 8.592 | [-26.250527899096422, 58.44895037302124] |
| evaluation | 15 | 22 | 4.766 | [-8.384500973136868, 20.699755220229378] |
| development | 5 | 38 | -2.773 | [-10.407702864327556, 5.387022099131958] |
| diagnostic_validation | 5 | 17 | 1.656 | [-7.105807151788892, 10.454604898038571] |
| evaluation | 5 | 22 | 3.832 | [-8.73699103680432, 18.960160291113713] |
| development | 60 | 38 | -2.318 | [-21.79778891778777, 17.28765108734584] |
| diagnostic_validation | 60 | 17 | -24.838 | [-67.2767098635136, 11.61566984379494] |
| evaluation | 60 | 22 | 1.675 | [-27.3857381913796, 28.587082105254645] |

## Reproduce and verification

Download BTCUSDT-1m-2024-06.zip through BTCUSDT-1m-2024-09.zip plus .CHECKSUM files from https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/ into data/raw/long_horizon. Use requirements-receipt-benchmark.txt.

```sh
python flow_activity_hypothesis.py
python -m unittest discover -s tests -p test_flow_activity_hypothesis.py
```

Three tests passed: future changes cannot alter prior features, current trade count cannot enter its historical reference, and a single day does not produce an uncertainty interval. Predictions/observations, sources and all results are saved beside this report. No thresholds were revised after evaluation.
