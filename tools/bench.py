"""Same-workload benchmark for CPython vs PyPy. Warms up, then takes the best run."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cribbage as C

DEAL = ['5H', '5S', '6D', 'JC', '7S', 'QH']
PARSED = [C._parse_card(c) for c in DEAL]
CANON = C._canonicalize(PARSED)[0]


def best_of(fn, runs, warmup):
    for _ in range(warmup):
        fn()
    times = []
    for _ in range(runs):
        t0 = time.time()
        fn()
        times.append(time.time() - t0)
    return min(times)


print(f"{platform.python_implementation()} {platform.python_version()}")

t0 = time.time()
C._build_base_table()
print(f"  build rank table:      {(time.time() - t0) * 1e3:7.1f} ms")

five = C._DECK[:4], C._DECK[9]
score_loop = lambda: [C._score(five[0], five[1]) for _ in range(10000)]
print(f"  _score:                {best_of(score_loop, 20, 20) / 10000 * 1e6:7.3f} us")

hand_ev = lambda: (C._evaluate_canonical_cached.cache_clear(), C.evaluate_discards(DEAL))
print(f"  evaluate_discards:     {best_of(hand_ev, 20, 20) * 1e3:7.2f} ms   (hand EV, 690 scorings)")

crib = lambda: C._evaluate_canonical(CANON, True, True)
t_crib = best_of(crib, 3, 1)
print(f"  + crib EV:             {t_crib:7.2f} s    (683,100 scorings)")

deals = 962988
print(f"  => crib sweep, 32 cores, at the 17.4x scaling we measured: "
      f"{deals * t_crib / 17.4 / 3600:.2f} h")
