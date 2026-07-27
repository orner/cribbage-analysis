"""How much does the opponent's *choice* of discard change your crib EV?

_crib_ev models the opponent's two crib cards as a uniform draw from the unseen
cards. Real opponents pick: as dealer they feed their own crib, as pone they
starve yours. This measures the resulting error, in points, and asks whether it
would change which discard you make.

Method: build an empirical distribution of what a policy opponent actually
throws (sampling random 6-card hands and running the evaluator on each), then
re-price your own discards against that distribution instead of a uniform one.
"""
import sys, random, time
from multiprocessing import Pool

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cribbage as C

DECK = C._DECK
POOL_HANDS = 20000     # opponent hands sampled to build the toss distribution
MY_HANDS = 800         # my hands evaluated
SAMPLES = 600          # opponent tosses averaged per discard


def opponent_toss(job):
    """What this opponent throws to the crib, under a given policy."""
    hand, is_dealer, strong = job
    best = C.evaluate_discards(hand, is_dealer=is_dealer, include_crib=strong)[0]
    return tuple(best.discard)


def realistic_crib_ev(toss, mine, samples):
    """Average crib score for my toss, over what the opponent actually throws."""
    total = 0.0
    used = 0
    for opp in samples:
        if opp[0] in mine or opp[1] in mine:
            continue
        crib = list(toss) + list(opp)
        excluded = mine | {opp[0], opp[1]}
        subtotal = 0
        starters = 0
        for starter in DECK:
            if starter in excluded:
                continue
            subtotal += C._score(crib, starter, is_crib=True)
            starters += 1
        total += subtotal / starters
        used += 1
    return total / used


def analyze(job):
    """Compare uniform-opponent pricing against the empirical one for one deal."""
    my_hand, is_dealer, samples = job
    mine = frozenset(my_hand)
    priced = C.evaluate_discards(my_hand, is_dealer=is_dealer, include_crib=True)

    rows = []
    for result in priced:
        toss = tuple(result.discard)
        real = realistic_crib_ev(toss, mine, samples)
        sign = 1 if is_dealer else -1
        rows.append({
            'model_crib': result.crib_ev,
            'real_crib': real,
            'model_total': result.hand_ev + sign * result.crib_ev,
            'real_total': result.hand_ev + sign * real,
        })

    by_model = max(rows, key=lambda r: r['model_total'])
    by_real = max(rows, key=lambda r: r['real_total'])
    return {
        'bias': sum(r['real_crib'] - r['model_crib'] for r in rows) / len(rows),
        'chosen_bias': by_model['real_crib'] - by_model['model_crib'],
        'agreed': by_model is by_real,
        'regret': by_real['real_total'] - by_model['real_total'],
    }


def summarize(name, results):
    n = len(results)
    mean = lambda key: sum(r[key] for r in results) / n
    agree = sum(1 for r in results if r['agreed']) / n
    print(f"\n{name}  ({n} deals)")
    print(f"  crib EV error, averaged over all 15 discards : {mean('bias'):+.2f} points")
    print(f"  crib EV error on the discard you would pick  : {mean('chosen_bias'):+.2f} points")
    print(f"  uniform model picks the same discard         : {agree:.1%} of deals")
    print(f"  EV lost by trusting the uniform model        : {mean('regret'):.3f} points/deal")


if __name__ == '__main__':
    random.seed(2718)
    t0 = time.time()
    hands = [random.sample(DECK, 6) for _ in range(POOL_HANDS)]

    with Pool() as pool:
        # What a pone throws into MY crib, and what a dealer throws into THEIRS.
        into_my_crib = pool.map(opponent_toss, [(h, False, True) for h in hands], 16)
        into_their_crib = pool.map(opponent_toss, [(h, True, True) for h in hands], 16)
        # A weaker opponent who ignores the crib entirely, for sensitivity.
        naive_into_my_crib = pool.map(opponent_toss, [(h, False, False) for h in hands], 16)
        print(f"built opponent toss distributions in {time.time() - t0:.0f}s", flush=True)

        def rate(tosses, predicate):
            return sum(1 for t in tosses if predicate(t)) / len(tosses)

        has_five = lambda t: any(r == 5 for r, _ in t)
        is_pair = lambda t: t[0][0] == t[1][0]
        touching = lambda t: abs(t[0][0] - t[1][0]) <= 2
        print("\nwhat gets thrown, vs a uniform random pair (5s in 17%, pairs in 6%):")
        for label, tosses in [("pone -> my crib", into_my_crib),
                              ("dealer -> own crib", into_their_crib),
                              ("naive pone -> my crib", naive_into_my_crib)]:
            print(f"  {label:<22} contains a 5: {rate(tosses, has_five):5.1%}   "
                  f"pair: {rate(tosses, is_pair):5.1%}   ranks within 2: {rate(tosses, touching):5.1%}")

        my_hands = [random.sample(DECK, 6) for _ in range(MY_HANDS)]
        for name, is_dealer, source in [
                ("MY CRIB (I deal; opponent starves it)", True, into_my_crib),
                ("THEIR CRIB (they deal; they feed it)", False, into_their_crib),
                ("MY CRIB vs a naive opponent", True, naive_into_my_crib)]:
            jobs = [(h, is_dealer, random.sample(source, SAMPLES)) for h in my_hands]
            summarize(name, pool.map(analyze, jobs, 4))

    print(f"\ntotal {time.time() - t0:.0f}s")
