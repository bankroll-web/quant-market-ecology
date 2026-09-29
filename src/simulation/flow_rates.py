"""Fit and evaluate a small, regularized state-conditional trade-count model.

Use valid one-second ecology CSVs from the separate reconstruction prototype.
This is a descriptive Poisson intensity layer, not a model of private information.
"""
import argparse
import csv
import json
import math
from pathlib import Path

PRIOR_SECONDS = 30.0


def read_rows(path):
    with open(path, newline="") as handle:
        for row in csv.DictReader(handle):
            yield {k: float(row[k]) for k in ("top_obi", "bid_depth_10bps", "ask_depth_10bps",
                                                  "buy_count", "sell_count")}


def depth_cutoffs(rows):
    depths = sorted(r["bid_depth_10bps"] + r["ask_depth_10bps"] for r in rows)
    if len(depths) < 30:
        raise ValueError("Need at least 30 valid book seconds to fit depth regimes")
    return [depths[len(depths) // 3], depths[2 * len(depths) // 3]]


def state(obi, depth, cutoffs):
    imbalance_bin = 0 if obi < -.25 else 2 if obi > .25 else 1
    depth_bin = 0 if depth < cutoffs[0] else 2 if depth >= cutoffs[1] else 1
    return f"obi{imbalance_bin}_depth{depth_bin}"


def fit(rows, prior_seconds=PRIOR_SECONDS):
    rows = list(rows)
    cutoffs = depth_cutoffs(rows)
    global_buy = sum(r["buy_count"] for r in rows) / len(rows)
    global_sell = sum(r["sell_count"] for r in rows) / len(rows)
    groups = {f"obi{i}_depth{j}": {"seconds": 0, "buy": 0., "sell": 0.}
              for i in range(3) for j in range(3)}
    for r in rows:
        g = groups[state(r["top_obi"], r["bid_depth_10bps"] + r["ask_depth_10bps"], cutoffs)]
        g["seconds"] += 1
        g["buy"] += r["buy_count"]
        g["sell"] += r["sell_count"]
    rates = {}
    for key, g in groups.items():
        exposure = g["seconds"] + prior_seconds
        rates[key] = {
            "seconds": g["seconds"],
            "buy_per_second": (g["buy"] + prior_seconds * global_buy) / exposure,
            "sell_per_second": (g["sell"] + prior_seconds * global_sell) / exposure,
        }
    return {"depth_cutoffs_btc": cutoffs, "obi_cutoffs": [-.25, .25],
            "prior_exposure_seconds": prior_seconds, "global_buy_per_second": global_buy,
            "global_sell_per_second": global_sell, "training_valid_seconds": len(rows),
            "rates": rates,
            "formula": "posterior_rate=(state_trade_count + prior_seconds*global_rate)/(state_seconds + prior_seconds)"}


def rate_for_state(model, obi, depth):
    return model["rates"][state(obi, depth, model["depth_cutoffs_btc"])]


def score(rows, model):
    rows = list(rows)
    scores = {"conditional": 0., "constant": 0.}
    for r in rows:
        g = rate_for_state(model, r["top_obi"], r["bid_depth_10bps"] + r["ask_depth_10bps"])
        for side in ("buy", "sell"):
            k = r[side + "_count"]
            for name, rate in (("conditional", g[side + "_per_second"]),
                               ("constant", model["global_" + side + "_per_second"])):
                scores[name] += rate - k * math.log(rate) + math.lgamma(k + 1)
    return {"holdout_valid_seconds": len(rows), "poisson_nll_per_second":
            {key: value / len(rows) for key, value in scores.items()},
            "note": "Lower NLL is better; the constant baseline uses training-hour mean counts."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", required=True, type=Path)
    parser.add_argument("--holdout", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    model = fit(read_rows(args.train))
    model["training_source"] = args.train.name
    model["holdout_source"] = args.holdout.name
    model["holdout_score"] = score(read_rows(args.holdout), model)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(model, indent=2) + "\n")
    print(json.dumps(model["holdout_score"], indent=2))


if __name__ == "__main__":
    main()
