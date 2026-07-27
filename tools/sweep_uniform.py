"""Full crib-inclusive sweep: best discard for every suit-distinct 6-card deal.

The crib EV of a discard does not depend on who owns the crib -- only its sign
does -- so one evaluation per deal yields both the dealer's and the pone's best
keep, halving what two separate sweeps would cost.
"""
import sys, time
from multiprocessing import Pool

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cribbage as C

OUT = 'crib_sweep.psv'


def row(job):
    deal, multiplicity = job
    results = C._evaluate_canonical(deal, True, True)
    dealer = max(results, key=lambda r: r.hand_ev + r.crib_ev)
    pone = max(results, key=lambda r: r.hand_ev - r.crib_ev)
    cards = lambda group: ' '.join(C.format_card(c) for c in group)
    return '|'.join([
        cards(deal), str(multiplicity),
        cards(dealer.keep), cards(dealer.discard),
        f'{dealer.hand_ev:.4f}', f'{dealer.crib_ev:.4f}',
        f'{dealer.hand_ev + dealer.crib_ev:.4f}',
        cards(pone.keep), cards(pone.discard),
        f'{pone.hand_ev:.4f}', f'{pone.crib_ev:.4f}',
        f'{pone.hand_ev - pone.crib_ev:.4f}',
    ]) + '\n'


if __name__ == '__main__':
    t0 = time.time()
    deals = list(C.canonical_deals())
    print(f'enumerated {len(deals):,} canonical deals in {time.time() - t0:.0f}s', flush=True)

    total = len(deals)
    step = max(1, total // 20)
    t0 = time.time()
    with open(OUT, 'w') as out, Pool() as pool:
        out.write('deal|multiplicity|d_keep|d_toss|d_hand_ev|d_crib_ev|d_total'
                  '|p_keep|p_toss|p_hand_ev|p_crib_ev|p_total\n')
        for i, line in enumerate(pool.imap_unordered(row, deals, chunksize=4), 1):
            out.write(line)
            if i % step == 0:
                out.flush()
                elapsed = time.time() - t0
                print(f'progress {i / total:5.0%}  {i:,}/{total:,}  '
                      f'elapsed {elapsed / 60:.0f}m  eta {elapsed / i * (total - i) / 60:.0f}m',
                      flush=True)
    print(f'done: {total:,} deals in {(time.time() - t0) / 3600:.2f}h -> {OUT}', flush=True)
