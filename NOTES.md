# Project notes

Cribbage hand scoring and discard analysis. Pure Python, no dependencies.
Paused 2026-07-27 in a working, fully tested state.

## Layout

```
cribbage.py         the library -- scoring, discard EV, canonicalisation, sweeps
opponent_model.py   generated data: what a policy opponent actually throws
opponent_model_v1.py  the previous iteration, kept for diffing
tests/              correctness suite (plain scripts, no framework; run them directly)
tools/              generators, sweep drivers, benchmarks, the opponent experiment
c/                  a standalone C port -- library, CLI, threaded sweep, tests
```

## API

```python
eval_cribbage_hand(hand, starter)                  # score 4 cards + starter
evaluate_discards(hand, is_dealer=True,            # rank all 15 discards, best first
                  include_crib=False, opponent=None)
best_discard(hand, ...)                            # just the top one
sweep(is_dealer=True, include_crib=False,          # every suit-distinct deal, parallel
      opponent=None, processes=None)
canonical_deal(hand) / canonical_deals()           # suit-canonical forms
format_card(card)
```

Cards are `"5H"`, `"10S"`/`"TS"`, `"AD"` (case-insensitive), or the parsed
`(rank, suit)` form with rank 1..13. Both are accepted everywhere; output
mirrors whatever you passed in.

`opponent` is `None` (uniform draw -- the default, and the right choice for
*choosing* a discard), `"policy"`, `"naive"`, or your own `{class: probability}`
dict. See ANALYSIS.md for what the models change.

## Running things

```bash
python3 tests/test_scoring.py          # scoring vs direct computation, 200k hands
python3 tests/test_discards.py         # discard evaluator vs a reference implementation
python3 tests/test_crib_ev.py          # rewritten crib loop vs the pre-optimisation one
python3 tests/test_opponent_model.py   # opponent model, incl. uniform-equivalence check

pypy3 tools/sweep_policy.py            # full crib sweep, both roles      (~24 min, 32 cores)
pypy3 tools/sweep_uniform.py           # full crib sweep, uniform opponent (~15 min)
pypy3 tools/analyze_sweep.py           # aggregates from the .psv files in the cwd
pypy3 tools/gen_opponent_model.py policy   # regenerate opponent_model.py  (~70 s)
pypy3 tools/compare_model_iterations.py    # diff it against opponent_model_v1.py
python3 tools/bench_ab.py              # old vs new _score, same harness
```

Sweeps write `crib_sweep*.psv` to the working directory and print progress every
5%. They use `multiprocessing.Pool` -- run them from a `__main__` guard, which
the drivers already do.

**Use `pypy3` for sweeps.** It is 2.7x faster on the current code and ~8x on the
crib loops; `pacman -S pypy3` on this machine. Use `python3` for everything else
-- PyPy is actually *slower* on short paths, where the JIT never warms up.
PyPy is at Python 3.11, so no 3.12+ syntax (nested same-quote f-strings bit me).

## Artifacts

```
crib_sweep_policy.psv   98 MB, 962,988 rows -- the complete policy sweep, both roles
crib_sweep.psv          2.5 MB, 25,619 rows -- a uniform-opponent sweep, stopped early
crib_sweep*.log         the run logs, kept as provenance
```

Both regenerate from `tools/sweep_*.py` (24 min and ~15 min respectively), which
write to the working directory -- so re-running from this folder overwrites them
in place.

Columns: `deal|multiplicity|d_keep|d_toss|d_hand_ev|d_crib_ev|d_total|p_keep|p_toss|p_hand_ev|p_crib_ev|p_total`
(`d_` = as dealer, `p_` = as pone). Multiplicities sum to C(52,6) = 20,358,520;
weight by them to recover a statistic over the whole deck.

## Why the code looks like this

Four things carry all the performance, in the order they were added:

1. **Rank lookup table.** Fifteens, pairs and runs depend only on ranks, and a
   deck can only produce 6,175 five-card rank multisets. Precompute all of them;
   only flush and nobs need suits.
2. **Suit canonicalisation.** Permuting the four suits maps the deck onto
   itself, so it changes no score. That collapses 20,358,520 deals to 962,988 --
   a 21.1x reduction, and the single biggest win in the project.
3. **Packed integer key.** Each rank owns one nibble; adding five cards' values
   counts the ranks without carrying, so the table key needs no sort, no tuple
   and no sequence hash. The suit rules were inlined at the same time -- the set
   comprehension and generator they used to build cost more than the lookup.
4. **PyPy** for long sweeps only.

Three bugs worth not reintroducing:

- `_evaluate_canonical` must stay uncached on the sweep path. A sweep visits
  each canonical deal exactly once, so an LRU cache there is pure memory growth
  in all 32 workers. `_evaluate_canonical_cached` is the one-off entry point.
- `canonical_deals()` yields *sorted* deals so they match what `_canonicalize`
  produces. The packed byte key groups by suit instead -- a different order for
  the same set, which silently splits cache entries if you let it leak out.
- In `_crib_ev_modeled`, a throw class's probability is divided by its size in a
  **full deck**, not by how many instances are still available. Dividing by
  availability keeps a blocked class at full weight, which is wrong: holding
  cards a class needs should cost it mass. This one only showed up as a
  disagreement with the Monte Carlo experiment (-0.50 vs -0.61).

`tests/test_opponent_model.py` catches the last of those: feeding
`_crib_ev_modeled` the true uniform distribution must reproduce `_crib_ev`
exactly, which exercises every branch against an implementation already trusted.

## Closed threads

- **Iterating the opponent model. Converged; do not bother going further.**
  `opponent_model.py` now holds iteration 2, generated by players who
  best-respond to iteration 1 rather than assuming a random opponent
  (`pypy3 tools/gen_opponent_model.py policy`; iteration 1 is kept as
  `opponent_model_v1.py`). The tables moved 0.04-0.05 in total variation, no
  single throw class by more than 0.005, and crib EV by **0.003 points averaged
  over all fifteen discards -- but 0.025 on the one actually played**, because
  your choice is correlated with the classes that moved. Against the ~0.5 points
  iteration 1 gained over uniform, the second step is still 20x smaller and in
  the same direction. `tools/compare_model_iterations.py` reports both numbers;
  quoting only the slate average understates what reaches the table by about
  ten times. Modelling the opponent is worth half a point; modelling their model
  of you is worth about 0.025.

- **The uniform sweep is complete.** Done by the C port rather than by
  `tools/sweep_uniform.py`: dealer 13.301, pone 3.918 over the full space, in
  about 3 minutes on 32 threads. It reproduces 962,988 canonical deals summing
  to C(52,6), and the gap against the policy sweep (0.561 and 0.426) corroborates
  the 0.60/0.39 calibration error measured the other way. See ANALYSIS.md.

- **A C core exists, as a standalone program.** `c/` is a full C11 translation
  -- scoring, both EVs, canonicalisation, the opponent model, and a threaded
  sweep -- checked against this library by `c/tools/difftest.py` on random hands
  and deals under all three opponent models, with zero mismatches. Scoring
  measured at **1.83 ns**, against the 3-5 ns estimated and PyPy's 52 ns. It is
  not bound to the Python API; see the note below.

- **The opponent model is ported.** `c/opponent_model_data.c` is generated from
  `opponent_model.py` by `c/tools/gen_opponent_model_c.py`, so this file stays
  the source of truth -- regenerate the model here, then re-run that script. All
  364 class probabilities round-trip exactly. `crib_sweep crib 32 policy`
  reproduces the policy sweep in about 3 minutes.

## Open threads

- **Bind the C to the Python API**, so `_score` and `_crib_ev` can be backed by
  it without changing callers. The port in `c/` is a separate program, not an
  extension module, so nothing in Python benefits from it yet.
- **Rerun the policy sweep under iteration 2** if the headline figures should
  reflect the current tables. ANALYSIS.md's dealer 12.727 / pone 3.484 were
  computed under iteration 1; the C gives 12.716 / 3.459 under iteration 2. The
  difference is real but small, and both are recorded, so this is tidiness
  rather than a correction.
- **Pegging.** Everything here is hand and crib EV only. The play of the hand is
  untouched, and it is where the rest of the game lives.
