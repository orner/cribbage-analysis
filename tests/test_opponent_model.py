import sys, random, time
from collections import Counter
from itertools import combinations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cribbage as C

random.seed(77)

# 1. The weighted path must reproduce the uniform path exactly when the weights
#    ARE uniform -- i.e. proportional to how many concrete throws each class has
#    available. This validates every branch of _crib_ev_modeled (keys, flush,
#    nobs, starter exclusion) against the implementation already trusted.
for _ in range(8):
    deal = random.sample(C._DECK, 6)
    unseen = [c for c in C._DECK if c not in set(deal)]
    uniform = {cls: size / 1326 for cls, size in C._CLASS_SIZE.items()}
    for toss in [deal[:2], deal[2:4], deal[4:]]:
        plain = C._crib_ev(toss, unseen)
        weighted = C._crib_ev_modeled(toss, unseen, uniform)
        assert abs(plain - weighted) < 1e-9, (toss, plain, weighted)
print("true uniform distribution reproduces the uniform crib EV exactly (24 tosses)")

# 2. A degenerate model: opponent always throws exactly one known class.
deal = [C._parse_card(c) for c in ["2S", "3H", "7D", "9C", "JS", "KH"]]
unseen = [c for c in C._DECK if c not in set(deal)]
only_five_five = {(5, 5, False): 1.0}
forced = C._crib_ev_modeled(deal[:2], unseen, only_five_five)
# check it by hand: average over starters of the crib 2S 3H + two fives
by_hand, n = 0.0, 0
for a, b in combinations([c for c in unseen if c[0] == 5], 2):
    for starter in unseen:
        if starter in (a, b):
            continue
        by_hand += C._score(deal[:2] + [a, b], starter, is_crib=True)
        n += 1
assert abs(forced - by_hand / n) < 1e-9, (forced, by_hand / n)
print(f"single-class model priced by hand: {forced:.4f} == {by_hand / n:.4f}")

# 3. Suit relabeling must not disturb a modeled evaluation either.
for _ in range(20):
    deal = random.sample(C._DECK, 6)
    perm = dict(zip("SHDC", random.sample("SHDC", 4)))
    permuted = [(r, perm[s]) for r, s in deal]
    for is_dealer in (True, False):
        a = [round(r.total_ev, 9) for r in
             C.evaluate_discards(deal, is_dealer, True, "policy")]
        b = [round(r.total_ev, 9) for r in
             C.evaluate_discards(permuted, is_dealer, True, "policy")]
        assert a == b, deal
print("20 deals x dealer/pone: modeled EVs survive suit relabeling")

# 4. The cache must not confuse models with each other.
deal = random.sample(C._DECK, 6)
runs = {name: C.evaluate_discards(deal, True, True, name)[0].crib_ev
        for name in (None, "policy", "naive")}
again = {name: C.evaluate_discards(deal, True, True, name)[0].crib_ev
         for name in (None, "policy", "naive")}
assert runs == again and len(set(runs.values())) == 3, runs
print(f"cache keeps models separate: uniform {runs[None]:.3f}, "
      f"policy {runs['policy']:.3f}, naive {runs['naive']:.3f}")

# 5. Does the library model reproduce the Monte Carlo simulation's bias?
print("\nbias vs the uniform model, over 150 random deals:")
for label, is_dealer, expected in [("my crib   (I deal)", True, -0.61),
                                   ("their crib (they deal)", False, +0.39)]:
    for model in ("policy", "naive"):
        deltas = []
        for _ in range(150):
            deal = random.sample(C._DECK, 6)
            plain = C.evaluate_discards(deal, is_dealer, True)
            modeled = C.evaluate_discards(deal, is_dealer, True, model)
            by_toss = {tuple(sorted(r.discard)): r.crib_ev for r in plain}
            deltas += [r.crib_ev - by_toss[tuple(sorted(r.discard))] for r in modeled]
        note = f"   (simulation said {expected:+.2f})" if model == "policy" else ""
        print(f"  {label:<24} {model:<7} {sum(deltas) / len(deltas):+.2f} points{note}")

t0 = time.time()
C.evaluate_discards(random.sample(C._DECK, 6), True, True, "policy")
t_model = time.time() - t0
t0 = time.time()
C.evaluate_discards(random.sample(C._DECK, 6), True, True)
print(f"\ncost per deal: uniform {time.time() - t0:.3f}s, modeled {t_model:.3f}s")
