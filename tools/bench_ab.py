"""Old vs new _score on identical varying inputs, same harness."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cribbage as C

OLD_TABLE = {}
for key, score in C._BASE_TABLE.items():   # rebuild the old tuple-keyed table
    ranks = []
    for rank in range(1, 14):
        ranks.extend([rank] * ((key >> (4 * (rank - 1))) & 0xF))
    OLD_TABLE[tuple(ranks)] = score

def old_score(cards, starter, is_crib=False):
    score = OLD_TABLE[tuple(sorted([rank for rank, _ in cards] + [starter[0]]))]
    suits = {suit for _, suit in cards}
    if len(suits) == 1:
        if starter[1] in suits: score += 5
        elif not is_crib: score += 4
    if any(rank == C._JACK and suit == starter[1] for rank, suit in cards):
        score += 1
    return score

random.seed(1)
HANDS = [(h, s) for h, s in ((random.sample(C._DECK, 4), random.choice(C._DECK))
                             for _ in range(1000)) if s not in h]
assert all(old_score(h, s) == C._score(h, s) for h, s in HANDS)

def timeit(fn):
    run = lambda: [fn(h, s) for h, s in HANDS]
    for _ in range(50): run()
    best = 1e9
    for _ in range(50):
        t0 = time.time(); run(); best = min(best, time.time() - t0)
    return best / len(HANDS) * 1e9

old, new = timeit(old_score), timeit(C._score)
print(f"{platform.python_implementation():8}  old {old:6.1f} ns   new {new:6.1f} ns   {old/new:.1f}x")
