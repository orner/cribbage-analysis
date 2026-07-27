#!/usr/bin/env python3
"""Check the C implementation against cribbage.py.

The Python project's own rule is that every real bug it found was caught by
differential testing rather than by unit tests over hand-picked cases. This is
that check applied across the language boundary: random hands and random deals,
scored both ways, compared exactly.

Run from the c/ directory:  python3 tools/difftest.py [trials]
"""

import random
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parent))

import cribbage  # noqa: E402  (needs the path set above)

CRIB = HERE / "crib"
RANKS = "A23456789TJQK"
SUITS = "SHDC"
DECK = [r + s for s in SUITS for r in RANKS]


def run(args):
    result = subprocess.run([str(CRIB)] + args, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"crib failed on {args}:\n{result.stderr}")
    return result.stdout


def check_scoring(trials, rng):
    print(f"scoring: {trials} random hands")
    bad = 0
    for _ in range(trials):
        cards = rng.sample(DECK, 5)
        c_score = int(run(["score"] + cards).strip())
        py_score = cribbage.eval_cribbage_hand(cards[:4], cards[4])
        if c_score != py_score:
            bad += 1
            if bad <= 3:
                print(f"  MISMATCH {cards}: C={c_score} Python={py_score}")
    print(f"  {bad} mismatches")
    return bad


def parse_table(text):
    """Rows of the CLI table as (keep, toss, hand_ev, crib_ev, total_ev)."""
    rows = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 10:
            continue
        keep = tuple(parts[1:5])
        toss = tuple(parts[5:7])
        rows.append((keep, toss, float(parts[7]), float(parts[8]), float(parts[9])))
    return rows


def check_discards(trials, rng, include_crib, is_dealer=True):
    what = "crib EV" if include_crib else "hand EV"
    role = "dealer" if is_dealer else "pone"
    print(f"discards ({what}, {role}): {trials} random deals")
    bad = 0
    for _ in range(trials):
        deal = rng.sample(DECK, 6)
        args = ["crib" if include_crib else "hand"] + deal
        if include_crib and not is_dealer:
            args.append("pone")
        rows = parse_table(run(args))

        expected = cribbage.evaluate_discards(
            deal, is_dealer=is_dealer, include_crib=include_crib
        )
        if len(rows) != len(expected):
            print(f"  MISMATCH {deal}: {len(rows)} rows vs {len(expected)}")
            bad += 1
            continue

        for got, want in zip(rows, expected):
            keep_ok = set(got[0]) == {cribbage.format_card(c) for c in want.keep}
            toss_ok = set(got[1]) == {cribbage.format_card(c) for c in want.discard}
            evs_ok = (
                abs(got[2] - want.hand_ev) < 5e-4
                and abs(got[3] - want.crib_ev) < 5e-4
                and abs(got[4] - want.total_ev) < 5e-4
            )
            if not (keep_ok and toss_ok and evs_ok):
                bad += 1
                if bad <= 3:
                    print(f"  MISMATCH {deal}")
                    print(f"    C      {got}")
                    print(
                        f"    Python {tuple(cribbage.format_card(c) for c in want.keep)}"
                        f" {tuple(cribbage.format_card(c) for c in want.discard)}"
                        f" {want.hand_ev:.4f} {want.crib_ev:.4f} {want.total_ev:.4f}"
                    )
                break
    print(f"  {bad} mismatches")
    return bad


def main():
    if not CRIB.exists():
        raise SystemExit("build first: make")
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    rng = random.Random(20260727)

    bad = 0
    bad += check_scoring(trials * 4, rng)
    bad += check_discards(trials, rng, include_crib=False)
    # Crib EV is ~45,540 scorings per discard, so far fewer deals.
    bad += check_discards(max(3, trials // 100), rng, include_crib=True)
    bad += check_discards(max(3, trials // 100), rng, include_crib=True, is_dealer=False)

    print()
    if bad:
        print(f"FAILED: {bad} mismatches")
        return 1
    print("C and Python agree everywhere checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
