"""Full crib sweep priced against a policy opponent, for both roles.

With a uniform opponent the crib EV did not depend on who owned the crib, so one
evaluation per deal answered for both. A policy opponent throws differently as
pone than as dealer, so each role now needs its own evaluation.
"""
import sys, time
from multiprocessing import Pool

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cribbage as C

OUT = 'crib_sweep_policy.psv'

# When I deal, the opponent is the pone starving my crib; when they deal, they
# are the dealer feeding their own.
INTO_MY_CRIB = C._opponent_weights('policy', True)
INTO_THEIR_CRIB = C._opponent_weights('policy', False)


def row(job):
    deal, multiplicity = job
    dealer = C._evaluate_canonical(deal, True, True, INTO_MY_CRIB)[0]
    pone = C._evaluate_canonical(deal, False, True, INTO_THEIR_CRIB)[0]
    cards = lambda group: ' '.join(C.format_card(c) for c in group)
    line = '|'.join([
        cards(deal), str(multiplicity),
        cards(dealer.keep), cards(dealer.discard),
        f'{dealer.hand_ev:.4f}', f'{dealer.crib_ev:.4f}', f'{dealer.total_ev:.4f}',
        cards(pone.keep), cards(pone.discard),
        f'{pone.hand_ev:.4f}', f'{pone.crib_ev:.4f}', f'{pone.total_ev:.4f}',
    ]) + '\n'
    stats = (multiplicity, dealer.hand_ev, dealer.crib_ev, dealer.total_ev,
             pone.hand_ev, pone.crib_ev, pone.total_ev)
    return line, stats


if __name__ == '__main__':
    t0 = time.time()
    deals = list(C.canonical_deals())
    print(f'enumerated {len(deals):,} canonical deals in {time.time() - t0:.0f}s', flush=True)

    total = len(deals)
    step = max(1, total // 20)
    weight = 0
    sums = [0.0] * 6
    t0 = time.time()

    with open(OUT, 'w') as out, Pool() as pool:
        out.write('deal|multiplicity|d_keep|d_toss|d_hand_ev|d_crib_ev|d_total'
                  '|p_keep|p_toss|p_hand_ev|p_crib_ev|p_total\n')
        for i, (line, stats) in enumerate(pool.imap_unordered(row, deals, chunksize=4), 1):
            out.write(line)
            multiplicity = stats[0]
            weight += multiplicity
            for k, value in enumerate(stats[1:]):
                sums[k] += multiplicity * value
            if i % step == 0:
                out.flush()
                elapsed = time.time() - t0
                print(f'progress {i / total:5.0%}  {i:,}/{total:,}  '
                      f'elapsed {elapsed / 60:.0f}m  eta {elapsed / i * (total - i) / 60:.0f}m',
                      flush=True)

    labels = ['dealer hand EV', 'dealer crib EV', 'dealer total EV',
              'pone hand EV', 'pone crib EV', 'pone total EV']
    print(f'\ndone: {total:,} deals in {(time.time() - t0) / 60:.1f} min -> {OUT}')
    print(f'weighted over all {weight:,} possible deals, playing the best discard:')
    for label, value in zip(labels, sums):
        print(f'  {label:<18} {value / weight:6.3f}')
