import random, sys, timeit
from itertools import combinations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cribbage as C

# --- 1. hand-checked cases -------------------------------------------------
cases = [
    ((["5H","5S","5D","JC"], "5C"), 29),
    ((["5H","5S","5D","JH"], "5C"), 28),
    ((["AH","2H","3H","4H"], "5H"), 12),
    ((["AS","2H","3C","5D"], "4S"), 7),
    ((["10H","JH","QH","KH"], "AH"), 10),
    ((["4H","5S","5D","6C"], "4S"), 24),
    ((["6C","7D","8H","8S"], "9C"), 16),
    ((["AC","3D","7H","9S"], "KC"), 0),
    ((["JD","4S","5H","6C"], "JC"), 11),
]
for (hand, starter), expected in cases:
    got = C.eval_cribbage_hand(hand, starter)
    assert got == expected, (hand, starter, got, expected)
print(f"{len(cases)} hand-checked cases OK")

# --- 2. table vs. direct computation, random hands -------------------------
def direct(cards, starter, is_crib=False):
    s = C._base_score([r for r,_ in cards] + [starter[0]])
    suits = {su for _,su in cards}
    if len(suits) == 1:
        if starter[1] in suits: s += 5
        elif not is_crib: s += 4
    if any(r == C._JACK and su == starter[1] for r,su in cards): s += 1
    return s

random.seed(7)
for _ in range(200000):
    five = random.sample(C._DECK, 5)
    for crib in (False, True):
        assert C._score(five[:4], five[4], crib) == direct(five[:4], five[4], crib)
print("200,000 random hands: table matches direct computation (hand + crib rules)")

# crib flush rule
assert C._score([C._parse_card(c) for c in ["2H","5H","9H","KH"]], C._parse_card("7S"), is_crib=True) == 2
assert C._score([C._parse_card(c) for c in ["2H","5H","9H","KH"]], C._parse_card("7S")) == 6
print("crib flush rule OK (4-card flush scores in hand, not in crib)")

# --- 3. speed ---------------------------------------------------------------
t = timeit.timeit(lambda: C.eval_cribbage_hand(["5H","5S","5D","JC"], "5C"), number=100000)/100000
print(f"\neval_cribbage_hand: {t*1e6:.2f} us")
t_int = timeit.timeit(lambda: C._score(C._DECK[:4], C._DECK[9]), number=200000)/200000
print(f"_score (pre-parsed): {t_int*1e6:.2f} us")
t_build = timeit.timeit(C._build_base_table, number=3)/3
print(f"table build at import: {t_build*1e3:.0f} ms, {len(C._BASE_TABLE):,} entries")

deal = ["5H","5S","6D","JC","7S","QH"]
t_hand = timeit.timeit(lambda: C.evaluate_discards(deal), number=50)/50
print(f"evaluate_discards (hand EV only): {t_hand*1e3:.1f} ms")
t_crib = timeit.timeit(lambda: C.evaluate_discards(deal, include_crib=True), number=1)
print(f"evaluate_discards (with crib EV): {t_crib:.1f} s")

import math
total = math.comb(52,6)
print(f"\nfull sweep of {total:,} deals, hand EV only, 1 core: {total*t_hand/3600:.1f} h")
