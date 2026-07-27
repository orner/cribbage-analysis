"""Analyse the policy sweep, and compare it against the uniform run where they overlap.

The uniform sweep was stopped early, but the deals it did finish are a random
sample of the space (imap_unordered), so joining on the deal gives an unbiased
comparison of what modelling the opponent changes.
"""
import sys
from collections import Counter

BASE = ''


def load(path):
    rows = {}
    with open(path) as handle:
        header = next(handle).rstrip('\n').split('|')
        for line in handle:
            parts = line.rstrip('\n').split('|')
            if len(parts) != len(header):
                continue                      # truncated final line of a killed run
            row = dict(zip(header, parts))
            rows[row['deal']] = row
    return rows


policy = load(BASE + 'crib_sweep_policy.psv')
print(f'policy sweep: {len(policy):,} deals')

weight = sum(int(r['multiplicity']) for r in policy.values())
print(f'covering {weight:,} of the 20,358,520 possible deals\n')


def weighted_mean(rows, field):
    total = sum(int(r['multiplicity']) * float(r[field]) for r in rows)
    return total / sum(int(r['multiplicity']) for r in rows)


rows = list(policy.values())
print('playing the best discard, averaged over every possible deal:')
for role, label in [('d', 'as dealer'), ('p', 'as pone ')]:
    print(f'  {label}  hand {weighted_mean(rows, role + "_hand_ev"):6.3f}   '
          f'crib {weighted_mean(rows, role + "_crib_ev"):6.3f}   '
          f'total {weighted_mean(rows, role + "_total"):6.3f}')

print('\nhow often the two roles keep different cards: ', end='')
differ = sum(int(r['multiplicity']) for r in rows if r['d_keep'] != r['p_keep'])
print(f'{differ / weight:.1%} of deals')

print('\nmost common throws into your own crib (as dealer):')
tosses = Counter()
for r in rows:
    ranks = tuple(sorted(card[:-1] for card in r['d_toss'].split()))
    tosses[ranks] += int(r['multiplicity'])
for toss, n in tosses.most_common(8):
    print(f'  {" ".join(toss):<8} {n / weight:5.2%}')

try:
    uniform = load(BASE + 'crib_sweep.psv')
except FileNotFoundError:
    sys.exit(0)

shared = set(uniform) & set(policy)
if not shared:
    sys.exit(0)

print(f'\ncompared with the uniform-opponent run, on {len(shared):,} shared deals:')
for role, label in [('d', 'dealer'), ('p', 'pone  ')]:
    same = sum(1 for deal in shared if uniform[deal][role + '_keep'] == policy[deal][role + '_keep'])
    crib_shift = sum(float(policy[deal][role + '_crib_ev']) - float(uniform[deal][role + '_crib_ev'])
                     for deal in shared) / len(shared)
    print(f'  {label}: same keep in {same / len(shared):6.2%} of deals, '
          f'crib EV shift {crib_shift:+.3f}')
