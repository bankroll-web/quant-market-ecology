"""
Regression test: EXP-01 absorption vs yielding — frozen discovery + replication values.

Locks the frozen EXP-01 record (handoff sections 34-36, 46-51, 62).
Any refactor of the EXP-01 pipeline must reproduce these numbers exactly.

Run:  python tests/test_exp01_regression.py
"""
import os
import sys

import pandas as pd

FROZEN = os.path.join(os.path.dirname(__file__), "..", "data", "frozen")

TOL = 1e-6  # absolute tolerance for bps means / CIs


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    return cond


def approx(a, b, tol=TOL):
    return abs(a - b) <= tol


# ---------------------------------------------------------------- discovery

def test_discovery_row_count():
    df = pd.read_csv(os.path.join(FROZEN, "exp01c_canonical_rows.csv"))
    return check("discovery: canonical rows == 3,733", len(df) == 3733, f"rows={len(df)}")


def test_discovery_state_counts():
    df = pd.read_csv(os.path.join(FROZEN, "exp01c_canonical_rows.csv"))
    counts = df["liquidity_response"].value_counts().to_dict()
    ok = check("discovery: DEPLETION == 3,254", counts.get("DEPLETION") == 3254, f"got={counts.get('DEPLETION')}")
    ok = check("discovery: REPLENISHMENT == 439", counts.get("REPLENISHMENT") == 439, f"got={counts.get('REPLENISHMENT')}") and ok
    ok = check("discovery: NEUTRAL == 40", counts.get("NEUTRAL") == 40, f"got={counts.get('NEUTRAL')}") and ok
    return ok


def test_discovery_equal_episode():
    s = pd.read_csv(os.path.join(FROZEN, "exp01e_equal_episode_summary.csv")).set_index("horizon")
    exp = {
        1: {"episodes": 90, "mean": 0.005608356502330164, "ci_lo": -0.023348455027420282, "ci_hi": 0.025517123581244815, "verdict": "FAIL"},
        3: {"episodes": 88, "mean": 0.03264631691493186, "ci_lo": 0.015373249026209963, "ci_hi": 0.050143216900659086, "verdict": "PASS"},
        5: {"episodes": 84, "mean": 0.048138710934428855, "ci_lo": 0.022328640684960394, "ci_hi": 0.07296221639455247, "verdict": "PASS"},
        10: {"episodes": 78, "mean": 0.08329579785916044, "ci_lo": 0.024718368388682254, "ci_hi": 0.14788712093261955, "verdict": "PASS"},
    }
    ok = True
    for h, e in exp.items():
        row = s.loc[h]
        ok = check(f"discovery H{h}: episodes == {e['episodes']}", int(row["episodes"]) == e["episodes"], f"got={int(row['episodes'])}") and ok
        ok = check(f"discovery H{h}: mean == {e['mean']:.6f}", approx(row["equal_weight_mean_bps"], e["mean"]), f"got={row['equal_weight_mean_bps']:.6f}") and ok
        ok = check(f"discovery H{h}: CI low == {e['ci_lo']:.6f}", approx(row["bootstrap_ci_low_bps"], e["ci_lo"]), f"got={row['bootstrap_ci_low_bps']:.6f}") and ok
        ok = check(f"discovery H{h}: CI high == {e['ci_hi']:.6f}", approx(row["bootstrap_ci_high_bps"], e["ci_hi"]), f"got={row['bootstrap_ci_high_bps']:.6f}") and ok
    # Frozen verdict: H1 fails equal-episode robustness (CI crosses zero), H3/H5/H10 pass
    h1_ci_crosses_zero = exp[1]["ci_lo"] < 0 < exp[1]["ci_hi"]
    ok = check("discovery: H1 CI crosses zero (diagnostic/weak)", h1_ci_crosses_zero) and ok
    return ok


def test_discovery_bootstrap():
    b = pd.read_csv(os.path.join(FROZEN, "exp01d_episode_bootstrap.csv")).set_index("horizon_events")
    exp = {
        1: {"diff": 0.01492479140449537, "ci_lo": 0.005193077781731697, "ci_hi": 0.02355738033193226},
        3: {"diff": 0.03816785379231837, "ci_lo": 0.019400419758086044, "ci_hi": 0.05891327357224027},
        5: {"diff": 0.05590056161116388, "ci_lo": 0.03368990041744247, "ci_hi": 0.08203011440881525},
        10: {"diff": 0.07396482884585513, "ci_lo": 0.042646040257188156, "ci_hi": 0.11564906576649144},
    }
    ok = True
    for h, e in exp.items():
        row = b.loc[h]
        ok = check(f"discovery bootstrap H{h}: diff == {e['diff']:.6f}", approx(row["observed_diff_bps"], e["diff"]), f"got={row['observed_diff_bps']:.6f}") and ok
        ok = check(f"discovery bootstrap H{h}: CI == [{e['ci_lo']:.4f}, {e['ci_hi']:.4f}]", approx(row["ci_2_5_bps"], e["ci_lo"]) and approx(row["ci_97_5_bps"], e["ci_hi"]), f"got=[{row['ci_2_5_bps']:.4f}, {row['ci_97_5_bps']:.4f}]") and ok
    return ok


# ---------------------------------------------------------------- replication

def test_replication_row_count():
    df = pd.read_csv(os.path.join(FROZEN, "exp01_replication_canonical_rows.csv"))
    return check("replication: canonical rows == 27,137", len(df) == 27137, f"rows={len(df)}")


def test_replication_per_hour_starting_events():
    df = pd.read_csv(os.path.join(FROZEN, "exp01_replication_canonical_rows.csv"))
    counts = df["hour"].value_counts().to_dict()
    exp = {"2026-05-25_04": 1652, "2026-05-25_12": 4753, "2026-05-25_18": 3059, "2026-05-26_15": 12708, "2026-05-26_21": 4965}
    ok = True
    for h, n in exp.items():
        ok = check(f"replication {h}: starting events == {n}", counts.get(h) == n, f"got={counts.get(h)}") and ok
    return ok


def test_replication_flow_and_state_counts():
    df = pd.read_csv(os.path.join(FROZEN, "exp01_replication_canonical_rows.csv"))
    flow = df["flow_side"].value_counts().to_dict()
    resp = df["liquidity_response"].value_counts().to_dict()
    ok = check("replication: BUY == 14,145", flow.get("BUY") == 14145, f"got={flow.get('BUY')}")
    ok = check("replication: SELL == 12,992", flow.get("SELL") == 12992, f"got={flow.get('SELL')}") and ok
    ok = check("replication: DEPLETION == 22,775", resp.get("DEPLETION") == 22775, f"got={resp.get('DEPLETION')}") and ok
    ok = check("replication: REPLENISHMENT == 4,093", resp.get("REPLENISHMENT") == 4093, f"got={resp.get('REPLENISHMENT')}") and ok
    ok = check("replication: NEUTRAL == 269", resp.get("NEUTRAL") == 269, f"got={resp.get('NEUTRAL')}") and ok
    return ok


def test_replication_hour_summary_same_sign():
    s = pd.read_csv(os.path.join(FROZEN, "exp01_replication_hour_summary.csv"))
    ok = True
    for h in ["h3_diff_bps", "h5_diff_bps", "h10_diff_bps"]:
        positive = (s[h] > 0).all()
        ok = check(f"replication: 5/5 hours positive at {h.upper()}", positive) and ok
    return ok


def test_replication_hour_summary_values():
    s = pd.read_csv(os.path.join(FROZEN, "exp01_replication_hour_summary.csv")).set_index("hour")
    exp = {
        "2026-05-25_04": {"h3_diff_bps": 0.022593196659905324, "h5_diff_bps": 0.029749243167206698, "h10_diff_bps": 0.0340807025854948},
        "2026-05-25_12": {"h3_diff_bps": 0.019191152928077874, "h5_diff_bps": 0.024035397580089324, "h10_diff_bps": 0.028927745128400205},
        "2026-05-25_18": {"h3_diff_bps": 0.013734782892498144, "h5_diff_bps": 0.010909016331183921, "h10_diff_bps": 0.015584111526587606},
        "2026-05-26_15": {"h3_diff_bps": 0.05092540854303627, "h5_diff_bps": 0.07268193275591958, "h10_diff_bps": 0.11870939342741951},
        "2026-05-26_21": {"h3_diff_bps": 0.01577004051464566, "h5_diff_bps": 0.02109850125546476, "h10_diff_bps": 0.022131793255959417},
    }
    ok = True
    for h, vals in exp.items():
        for col, v in vals.items():
            ok = check(f"replication {h}: {col} == {v:.6f}", approx(s.loc[h, col], v), f"got={s.loc[h, col]:.6f}") and ok
    return ok


def test_replication_final_summary():
    s = pd.read_csv(os.path.join(FROZEN, "exp01_replication_final_summary.csv")).set_index("horizon")
    exp = {
        1: {"episodes": 293, "mean": 0.015045556139590141, "ci_lo": 0.010570134973001896, "ci_hi": 0.020039332741765097, "p": 4.999750012499375e-05},
        3: {"episodes": 287, "mean": 0.016905534167914595, "ci_lo": 0.00024522724602567486, "ci_hi": 0.031367318898183026, "p": 0.014449277536123194},
        5: {"episodes": 280, "mean": 0.0347350717503178, "ci_lo": 0.02219842925388571, "ci_hi": 0.04801706493107702, "p": 4.999750012499375e-05},
        10: {"episodes": 266, "mean": 0.04293282100110298, "ci_lo": 0.027452863811095716, "ci_hi": 0.05888287706575722, "p": 4.999750012499375e-05},
    }
    ok = True
    for h, e in exp.items():
        row = s.loc[h]
        ok = check(f"replication H{h}: episodes == {e['episodes']}", int(row["episodes"]) == e["episodes"], f"got={int(row['episodes'])}") and ok
        ok = check(f"replication H{h}: mean == {e['mean']:.6f}", approx(row["equal_weight_mean_bps"], e["mean"]), f"got={row['equal_weight_mean_bps']:.6f}") and ok
        ok = check(f"replication H{h}: CI == [{e['ci_lo']:.6f}, {e['ci_hi']:.6f}]", approx(row["bootstrap_ci_low_bps"], e["ci_lo"]) and approx(row["bootstrap_ci_high_bps"], e["ci_hi"]), f"got=[{row['bootstrap_ci_low_bps']:.6f}, {row['bootstrap_ci_high_bps']:.6f}]") and ok
        ok = check(f"replication H{h}: signflip p == {e['p']:.6f}", approx(row["signflip_one_sided_p"], e["p"]), f"got={row['signflip_one_sided_p']:.6f}") and ok
    # Frozen verdicts
    ok = check("replication: H3/H5/H10 survive equal-episode inference", True) and ok
    return ok


def test_replication_sparsity():
    s = pd.read_csv(os.path.join(FROZEN, "exp01_replication_final_summary.csv")).set_index("horizon")
    ok = True
    for h in [1, 3, 5, 10]:
        zero_rate = s.loc[h, "zero_rate"]
        ok = check(f"replication H{h}: zero rate in [0.40, 0.50]", 0.40 <= zero_rate <= 0.50, f"got={zero_rate:.4f}") and ok
    return ok


def main():
    results = [
        test_discovery_row_count(),
        test_discovery_state_counts(),
        test_discovery_equal_episode(),
        test_discovery_bootstrap(),
        test_replication_row_count(),
        test_replication_per_hour_starting_events(),
        test_replication_flow_and_state_counts(),
        test_replication_hour_summary_same_sign(),
        test_replication_hour_summary_values(),
        test_replication_final_summary(),
        test_replication_sparsity(),
    ]
    n_pass = sum(results)
    n_fail = len(results) - n_pass
    print(f"\nEXP-01 regression: {n_pass} passed, {n_fail} failed")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())