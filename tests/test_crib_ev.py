import sys, random
from itertools import combinations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cribbage as C

def old_crib_ev(toss, unseen):
    """The pre-rewrite version: builds a 4-card list and calls _score."""
    total = deals = 0
    for i, starter in enumerate(unseen):
        rest = unseen[:i] + unseen[i + 1:]
        for opponent in combinations(rest, 2):
            total += C._score(toss + list(opponent), starter, is_crib=True)
            deals += 1
    return total / deals

random.seed(21)
# ordinary random deals
for n in range(12):
    deal = random.sample(C._DECK, 6)
    toss, keep = deal[:2], deal[2:]
    unseen = [c for c in C._DECK if c not in set(deal)]
    a, b = C._crib_ev(toss, unseen), old_crib_ev(toss, unseen)
    cards = ' '.join(C.format_card(c) for c in toss)
    assert abs(a - b) < 1e-12, (toss, a, b)
print("12 random tosses: rewritten _crib_ev == old implementation exactly")

# suited tosses and jack tosses, where the flush and nobs branches actually fire
tricky = [
    [(5, 'H'), (10, 'H')],                       # suited toss -> flush branch live
    [(_j := C._RANKS['J'], 'S'), (5, 'S')],      # suited toss containing a jack
    [(C._RANKS['J'], 'D'), (C._RANKS['J'], 'C')],# two jacks, different suits
    [(C._RANKS['J'], 'H'), (7, 'S')],            # one jack, unsuited toss
]
for toss in tricky:
    deal = toss + [c for c in C._DECK if c not in set(toss)][:4]
    unseen = [c for c in C._DECK if c not in set(deal)]
    a, b = C._crib_ev(toss, unseen), old_crib_ev(toss, unseen)
    cards = ' '.join(C.format_card(c) for c in toss)
    assert abs(a - b) < 1e-12, (toss, a, b)
    print(f"  {cards:<10} {a:.6f}  == old {b:.6f}")
print("flush/nobs branches match too")

# exhaustive flush check: a crib flush must need all five suited
allH = [C._parse_card(c) for c in ["2H","5H","9H","KH"]]
assert C._score(allH, C._parse_card("7S"), is_crib=True) == 2
assert C._score(allH, C._parse_card("7H"), is_crib=True) == 2 + 5
assert C._score(allH, C._parse_card("7S")) == 2 + 4
print("crib vs hand flush rules still correct after the rewrite")
