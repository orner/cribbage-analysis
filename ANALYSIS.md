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
a policy opponent. The sweep ran under **iteration 1** of the model; re-running
it under iteration 2 moves the totals by -0.011 and -0.025, so these are stable
to about a fortieth of a point rather than exactly current -- see "The policy
sweep, re-run in C" below:

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

### The same space under uniform pricing

The uniform sweep is complete as well, run by the C port in `c/` (~3 minutes on
32 threads). It reproduces 962,988 canonical deals summing to C(52,6), which is
the check that its canonicalisation agrees with the Python's.

| | hand EV | crib EV | total |
|---|---|---|---|
| as dealer | 8.003 | 5.298 | **13.301** |
| as pone | 8.133 | 4.215 | **3.918** |

Both findings above survive the change of opponent model. The pone's hand is
still worth more than the dealer's, 8.133 against 8.003, and the two roles still
keep different cards in 59.9% of deals against 60.0%.

Set beside the policy figures, uniform pricing overstates your crib by 0.561 and
understates theirs by 0.426. Those sit close to the 0.60 and 0.39 in the next
section, but they are **not the same quantity**: that section reprices identical
discards, while these two sweeps each play their own best discard, so the
chosen keep sometimes differs. Two constructions, two implementations, two
languages, landing a few hundredths apart.

### The policy sweep, re-run in C

The C also carries the opponent model, so the policy sweep can be reproduced
independently. Note that it runs **iteration 2** of the model -- whatever
`opponent_model.py` currently holds -- while the full-space figures at the top
of this file were computed under iteration 1:

| | C, iteration 2 | above, iteration 1 | delta |
|---|---|---|---|
| dealer total | 12.716 | 12.727 | -0.011 |
| pone total | 3.459 | 3.484 | -0.025 |
| dealer crib | 4.728 | 4.737 | -0.009 |
| pone crib | 4.667 | 4.641 | **+0.026** |

Hand EVs agree to 0.003, and the roles still disagree on 59.8% of deals against
60.0%. The crib columns move in the directions a 40-deal Python sample predicts
for the same iteration change (-0.005 and +0.032), so this is the model
iteration talking, not a disagreement between the implementations -- which
`c/tools/difftest.py` checks deal by deal.

That pone-side +0.026 looked at first like it contradicted the +0.003 recorded
under "Iterating the opponent model" below. It does not: the two measure
different discards. That figure averaged the repricing across all fifteen; a
sweep keeps only the one played, and the played discard moves about ten times
further because the choice is correlated with the classes the iteration moved.
`tools/compare_model_iterations.py` now reports both, and its played-discard
numbers (-0.0092 and +0.0252) match this sweep's full-space deltas.

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
- The opponent being modelled originally decided using the *uniform* model.
  Iterating that -- regenerating the tables from players who best-respond to the
  previous ones -- moved crib EV by 0.003 points averaged over all fifteen
  discards, 0.025 on the one actually played, and no throw class by more than
  0.005. The process has converged and the figures above are stable to within
  that. See the "Iterating the opponent model" section below.
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
sweep, so treat those percentages as indicative rather than full-space. The
uniform sweep has since been completed over the whole space -- see "The same
space under uniform pricing" above -- so that comparison no longer has to rest
on the partial one.

## Iterating the opponent model

The tables describe an opponent who is sharp about their own cards. But which
model do *they* use? Iteration 1 assumed a random opponent; iteration 2
best-responds to iteration 1. If that changes little, the process has converged.

It changes almost nothing.

| table | movement between iterations (total variation) |
|---|---|
| `PONE_POLICY` | 0.043 |
| `DEALER_POLICY` | 0.053 |
| `PONE_NAIVE` (control) | 0.0000 |
| `DEALER_NAIVE` (control) | 0.0000 |

| | iter 1 -> 2, all 15 | iter 1 -> 2, discard played | uniform -> iter 2 | same discard |
|---|---|---|---|---|
| your crib | -0.0027 | **-0.0092** | -0.598 | 97.2% |
| their crib | +0.0033 | **+0.0252** | +0.395 | 96.8% |

Two columns, because the answer depends on which discard you ask about. Averaged
across all fifteen the second step is tiny. But you only ever play one of them,
and that one moves three to eight times further: your choice is correlated with
the classes the iteration moved, so the slate average dilutes it. As pone you
pick the throw that starves the dealer's crib, which lands you squarely in the
part of `DEALER_POLICY` that shifted.

The played column is also the only one a sweep can see, since a sweep keeps
`[0]`. The C policy sweep's full-space deltas against the iteration-1 figures
above are -0.009 and +0.026, against -0.0092 and +0.0252 here -- a 400-deal
sample and a 962,988-deal enumeration agreeing to a thousandth.

Even on the played discard the second step is 20x smaller than the first and
points the same way, which is convergence rather than oscillation. The naive controls moving *exactly* zero is
the check that the comparison is wired correctly: naive players ignore the crib,
so no opponent model can reach their decisions, and both runs used the same seed
and therefore the same 50,000 hands. Drift there would have meant a bug.

The largest movers are the near-indifferent cases you would expect -- the pone
shuffling between 10-K, 7-K and 8-K, the dealer nudging toward A-3 and A-4.

**Modelling the opponent is worth about half a point of calibration; modelling
their model of you is worth about 0.025 on the discard you actually play.** Not
nothing -- an earlier version of this file said nothing, on the strength of the
all-fifteen average alone -- but around 5% of what the first step bought, and
still small against the 0.4 to 0.6 the uniform assumption costs. A third
iteration would be wasted compute.


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
