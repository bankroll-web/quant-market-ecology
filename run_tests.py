"""
Run the full regression suite for the quant-market-ecology project.

Usage:
    python run_tests.py

Exit code 0 = all suites pass. Any failure exits 1.
"""
import subprocess
import sys
from pathlib import Path

TESTS = [
    "test_d06_reconstruction.py",
    "test_d09_intervals.py",
    "test_d09b_touch.py",
    "test_exp01_regression.py",
    "test_refactored_d06.py",
]


def main():
    root = Path(__file__).parent
    failures = []
    for t in TESTS:
        print(f"\n{'=' * 70}\nRUNNING {t}\n{'=' * 70}")
        r = subprocess.run([sys.executable, str(root / "tests" / t)], cwd=root)
        if r.returncode != 0:
            failures.append(t)
    print(f"\n{'=' * 70}")
    if failures:
        print(f"FAILED SUITES: {failures}")
        return 1
    print("ALL REGRESSION SUITES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())