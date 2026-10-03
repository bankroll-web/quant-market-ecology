"""Regularized state-conditional intensities of observed L2 level changes.

Counts are displayed level increases/decreases, not maker orders or cancellations.
Only intervals within verified reconstruction episodes contribute exposure.
"""
import argparse
import csv
import json
import math
from pathlib import Path

KINDS = ("bid_add_levels", "bid_remove_levels", "ask_add_levels", "ask_remove_levels")
PRIOR_SECONDS = 30.0


def rows(path):
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            keys = ("exposure_seconds", "pre_obi_top", "pre_bid_depth_10bps", "pre_ask_depth_10bps") + KINDS
            yield {key: float(row[key]) for key in keys}


def weighted_cutoffs(data):
    values = sorted((r["pre_bid_depth_10bps"] + r["pre_ask_depth_10bps"], r["exposure_seconds"])
                    for r in data)
    total = sum(w for _, w in values)
    if total <= 0:
        raise ValueError("No positive within-episode exposure")
    result, cumulative, targets = [], 0., [total / 3, 2 * total / 3]
    for value, weight in values:
        cumulative += weight
        while targets and cumulative >= targets[0]:
            result.append(value)
            targets.pop(0)
    return result


def bucket(obi, depth, cutoffs):
    i = 0 if obi < -.25 else 2 if obi > .25 else 1
    j = 0 if depth < cutoffs[0] else 2 if depth >= cutoffs[1] else 1
    return f"obi{i}_depth{j}"


def fit(data, prior_seconds=PRIOR_SECONDS):
    data = list(data)
    cutoffs = weighted_cutoffs(data)
    total_seconds = sum(r["exposure_seconds"] for r in data)
    global_rates = {k: sum(r[k] for r in data) / total_seconds for k in KINDS}
    groups = {f"obi{i}_depth{j}": {"seconds": 0., "intervals": 0, **{k: 0. for k in KINDS}}
              for i in range(3) for j in range(3)}
    for r in data:
        group = groups[bucket(r["pre_obi_top"], r["pre_bid_depth_10bps"] + r["pre_ask_depth_10bps"], cutoffs)]
        group["seconds"] += r["exposure_seconds"]
        group["intervals"] += 1
        for k in KINDS:
            group[k] += r[k]
    fitted = {}
    for name, g in groups.items():
        fitted[name] = {"seconds": g["seconds"], "intervals": g["intervals"],
                        **{k + "_per_second": (g[k] + prior_seconds * global_rates[k]) / (g["seconds"] + prior_seconds)
                           for k in KINDS}}
    return {"depth_cutoffs_btc": cutoffs, "obi_cutoffs": [-.25, .25],
            "prior_exposure_seconds": prior_seconds, "training_intervals": len(data),
            "training_exposure_seconds": total_seconds, "global_per_second": global_rates,
            "state_rates": fitted,
            "observation": "Displayed level increases/decreases within 10 bps of the pre-event mid; decreases include executions and other causes. Not identified maker/cancel events.",
            "formula": "rate=(state_count+prior_seconds*global_rate)/(state_exposure_seconds+prior_seconds)"}


def score(data, model):
    nll = {"conditional": 0., "constant": 0.}
    seconds = 0.
    intervals = 0
    for r in data:
        dt = r["exposure_seconds"]
        if dt <= 0:
            continue
        seconds += dt
        intervals += 1
        state = model["state_rates"][bucket(r["pre_obi_top"], r["pre_bid_depth_10bps"] + r["pre_ask_depth_10bps"], model["depth_cutoffs_btc"])]
        for k in KINDS:
            count = r[k]
            for name, rate in (("conditional", state[k + "_per_second"]),
                               ("constant", model["global_per_second"][k])):
                expected = rate * dt
                nll[name] += expected - count * math.log(expected) + math.lgamma(count + 1)
    return {"holdout_intervals": intervals, "holdout_exposure_seconds": seconds,
            "poisson_nll_per_exposure_second": {k: v / seconds for k, v in nll.items()},
            "note": "Lower is better; Poisson is a diagnostic count likelihood, not a validated arrival law."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--holdout", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    model = fit(rows(args.train))
    model["training_source"] = args.train.name
    model["holdout_source"] = args.holdout.name
    model["holdout_score"] = score(rows(args.holdout), model)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(model, indent=2) + "\n")
    print(json.dumps(model["holdout_score"], indent=2))


if __name__ == "__main__":
    main()
