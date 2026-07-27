"""Honest _score timing: vary the arguments so no JIT can hoist the call."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cribbage as C

random.seed(1)
HANDS = [(random.sample(C._DECK, 4), random.choice(C._DECK)) for _ in range(1000)]
HANDS = [(h, s) for h, s in HANDS if s not in h]

def loop():
    total = 0
    for hand, starter in HANDS:
        total += C._score(hand, starter)
    return total

for _ in range(50):
    loop()
best = min((lambda: (lambda t0: (loop(), time.time() - t0)[1])(time.time()))() for _ in range(50))
print(f"{platform.python_implementation()}: _score over 1000 distinct hands "
      f"-> {best / len(HANDS) * 1e9:.1f} ns/call")
