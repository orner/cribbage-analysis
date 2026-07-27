import random, sys, timeit, math
from itertools import combinations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cribbage as C

# --- scoring unchanged ------------------------------------------------------
cases = [((["5H","5S","5D","JC"],"5C"),29), ((["5H","5S","5D","JH"],"5C"),28),
         ((["AH","2H","3H","4H"],"5H"),12), ((["AS","2H","3C","5D"],"4S"),7),
         ((["10H","JH","QH","KH"],"AH"),10), ((["4H","5S","5D","6C"],"4S"),24),
         ((["6C","7D","8H","8S"],"9C"),16), ((["AC","3D","7H","9S"],"KC"),0),
         ((["JD","4S","5H","6C"],"JC"),11)]
for (h,s),e in cases: assert C.eval_cribbage_hand(h,s)==e, (h,s,e)
print("scoring: 9 hand-checked cases still OK")

# --- reference discard evaluator, no canonicalization ------------------------
def reference(hand, is_dealer=True, include_crib=False):
    cards=[C._parse_card(c) for c in hand]; dealt=set(cards)
    unseen=[c for c in C._DECK if c not in dealt]; out=[]
    for kept in combinations(range(6),4):
        keep=[cards[i] for i in kept]; toss=[cards[i] for i in range(6) if i not in kept]
        h=sum(C._score(keep,st) for st in unseen)/len(unseen)
        cr=C._crib_ev(toss,unseen) if include_crib else 0.0
        out.append((frozenset(keep), round(h,9), round(cr,9), round(h+(cr if is_dealer else -cr),9)))
    return sorted(out, key=lambda r:-r[3])

random.seed(11)
deals=[random.sample(C._DECK,6) for _ in range(300)]
for deal in deals:
    for dealer in (True, False):
        got=C.evaluate_discards(deal, is_dealer=dealer)
        assert [ (frozenset(r.keep), round(r.hand_ev,9), round(r.crib_ev,9), round(r.total_ev,9)) for r in got ] \
               == reference(deal, is_dealer=dealer), deal
        # keep/discard must partition the input deal, in input order
        for r in got:
            assert set(r.keep)|set(r.discard)==set(deal) and len(r.keep)==4 and len(r.discard)==2
            assert list(r.keep)==[c for c in deal if c in r.keep]
print("300 random deals x dealer/pone: canonical evaluator == reference, cards mapped back correctly")

# with crib EV (slow: 0.5 s per deal)
for deal in deals[:2]:
    got=C.evaluate_discards(deal, include_crib=True)
    assert [ (frozenset(r.keep), round(r.hand_ev,9), round(r.crib_ev,9), round(r.total_ev,9)) for r in got ] \
           == reference(deal, include_crib=True)
print("2 random deals with crib EV: canonical evaluator == reference")

# --- invariance under suit permutation --------------------------------------
for deal in deals[:100]:
    perm=dict(zip("SHDC", random.sample("SHDC",4)))
    permuted=[(r,perm[s]) for r,s in deal]
    a=[round(r.total_ev,9) for r in C.evaluate_discards(deal)]
    b=[round(r.total_ev,9) for r in C.evaluate_discards(permuted)]
    assert a==b, deal
    assert C.canonical_deal(deal)[0]==C.canonical_deal(permuted)[0]
print("100 deals: relabeling suits changes neither the canonical form nor any EV")

# --- canonical key agrees with the parsed-card canonicalizer ----------------
for _ in range(20000):
    idx=sorted(random.sample(range(52),6))
    key=C._canonical_key(idx)
    assert tuple(sorted(C._DECK[i] for i in key))==C._canonicalize([C._DECK[i] for i in idx])[0]
print("20,000 deals: _canonical_key agrees with _canonicalize")

# --- speed ------------------------------------------------------------------
t=timeit.timeit(lambda: C._canonical_key((0,1,2,20,33,47)), number=200000)/200000
print(f"\n_canonical_key: {t*1e6:.2f} us  ->  all {math.comb(52,6):,} deals in {math.comb(52,6)*t/60:.1f} min")
C._evaluate_canonical_cached.cache_clear()
d=[C._parse_card(c) for c in ["5H","5S","6D","JC","7S","QH"]]
t_cold=timeit.timeit(lambda: (C._evaluate_canonical_cached.cache_clear(), C.evaluate_discards(["5H","5S","6D","JC","7S","QH"])), number=50)/50
t_warm=timeit.timeit(lambda: C.evaluate_discards(["5H","5S","6D","JC","7S","QH"]), number=2000)/2000
print(f"evaluate_discards cold: {t_cold*1e3:.2f} ms   cached: {t_warm*1e6:.1f} us")
