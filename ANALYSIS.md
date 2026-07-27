# Analysis

What the sweeps and experiments found. Everything here is measured, not
estimated, unless explicitly marked. Numbers come from `tools/sweep_policy.py`,
`tools/experiment_opponent_bias.py` and `tools/bench_ab.py`.

## The space

| | |
|---|---|
| 6-card deals, C(52,6) | 20,358,520 |
| suit-distinct deals | 962,988 (21.1x fewer) |
| ways to discard from a deal | 15 |
| 5-card rank multisets a deck can produce | 6,175 |
| scorings in one deal's exact crib EV | 683,100 |

Highest-EV deal in the entire space: **four 5s plus A-2**, keeping the four 5s
for a hand EV of 22.78.

## Full-space results

Every possible deal, weighted by multiplicity, playing the best discard against
a policy opponent:

| | hand EV | crib EV | total |
|---|---|---|---|
| as dealer | 7.990 | 4.737 | **12.727** |
| as pone | 8.125 | 4.641 | **3.484** |

Two things stand out.

**The pone's hand is worth more than the dealer's** (8.125 vs 7.990). A dealer
trades hand value to feed their own crib; a pone will not, because the crib
works against them. A uniform opponent model cannot express this asymmetry at
all -- it prices both cribs identically -- so this only appears once the
opponent is modelled.

**The two roles keep different cards in 60.0% of deals.** Same six cards; which
side of the table you are on flips the right answer more often than not.

Most common throws into your own crib as dealer: 7-8 (4.27%), 2-3 (3.34%),
6-8 (2.85%), A-3 (2.69%), 8-9 (2.55%), 6-7 (2.52%). Read this as a *frequency*
ranking, not a quality one -- 5-5 is the strongest throw by value and barely
appears, because you seldom hold two 5s you can spare.

## What opponents actually throw

Sampled from 20,000 hands per policy, each resolved with the evaluator:

| | contains a 5 | is a pair | ranks within 2 |
|---|---|---|---|
| uniform random pair (the default model's assumption) | 16.8% | 5.9% | 33.6% |
| pone -> **your** crib | **1.1%** | 2.8% | 21.9% |
| dealer -> **their own** crib | 12.4% | **14.4%** | **57.8%** |

The starving effect is stark: a pone puts a 5 in your crib 1.1% of the time
against 16.8% for a random pair, a 15x suppression.

The dealer row corrects a natural assumption. Dealers do **not** feed their crib
with 5s -- they throw one only 12.4% of the time, *less often than chance*,
because a 5 is also the best card to keep in hand. What they actually feed it is
pairs (2.4x uniform) and touching cards (1.7x).

## How much the opponent's discard matters

It matters a great deal for **calibration** and almost not at all for
**decisions**.

| | crib EV error | same discard chosen | EV lost by trusting uniform |
|---|---|---|---|
| your crib (you deal) | **-0.60** | 92-93% | ~0.012 pts/deal |
| their crib (they deal) | **+0.39** | 93-96% | ~0.010 pts/deal |
| your crib, naive opponent | -0.25 | 94% | ~0.010 pts/deal |

Both errors run against you: your crib is worth ~0.6 less than a uniform model
says, theirs ~0.4 more. Call it half a point per deal of systematic optimism,
and it scales with opponent skill -- against someone who ignores the crib
entirely, the error halves.

But it barely changes what to *do*. The bias is close to uniform across all 15
discards, so it shifts the whole slate rather than reordering it, and where the
choice does change the alternatives are nearly tied. **Use the uniform model to
choose a discard; apply the correction only when you need calibrated absolute
numbers** -- endgame counting, say.

Your own hand EV is untouched by any of this. What the opponent throws cannot
reach your four cards.

### Methodology and caveats

- The empirical distribution was validated two independent ways: a Monte Carlo
  simulation dealing both hands from one deck (-0.61 / +0.39) and the library's
  class-weighted model (-0.60 / +0.39). They were built separately and agree.
- The opponent being modelled decides using the *uniform* model, since that is
  what generated the tables. This is one refinement step, not a fixed point.
- The EV-lost figures are **upper bounds**. The realistic pricing averages 600
  sampled opponent throws per discard, and picking the argmax under a noisy
  estimate partly chases that noise.
- Crib EV assumes the opponent's two cards are their *only* private information
  in play. Position, pegging and score are all ignored.

### A correction worth recording

An interim report from the policy sweep at 50% gave dealer total 12.480 and pone
3.277. Those were wrong and should be discarded. `imap_unordered` returns
results as they complete, but tasks are *dispatched* in order, so the first half
was the first half of the canonical enumeration -- ordered by low card indices,
and therefore biased toward low-rank deals. The final figures above are exact.
The same bias affects the 25,618-deal comparison against the partial uniform
sweep, so treat those percentages as indicative rather than full-space.

## Performance

The scoring path got about 25x faster; the sweep that framed the whole project
went from impossible to routine.

| | at the start | now |
|---|---|---|
| `eval_cribbage_hand` | 4.6 us | 0.15 us |
| `_score`, A/B on identical inputs | 585 ns | 177 ns (CPython), 52 ns (PyPy) |
| one deal, hand EV | 3.2 ms | 0.14 ms |
| one deal, crib EV | 0.46 s | 0.07 s (CPython), 0.02 s (PyPy) |
| full hand-EV sweep | 18.3 h (1 core) | 1.0 min (32 cores) |
| full crib sweep | ~7.1 h (projected) | 23.9 min (measured, both roles) |

Where it came from, in order of size: suit canonicalisation (21.1x, and it
shrinks the problem rather than speeding up the code), the rank lookup table,
the packed integer key with inlined suit rules (3.3x on CPython, 4.7x on PyPy),
and PyPy itself.

**On PyPy specifically.** It gave 2.7x on the *original* code with no changes at
all -- well short of the 5-15x I expected. The reason is instructive: PyPy's
wins come from removing object overhead, and the old `_score` was dominated by
allocating a sorted tuple and hashing it, which is algorithm, not interpreter
overhead. Rewriting that into integer arithmetic is what let the JIT pay off.
Note also that PyPy is *slower* than CPython on the hand-EV path (0.19 vs
0.14 ms), which is short and never warms up. It only wins on long loops.

Parallel scaling measured 17.4x on 32 cores, not 32x -- the enumeration phase is
serial and the parent pickles and collects ~1M results. Any estimate that
divides by the core count will be optimistic by about that factor; an early
4.2 h projection for the crib sweep was really 7.1 h for exactly this reason.

## Correctness

The results above rest on a suite that is worth keeping:

- 9 hand-checked scoring cases, including the 29-hand.
- 200,000 random hands: table lookup vs direct computation, under both the hand
  and crib flush rules.
- 300 deals x dealer/pone: the canonical evaluator vs a reference implementation
  that skips canonicalisation entirely.
- Suit-relabelling invariance, for both plain and modelled evaluations.
- The rewritten crib loop vs a preserved copy of the pre-optimisation one, on
  random tosses and on hand-picked ones that force the flush and nobs branches.
- The weighted crib EV, fed the true uniform distribution, reproducing the
  uniform implementation exactly.

That last pattern -- differential testing against the slower implementation you
are replacing -- caught every real bug in this project.
