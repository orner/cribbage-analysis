# cribbage in C

A straight C port of `cribbage.py` from the parent directory: hand scoring,
discard expected values, suit canonicalisation, and a full-space sweep. No
dependencies beyond libc and pthreads.

The point of this version is to be readable. It uses the same algorithms as the
Python and keeps the comments that explain *why* they look like that, so the two
can be read side by side.

## Build and run

```sh
make            # crib, crib_test, crib_sweep
make test       # the C correctness suite
make difftest   # check this C against cribbage.py (needs python3)
```

```sh
./crib score 5H 5S 5D JC 5C          # 29
./crib hand  5H 5S 5D JC 2H 9D       # rank the 15 discards, hand EV only
./crib crib  5H 5S 5D JC 2H 9D       # ... with crib EV too
./crib crib  5H 5S 5D JC 2H 9D pone  # crib counts against you
./crib crib  5H 5S 5D JC 2H 9D policy  # priced against a thinking opponent

./crib_sweep hand 32                 # every deal, hand EV     (~1 s on 32 cores)
./crib_sweep crib 32                 # every deal, with crib EV (much longer)
./crib_sweep crib 32 policy          # ... against the policy opponent
```

Cards are `5H`, `10S` or `TS`, `AD`. Case does not matter.

## Files

| | |
|---|---|
| `cribbage.h` / `cribbage.c` | the library: scoring, EVs, canonicalisation |
| `opponent_model_data.c` | generated tables — what a real opponent throws |
| `tools/gen_opponent_model_c.py` | regenerates that from `../opponent_model.py` |
| `cli.c` | `crib` — score a hand, rank the discards |
| `sweep.c` | `crib_sweep` — enumerate and evaluate every deal, threaded |
| `test_cribbage.c` | correctness suite, including a second independent scorer |
| `tools/difftest.py` | runs the same inputs through C and Python and compares |

## The three ideas that make it fast

**Precompute the rank table.** Fifteens, pairs and runs depend only on ranks,
and a 52-card deck can only produce 6,175 distinct five-card rank multisets.
They all get computed once at startup. Only the flush and his nobs need suits.

**Key the table by adding nibbles.** Each rank owns one nibble of a 64-bit
integer. Adding five cards' values counts how many of each rank are present —
no rank can appear more than four times, so the nibbles never carry — and that
sum identifies the multiset on its own. The hot loop is therefore five array
lookups and four adds, with no sorting and no hashing of a sequence.

**Canonicalise the suits.** Permuting the four suits maps the deck onto itself,
so it cannot change any score, or any expected value computed over the unseen
cards. Keeping one representative per equivalence class collapses the
20,358,520 six-card deals to 962,988 — a 21.1x reduction. This is the largest
win by a wide margin, and it shrinks the problem rather than speeding up the
code.

`crib_sweep` reproduces both of those counts exactly, which is the strongest
single check that the canonicalisation is right.

## Correctness

Three independent legs, in the spirit of the parent project — where every real
bug was caught by differential testing rather than by unit tests over
hand-picked cases:

1. **Nine hand-checked cases**, including the 29 hand.
2. **The table-driven scorer against a second, deliberately naive scorer** in
   `test_cribbage.c` that computes fifteens, pairs and runs directly, over
   200,000 random hands under both the hand and the crib flush rule, plus a
   suit-relabelling invariance check over 20,000 more.
3. **This C against `cribbage.py`**, via `tools/difftest.py`: random hands
   scored both ways, and random deals run through the full discard evaluation —
   with and without crib EV, for both dealer and pone, and under all three
   opponent models.

All three pass. Note that four of the expected values in leg 1 were wrong when
first written and the code was right; the Python was the tiebreaker.

## Measured against the Python

Same machine, 32 cores.

| | Python | this C |
|---|---|---|
| one scoring | 52 ns (PyPy), 177 ns (CPython) | **~2.6 ns** |
| one deal, crib EV | ~70 ms (CPython) | ~1.8 ms |
| enumerate canonical deals | ~1 min (serial) | 0.5 s |
| full hand-EV sweep | 1.0 min (32 cores) | 0.9 s (32 threads) |
| full crib sweep, both roles | 23.9 min, policy (32 cores) | ~3 min, policy or uniform (32 threads) |

The per-scoring figure subtracts a measured process-startup baseline, best of
three at 100 iterations; the sweep rows are plain wall clock. Treat it as rough
-- an earlier single cold run put it at 1.83 ns, which was optimistic because
the baseline being subtracted was itself measured cold.

`../NOTES.md` estimated 3-5 ns per scoring for a C core before one existed,
which turned out to be about right, if slightly pessimistic.

On an older machine -- a Ryzen 9 3900X against this 9950X3D -- the same binary
scores in about 4.8 ns and runs the threaded hand sweep in 1.9 s against 0.9 s.
Roughly 1.8x per core, and only 2.1x overall despite a third fewer threads,
because enumeration is serial and by then dominates the wall clock.

## The opponent model

The crib can be priced three ways, matching the Python:

| | |
|---|---|
| uniform (default) | the opponent's two cards are a random draw from the unseen |
| `policy` | an opponent who weighs the crib — starves yours, feeds their own |
| `naive` | an opponent who keeps their best hand and ignores the crib |

```sh
./crib crib 5S 5H 5D JC 2S 9S            # uniform
./crib crib 5S 5H 5D JC 2S 9S policy     # against a thinking opponent
./crib crib 5S 5H 5D JC 2S 9S pone naive # their crib, naive opponent
./crib_sweep crib 32 policy              # the whole space, policy priced
```

`opponent_model_data.c` is **generated** from `../opponent_model.py` by
`tools/gen_opponent_model_c.py`. The Python remains the source of truth: after
regenerating the model there, re-run that script rather than editing the C data
by hand.

A class's probability is split across the throws it has in a full deck, so a
class you have partly blocked — because you hold cards it needs — keeps only the
share that survives. Dividing by availability instead would keep a blocked class
at full weight, which is wrong, and is one of the three bugs `../NOTES.md`
warns against reintroducing.

## What is not ported

**Pegging.** Untouched here, as in the Python. It is where the rest of the game
lives.
