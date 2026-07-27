from collections import Counter, defaultdict, namedtuple
from functools import lru_cache
from itertools import combinations, combinations_with_replacement
from multiprocessing import Pool

# Cards are strings: a rank ("A", "2".."10" or "T", "J", "Q", "K") followed by
# a suit ("S", "H", "D", "C") -- e.g. "5H", "10S", "AD". Case insensitive. The
# parsed form, (rank, suit) with rank 1..13, is accepted everywhere too.
_RANKS = {rank: i + 1 for i, rank in enumerate("A23456789TJQK")}
_SUITS = "SHDC"
_JACK = _RANKS["J"]
_RANK_NAMES = {rank: name for name, rank in _RANKS.items()}
_RANK_NAMES[_RANKS["T"]] = "10"

_DECK = [(rank, suit) for suit in _SUITS for rank in _RANKS.values()]


def _parse_card(card):
    """Return (rank, suit) for a card, where rank is 1 (ace) through 13 (king)."""
    if isinstance(card, tuple):
        if card in _DECK_SET:
            return card
        raise ValueError(f"unrecognized card: {card!r}")
    text = str(card).strip().upper()
    rank, suit = text[:-1], text[-1:]
    if rank == "10":
        rank = "T"
    if rank not in _RANKS or suit not in _SUITS:
        raise ValueError(f"unrecognized card: {card!r}")
    return _RANKS[rank], suit


_DECK_SET = frozenset(_DECK)


def format_card(card) -> str:
    """Render a card as a string, e.g. (10, "S") -> "10S"."""
    rank, suit = _parse_card(card)
    return _RANK_NAMES[rank] + suit


def _base_score(ranks):
    """Fifteens, pairs and runs for five ranks. Suit-independent."""
    score = 0

    # Fifteens: every subset summing to 15, face cards counting ten.
    values = [min(rank, 10) for rank in ranks]
    for size in range(2, len(values) + 1):
        score += 2 * sum(1 for combo in combinations(values, size) if sum(combo) == 15)

    # Pairs: two points per matching pair, which also covers three/four of a kind.
    counts = Counter(ranks)
    score += 2 * sum(count * (count - 1) // 2 for count in counts.values())

    # Runs: each maximal run of three or more distinct ranks scores its length,
    # once per combination of the duplicated ranks in it.
    length, ways = 0, 1
    for rank in range(1, len(_RANKS) + 2):
        count = counts.get(rank, 0)
        if count:
            length += 1
            ways *= count
        else:
            if length >= 3:
                score += length * ways
            length, ways = 0, 1

    return score


# Each rank owns one nibble of an integer, so adding up five cards' values
# counts how many of each rank are present -- no card can appear more than four
# times, so the nibbles never carry. That sum identifies the rank multiset on
# its own, which means the table can be keyed without sorting the ranks first,
# and the key is an int rather than a tuple: no allocation, no hashing a
# sequence, just five list lookups and four adds in the hot loop.
_RANK_BITS = [0] + [1 << (4 * (rank - 1)) for rank in sorted(_RANKS.values())]


def _packed(ranks):
    """The packed key for a group of ranks."""
    key = 0
    for rank in ranks:
        key += _RANK_BITS[rank]
    return key


def _build_base_table():
    """Every 5-card rank multiset a real deck can produce -- 6,175 of them."""
    table = {}
    for ranks in combinations_with_replacement(sorted(_RANKS.values()), 5):
        if max(Counter(ranks).values()) <= 4:
            table[_packed(ranks)] = _base_score(ranks)
    return table


_BASE_TABLE = _build_base_table()


def _score(cards, starter, is_crib=False) -> int:
    """Score four parsed cards against a parsed starter.

    Everything except the flush and his nobs depends only on the ranks, so it
    comes straight out of the precomputed table. The cards are unpacked by hand
    rather than looped over: at hundreds of billions of calls in a full sweep,
    the set and generator this used to build cost more than the lookup itself.
    """
    (rank_a, suit_a), (rank_b, suit_b), (rank_c, suit_c), (rank_d, suit_d) = cards
    starter_rank, starter_suit = starter

    score = _BASE_TABLE[_RANK_BITS[rank_a] + _RANK_BITS[rank_b] + _RANK_BITS[rank_c]
                        + _RANK_BITS[rank_d] + _RANK_BITS[starter_rank]]

    # Flush: four matching suits in hand scores four, five if the starter
    # matches too. A crib only scores the five-card flush.
    if suit_a == suit_b == suit_c == suit_d:
        if suit_a == starter_suit:
            score += 5
        elif not is_crib:
            score += 4

    # His nobs: a jack in hand matching the starter's suit.
    if ((rank_a == _JACK and suit_a == starter_suit)
            or (rank_b == _JACK and suit_b == starter_suit)
            or (rank_c == _JACK and suit_c == starter_suit)
            or (rank_d == _JACK and suit_d == starter_suit)):
        score += 1

    return score


def eval_cribbage_hand(hand, starter_card) -> int:
    """Score a 4-card cribbage hand against the starter card."""
    cards = [_parse_card(card) for card in hand]
    if len(cards) != 4:
        raise ValueError("a cribbage hand is four cards")
    return _score(cards, _parse_card(starter_card))


DiscardEval = namedtuple("DiscardEval", "keep discard hand_ev crib_ev total_ev")


def _toss_class(card_a, card_b):
    """The only properties of a two-card throw that change how a crib scores."""
    (rank_a, suit_a), (rank_b, suit_b) = card_a, card_b
    low, high = (rank_a, rank_b) if rank_a <= rank_b else (rank_b, rank_a)
    return low, high, suit_a == suit_b


# How many concrete two-card throws each class has in a full deck: six for a
# same-rank pair, four suited and twelve unsuited for two different ranks.
_CLASS_SIZE = {}
for _low in sorted(_RANKS.values()):
    for _high in range(_low, len(_RANKS) + 1):
        if _low == _high:
            _CLASS_SIZE[(_low, _high, False)] = 6
        else:
            _CLASS_SIZE[(_low, _high, True)] = 4
            _CLASS_SIZE[(_low, _high, False)] = 12


def _expand(table):
    """Turn a (low, high) -> (unsuited, suited) table into class -> probability."""
    weights = {}
    for (low, high), (unsuited, suited) in table.items():
        weights[(low, high, False)] = unsuited
        if low != high:
            weights[(low, high, True)] = suited
    return weights


try:
    import opponent_model as _opponent_model
except ImportError:                                     # uniform pricing only
    _OPPONENT_MODELS = {}
else:
    # Keyed by (model, am I the dealer): when I deal, the opponent is the pone
    # throwing into my crib; when they deal, they are feeding their own.
    _OPPONENT_MODELS = {
        ("policy", True): _expand(_opponent_model.PONE_POLICY),
        ("policy", False): _expand(_opponent_model.DEALER_POLICY),
        ("naive", True): _expand(_opponent_model.PONE_NAIVE),
        ("naive", False): _expand(_opponent_model.DEALER_NAIVE),
    }


def _opponent_weights(opponent, is_dealer):
    """Resolve an opponent model to the throw distribution facing you this deal."""
    if opponent is None:
        return None
    if isinstance(opponent, dict):
        return opponent
    if not _OPPONENT_MODELS:
        raise ValueError("opponent models need opponent_model.py alongside this module")
    try:
        return _OPPONENT_MODELS[(opponent, is_dealer)]
    except KeyError:
        raise ValueError(f"unknown opponent model: {opponent!r}") from None


def _crib_ev(toss, unseen):
    """Average crib score for a discard, over every starter and opponent throw.

    Assumes the opponent's two cards are drawn uniformly from the unseen ones,
    which is the usual approximation -- a real opponent discards deliberately.

    This is where a sweep spends essentially all of its time -- 45,540 scorings
    per discard -- so the scoring is inlined rather than calling _score: the
    tossed cards' share of the table key is hoisted out, and both suit rules are
    reduced to checks that fail on their first comparison nearly every time.
    """
    (rank_a, suit_a), (rank_b, suit_b) = toss
    toss_key = _RANK_BITS[rank_a] + _RANK_BITS[rank_b]
    toss_suited = suit_a == suit_b
    jack_suits = {suit for rank, suit in toss if rank == _JACK}

    packed = [(_RANK_BITS[rank], rank, suit) for rank, suit in unseen]
    table = _BASE_TABLE
    total = 0

    for i, (starter_key, _, starter_suit) in enumerate(packed):
        rest = packed[:i] + packed[i + 1:]
        base = toss_key + starter_key
        # A crib flush needs all five cards suited, so the two tossed cards and
        # the starter must agree before either opponent card can matter.
        flush_suit = suit_a if toss_suited and suit_a == starter_suit else None
        nobs = 1 if starter_suit in jack_suits else 0

        for (key_c, rank_c, suit_c), (key_d, rank_d, suit_d) in combinations(rest, 2):
            score = table[base + key_c + key_d] + nobs
            if not nobs:
                if (rank_c == _JACK and suit_c == starter_suit) or \
                        (rank_d == _JACK and suit_d == starter_suit):
                    score += 1
            if flush_suit is not None and suit_c == flush_suit and suit_d == flush_suit:
                score += 5
            total += score

    count = len(unseen)
    return total / (count * (count - 1) * (count - 2) // 2)


def _crib_ev_modeled(toss, unseen, weights):
    """Average crib score for a discard, against an opponent who chooses.

    The same enumeration as _crib_ev, except each opponent throw carries the
    probability that this opponent actually makes it. A class's probability is
    split evenly across the throws it has in a full deck, so a class you have
    partly blocked -- because you hold cards it needs -- keeps only the share
    that survives, which is what conditioning on your own hand should do. The
    divisor is then the weight that really accumulated.
    """
    (rank_a, suit_a), (rank_b, suit_b) = toss
    toss_key = _RANK_BITS[rank_a] + _RANK_BITS[rank_b]
    toss_suited = suit_a == suit_b
    jack_suits = {suit for rank, suit in toss if rank == _JACK}

    throws = []
    for (i, card_c), (j, card_d) in combinations(enumerate(unseen), 2):
        throw_class = _toss_class(card_c, card_d)
        weight = weights.get(throw_class, 0.0)
        if weight:
            (rank_c, suit_c), (rank_d, suit_d) = card_c, card_d
            throws.append((weight / _CLASS_SIZE[throw_class], i, j,
                           _RANK_BITS[rank_c] + _RANK_BITS[rank_d],
                           rank_c, suit_c, rank_d, suit_d))

    table = _BASE_TABLE
    total = 0.0
    weight_total = 0.0

    for index, (starter_rank, starter_suit) in enumerate(unseen):
        base = toss_key + _RANK_BITS[starter_rank]
        flush_suit = suit_a if toss_suited and suit_a == starter_suit else None
        nobs = 1 if starter_suit in jack_suits else 0

        for weight, i, j, throw_key, rank_c, suit_c, rank_d, suit_d in throws:
            if i == index or j == index:
                continue
            score = table[base + throw_key] + nobs
            if not nobs:
                if (rank_c == _JACK and suit_c == starter_suit) or \
                        (rank_d == _JACK and suit_d == starter_suit):
                    score += 1
            if flush_suit is not None and suit_c == flush_suit and suit_d == flush_suit:
                score += 5
            total += weight * score
            weight_total += weight

    return total / weight_total


def _canonicalize(cards):
    """Relabel suits into a canonical order, keeping every score unchanged.

    Permuting the four suits maps the deck onto itself, so it leaves fifteens,
    pairs, runs, flushes and nobs alone -- and with them every expected value
    computed over the unseen cards. Grouping the deal by suit and sorting those
    rank groups therefore picks one representative per equivalence class, which
    is what collapses the 20.4M possible deals to roughly a twentieth as many.

    Returns the canonical deal and the map from the caller's suits to canonical
    ones, which is what translates an answer back to the cards actually held.
    """
    groups = defaultdict(list)
    for rank, suit in cards:
        groups[suit].append(rank)
    ordered = sorted((tuple(sorted(ranks)), suit) for suit, ranks in groups.items())
    suit_map = {suit: _SUITS[i] for i, (_, suit) in enumerate(ordered)}
    canonical = tuple(sorted((rank, suit_map[suit]) for rank, suit in cards))
    return canonical, suit_map


def canonical_deal(hand):
    """Canonical form of a 6-card deal, plus the suit map that produced it."""
    return _canonicalize([_parse_card(card) for card in hand])


def _canonical_key(indices):
    """Canonical form of a deal given as deck indices, packed into bytes.

    Same relabeling as _canonicalize, but cheap enough to run on all 20.4M
    deals: indices arrive ascending, so each suit's ranks are already sorted.
    """
    groups = defaultdict(list)
    for index in indices:
        groups[index // len(_RANKS)].append(index % len(_RANKS))
    canonical = []
    for order, (ranks, _) in enumerate(sorted((tuple(r), s) for s, r in groups.items())):
        canonical.extend(order * len(_RANKS) + rank for rank in ranks)
    return bytes(canonical)


def canonical_deals():
    """Yield (deal, multiplicity) once per suit-distinct 6-card deal.

    The multiplicities sum to C(52,6); weight results by them to recover a
    statistic over the whole deck.
    """
    counts = Counter()
    for indices in combinations(range(len(_DECK)), 6):
        counts[_canonical_key(indices)] += 1
    for key, multiplicity in counts.items():
        # Sorted, so a swept deal is the very tuple _canonicalize would produce
        # -- the packed key groups by suit instead, which is a different order.
        yield tuple(sorted(_DECK[index] for index in key)), multiplicity


def _evaluate_canonical(cards, is_dealer, include_crib, weights=None):
    """Rank the 15 discards from an already-canonical, already-parsed deal."""
    dealt = frozenset(cards)
    unseen = [card for card in _DECK if card not in dealt]

    results = []
    for kept in combinations(range(6), 4):
        keep = [cards[i] for i in kept]
        toss = [cards[i] for i in range(6) if i not in kept]
        hand_ev = sum(_score(keep, starter) for starter in unseen) / len(unseen)
        if not include_crib:
            crib_ev = 0.0
        elif weights is None:
            crib_ev = _crib_ev(toss, unseen)
        else:
            crib_ev = _crib_ev_modeled(toss, unseen, weights)
        results.append(DiscardEval(
            keep=tuple(keep),
            discard=tuple(toss),
            hand_ev=hand_ev,
            crib_ev=crib_ev,
            total_ev=hand_ev + (crib_ev if is_dealer else -crib_ev),
        ))

    return tuple(sorted(results, key=lambda result: result.total_ev, reverse=True))


# Only one-off evaluation benefits from the cache: a sweep visits each canonical
# deal exactly once, so caching there would just grow in every worker.
@lru_cache(maxsize=4096)
def _evaluate_canonical_cached(cards, is_dealer, include_crib, opponent):
    return _evaluate_canonical(cards, is_dealer, include_crib,
                               _opponent_weights(opponent, is_dealer))


def evaluate_discards(hand, is_dealer=True, include_crib=False, opponent=None):
    """Rank all 15 ways to discard from a 6-card deal, best first.

    Each result carries the expected hand score over the 46 unseen starters. With
    include_crib the expected crib score is added as well (subtracted when the
    crib is the opponent's), which costs about a thousand times more work.

    By default the opponent's two crib cards are priced as a uniform draw from
    the unseen cards. Pass opponent="policy" to price them against what an
    opponent who weighs the crib actually throws, or "naive" for one who ignores
    it; a dict of class -> probability works too. Modelling the opponent shifts
    the crib EV by roughly half a point -- down for your crib, up for theirs --
    but rarely changes which discard comes out on top. It leaves the hand EV
    alone: what they throw cannot touch your own four cards.

    The work is done on the suit-canonical form of the deal and cached, so deals
    that differ only in which suits they use are evaluated once between them.
    """
    originals = list(hand)
    if len(originals) != 6:
        raise ValueError("a cribbage deal is six cards")
    cards = [_parse_card(card) for card in originals]
    if len(set(cards)) != 6:
        raise ValueError("duplicate cards in deal")

    canonical, suit_map = _canonicalize(cards)
    if isinstance(opponent, dict):      # a custom model is not a cache key
        results = _evaluate_canonical(canonical, is_dealer, include_crib, opponent)
    else:
        results = _evaluate_canonical_cached(canonical, is_dealer, include_crib, opponent)

    # Undo the relabeling, and hand back the caller's own cards in their order.
    # Equal-value discards are ordered by the deal as dealt, not by canonical
    # suit, so the ranking does not depend on which suits happened to be used.
    index_of = {(rank, suit_map[suit]): i for i, (rank, suit) in enumerate(cards)}
    restored = []
    for result in results:
        kept = tuple(sorted(index_of[card] for card in result.keep))
        tossed = tuple(sorted(index_of[card] for card in result.discard))
        restored.append((kept, result._replace(
            keep=tuple(originals[i] for i in kept),
            discard=tuple(originals[i] for i in tossed),
        )))
    restored.sort(key=lambda item: (-item[1].total_ev, item[0]))
    return [result for _, result in restored]


def _sweep_one(job):
    deal, multiplicity, is_dealer, include_crib, opponent = job
    weights = _opponent_weights(opponent, is_dealer)
    return deal, multiplicity, _evaluate_canonical(deal, is_dealer, include_crib, weights)[0]


def sweep(is_dealer=True, include_crib=False, opponent=None,
          processes=None, chunk_size=None):
    """Yield (deal, multiplicity, best discard) for every suit-distinct deal.

    Enumerating canonical deals rather than all C(52,6) of them is what makes a
    full sweep affordable. The deals are independent, so they are farmed out to
    a process pool -- processes defaults to every core, and processes=1 stays in
    this one. Results then arrive in completion order rather than deal order.

    Enumerating the canonical deals is itself a serial minute or so before any
    result appears. On platforms that spawn rather than fork, call this from
    under an `if __name__ == "__main__"` guard.
    """
    deals = canonical_deals()

    if processes == 1:
        weights = _opponent_weights(opponent, is_dealer)
        for deal, multiplicity in deals:
            yield deal, multiplicity, _evaluate_canonical(
                deal, is_dealer, include_crib, weights)[0]
        return

    # Crib EVs take a half-second each, so hand those out one at a time; bare
    # hand EVs are sub-millisecond and would drown in per-task overhead.
    if chunk_size is None:
        chunk_size = 1 if include_crib else 256

    jobs = ((deal, multiplicity, is_dealer, include_crib, opponent)
            for deal, multiplicity in deals)
    with Pool(processes) as pool:
        yield from pool.imap_unordered(_sweep_one, jobs, chunksize=chunk_size)


def best_discard(hand, is_dealer=True, include_crib=False, opponent=None) -> DiscardEval:
    """The highest expected-value discard from a 6-card deal."""
    return evaluate_discards(hand, is_dealer, include_crib, opponent)[0]
