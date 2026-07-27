# cribbage-analysis

Cribbage hand scoring and discard analysis, worked out over the whole game
rather than sampled. Pure Python with no dependencies, plus a standalone C port.

The question is the one that comes up every hand: you have been dealt six cards,
you must throw two away, which two? There are 20,358,520 six-card deals and
fifteen ways to discard from each, and this answers all of them.

## Quick start

```python
>>> import cribbage
>>> cribbage.eval_cribbage_hand(["5H", "5S", "5D", "JC"], "5C")
29

>>> best = cribbage.best_discard(["5H", "5S", "5D", "JC", "2H", "9D"])
>>> [cribbage.format_card(c) for c in best.keep], best.hand_ev
(['5H', '5S', '5D', 'JC'], 16.652...)
```

Cards are `"5H"`, `"10S"` or `"TS"`, `"AD"` — case insensitive. `NOTES.md` has
the full API; `ANALYSIS.md` has what the sweeps found.

## What is here

| | |
|---|---|
| `cribbage.py` | the library — scoring, discard EV, canonicalisation, sweeps |
| `opponent_model.py` | generated data: what a real opponent actually throws |
| `tests/` | correctness suite, plain scripts, run them directly |
| `tools/` | generators, sweep drivers, benchmarks |
| `c/` | a standalone C11 port, checked against the Python |
| `ANALYSIS.md` | the findings |
| `NOTES.md` | API, how to run things, and why the code looks like it does |

## Three findings worth the trouble

**The pone's hand is worth more than the dealer's** — 8.125 against 7.990,
across the whole space. A dealer trades hand value to feed their own crib; a
pone never will, because the crib works against them. A uniform opponent model
cannot express this asymmetry at all.

**Real opponents starve your crib of fives.** A uniform random pair contains a
5 about 16.8% of the time. An actual pone throws one into your crib **1.1%** of
the time — a 15x suppression. Less obviously, dealers do not stuff their own
crib with fives either: they throw one 12.4% of the time, *less often than
chance*, because a 5 is also the best card to keep. What they feed it is pairs
and touching cards.

**Modelling the opponent is worth half a point of calibration and almost
nothing in decisions.** Your crib is worth ~0.6 less than a uniform model
claims and theirs ~0.4 more, both errors running against you. But the same
discard still gets chosen 92–96% of the time, because the bias shifts the whole
slate rather than reordering it. Use the simple model to choose; apply the
correction only when you need a calibrated absolute number.

Going one level further — modelling *their* model of *you* — moves crib EV by
about 0.025 points on the discard you actually play, and a tenth of that
averaged across all fifteen. Small either way against the ~0.5 the first step
bought, so that direction is a dead end — but the two numbers differ by ten
times, and which one you quote depends on whether you are pricing a slate or
playing a card.

## How it got fast enough to be possible

A full sweep started out as an 18.3-hour estimate on one core. Three things
fixed that, in order of size:

1. **Suit canonicalisation.** Permuting the four suits maps the deck onto
   itself, so it cannot change a score. Keeping one representative per
   equivalence class collapses 20,358,520 deals to **962,988** — a 21.1x
   reduction that shrinks the problem rather than speeding up the code.
2. **A precomputed rank table.** Fifteens, pairs and runs depend only on ranks,
   and a deck can produce just 6,175 five-card rank multisets. Only flush and
   nobs need suits.
3. **A packed integer key.** Each rank owns one nibble, so adding five cards'
   values counts the ranks without carrying — the table lookup needs no sort,
   no tuple and no sequence hash.

Scoring went from 4.6 µs to 0.15 µs in Python, and to **1.83 ns** in C.

## Correctness

Everything here rests on differential testing: a fast implementation checked
against a slower one written a different way. That is what caught every real bug
in this project — not unit tests over hand-picked cases, though those exist too,
including the 29 hand.

```sh
python3 tests/test_scoring.py         # table lookup vs direct, 200k hands
python3 tests/test_discards.py        # evaluator vs a reference implementation
python3 tests/test_crib_ev.py         # rewritten crib loop vs the original
python3 tests/test_opponent_model.py  # incl. uniform-equivalence check

cd c && make test && make difftest    # the C, and the C against the Python
```

## The C port

`c/` is a full C11 translation — scoring, both expected values,
canonicalisation, the opponent model, and a threaded full-space sweep. No
dependencies beyond libc and pthreads. It is written to be read next to the
Python, and `c/tools/difftest.py` runs identical inputs through both and
compares them.

```sh
cd c && make
./crib score 5H 5S 5D JC 5C          # 29
./crib crib  5H 5S 5D JC 2H 9D policy
./crib_sweep crib 32 policy          # the whole game
```

## Licence

MIT.
