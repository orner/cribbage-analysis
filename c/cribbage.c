/* cribbage.c -- see cribbage.h. Port of cribbage.py. */

#include "cribbage.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ------------------------------------------------------------------ deck */

const cr_card cr_deck[CR_DECK_SIZE] = {
#define ROW(s)                                                                        \
    {1, s}, {2, s}, {3, s}, {4, s}, {5, s}, {6, s}, {7, s}, {8, s}, {9, s}, {10, s},  \
        {11, s}, {12, s}, {13, s}
    ROW('S'), ROW('H'), ROW('D'), ROW('C')
#undef ROW
};

static const char CR_SUITS[CR_NSUITS + 1] = "SHDC";

static int suit_index(char suit)
{
    for (int i = 0; i < CR_NSUITS; i++)
        if (CR_SUITS[i] == suit)
            return i;
    return -1;
}

bool cr_parse_card(const char *text, cr_card *out)
{
    if (!text)
        return false;
    while (*text == ' ')
        text++;

    size_t len = strlen(text);
    while (len > 0 && (text[len - 1] == ' ' || text[len - 1] == '\n'))
        len--;
    if (len < 2 || len > 3)
        return false;

    char suit = (char)toupper((unsigned char)text[len - 1]);
    if (suit_index(suit) < 0)
        return false;

    int rank;
    if (len == 3) {
        if (text[0] != '1' || text[1] != '0')
            return false;
        rank = 10;
    } else {
        char c = (char)toupper((unsigned char)text[0]);
        switch (c) {
        case 'A': rank = 1; break;
        case 'T': rank = 10; break;
        case 'J': rank = 11; break;
        case 'Q': rank = 12; break;
        case 'K': rank = 13; break;
        default:
            if (c < '2' || c > '9')
                return false;
            rank = c - '0';
        }
    }
    out->rank = (uint8_t)rank;
    out->suit = suit;
    return true;
}

void cr_format_card(cr_card card, char buf[4])
{
    static const char *names[] = {"", "A", "2", "3", "4",  "5", "6",
                                  "7", "8", "9", "10", "J", "Q", "K"};
    snprintf(buf, 4, "%s%c", names[card.rank], card.suit);
}

/* --------------------------------------------------- the base-score table */

/* Each rank owns one nibble of a 64-bit integer, so adding up five cards'
 * values counts how many of each rank are present -- no rank can appear more
 * than four times, so the nibbles never carry. That sum identifies the rank
 * multiset on its own, which means the table can be keyed without sorting the
 * ranks first: five array lookups and four adds in the hot loop, no sorting
 * and no hashing of a sequence. */
static uint64_t RANK_BITS[CR_NRANKS + 1];

/* 6,175 five-card rank multisets exist in a real deck. An open-addressed table
 * with room to spare keeps lookups to about one probe. A key of 0 cannot occur
 * (five cards always contribute five nibbles), so 0 marks an empty slot. */
#define TABLE_BITS 14
#define TABLE_SIZE (1u << TABLE_BITS)
#define TABLE_MASK (TABLE_SIZE - 1u)

static uint64_t table_keys[TABLE_SIZE];
static int16_t table_vals[TABLE_SIZE];

static inline uint32_t table_slot(uint64_t key)
{
    /* Fibonacci hashing: multiply by 2^64/phi and take the high bits. */
    return (uint32_t)((key * 0x9E3779B97F4A7C15ULL) >> (64 - TABLE_BITS));
}

static inline int base_lookup(uint64_t key)
{
    uint32_t slot = table_slot(key);
    for (;;) {
        if (table_keys[slot] == key)
            return table_vals[slot];
        slot = (slot + 1) & TABLE_MASK;
    }
}

static void table_insert(uint64_t key, int value)
{
    uint32_t slot = table_slot(key);
    while (table_keys[slot] != 0) {
        if (table_keys[slot] == key)
            return;
        slot = (slot + 1) & TABLE_MASK;
    }
    table_keys[slot] = key;
    table_vals[slot] = (int16_t)value;
}

/* Fifteens, pairs and runs for five ranks. Suit-independent, which is the
 * whole reason this can be precomputed. */
static int base_score(const int ranks[5])
{
    int score = 0;

    /* Fifteens: every subset of two or more summing to fifteen, face cards
     * counting ten. Thirty-two subsets is cheap enough to enumerate whole. */
    int values[5];
    for (int i = 0; i < 5; i++)
        values[i] = ranks[i] < 10 ? ranks[i] : 10;
    for (int mask = 0; mask < 32; mask++) {
        int count = 0, sum = 0;
        for (int i = 0; i < 5; i++)
            if (mask & (1 << i)) {
                count++;
                sum += values[i];
            }
        if (count >= 2 && sum == 15)
            score += 2;
    }

    int counts[CR_NRANKS + 2] = {0};
    for (int i = 0; i < 5; i++)
        counts[ranks[i]]++;

    /* Pairs: two points per matching pair, which covers three and four of a
     * kind without a special case. */
    for (int rank = 1; rank <= CR_NRANKS; rank++)
        score += 2 * (counts[rank] * (counts[rank] - 1) / 2);

    /* Runs: each maximal run of three or more distinct ranks scores its
     * length, once per combination of the duplicated ranks inside it. The loop
     * runs one past the last rank so a run ending at a king still closes. */
    int length = 0, ways = 1;
    for (int rank = 1; rank <= CR_NRANKS + 1; rank++) {
        if (counts[rank]) {
            length++;
            ways *= counts[rank];
        } else {
            if (length >= 3)
                score += length * ways;
            length = 0;
            ways = 1;
        }
    }

    return score;
}

static void build_table(void)
{
    RANK_BITS[0] = 0;
    for (int rank = 1; rank <= CR_NRANKS; rank++)
        RANK_BITS[rank] = (uint64_t)1 << (4 * (rank - 1));

    /* Every multiset of five ranks, in nondecreasing order, with no rank used
     * more than the four times a deck can supply. */
    int ranks[5];
    for (ranks[0] = 1; ranks[0] <= CR_NRANKS; ranks[0]++)
        for (ranks[1] = ranks[0]; ranks[1] <= CR_NRANKS; ranks[1]++)
            for (ranks[2] = ranks[1]; ranks[2] <= CR_NRANKS; ranks[2]++)
                for (ranks[3] = ranks[2]; ranks[3] <= CR_NRANKS; ranks[3]++)
                    for (ranks[4] = ranks[3]; ranks[4] <= CR_NRANKS; ranks[4]++) {
                        int counts[CR_NRANKS + 1] = {0};
                        int ok = 1;
                        for (int i = 0; i < 5; i++)
                            if (++counts[ranks[i]] > 4)
                                ok = 0;
                        if (!ok)
                            continue;
                        uint64_t key = 0;
                        for (int i = 0; i < 5; i++)
                            key += RANK_BITS[ranks[i]];
                        table_insert(key, base_score(ranks));
                    }
}

void cr_init(void)
{
    static bool done = false;
    if (done)
        return;
    done = true;
    build_table();
}

/* ---------------------------------------------------------------- scoring */

int cr_score(const cr_card hand[4], cr_card starter, bool is_crib)
{
    /* Unpacked by hand rather than looped over: at hundreds of billions of
     * calls in a full sweep, the loop overhead costs more than the lookup. */
    const uint8_t ra = hand[0].rank, rb = hand[1].rank;
    const uint8_t rc = hand[2].rank, rd = hand[3].rank;
    const char sa = hand[0].suit, sb = hand[1].suit;
    const char sc = hand[2].suit, sd = hand[3].suit;

    int score = base_lookup(RANK_BITS[ra] + RANK_BITS[rb] + RANK_BITS[rc] +
                            RANK_BITS[rd] + RANK_BITS[starter.rank]);

    /* Flush: four matching suits in hand score four, five if the starter
     * matches too. A crib only ever scores the five-card flush. */
    if (sa == sb && sb == sc && sc == sd) {
        if (sa == starter.suit)
            score += 5;
        else if (!is_crib)
            score += 4;
    }

    /* His nobs: a jack in hand whose suit matches the starter. */
    if ((ra == CR_JACK && sa == starter.suit) || (rb == CR_JACK && sb == starter.suit) ||
        (rc == CR_JACK && sc == starter.suit) || (rd == CR_JACK && sd == starter.suit))
        score += 1;

    return score;
}

double cr_hand_ev(const cr_card keep[4], const cr_card *unseen, int n_unseen)
{
    long total = 0;
    for (int i = 0; i < n_unseen; i++)
        total += cr_score(keep, unseen[i], false);
    return (double)total / (double)n_unseen;
}

/* ---------------------------------------------------------------- crib EV */

double cr_crib_ev(const cr_card toss[2], const cr_card *unseen, int n_unseen)
{
    const char suit_a = toss[0].suit, suit_b = toss[1].suit;
    const uint64_t toss_key = RANK_BITS[toss[0].rank] + RANK_BITS[toss[1].rank];
    const bool toss_suited = suit_a == suit_b;

    /* Which suits a tossed jack could claim nobs with. */
    char jack_suits[2] = {0, 0};
    int n_jacks = 0;
    for (int i = 0; i < 2; i++)
        if (toss[i].rank == CR_JACK)
            jack_suits[n_jacks++] = toss[i].suit;

    /* Hoist the per-card work out of the inner loop. */
    uint64_t keys[CR_DECK_SIZE];
    uint8_t ranks[CR_DECK_SIZE];
    char suits[CR_DECK_SIZE];
    for (int i = 0; i < n_unseen; i++) {
        keys[i] = RANK_BITS[unseen[i].rank];
        ranks[i] = unseen[i].rank;
        suits[i] = unseen[i].suit;
    }

    long total = 0;

    for (int s = 0; s < n_unseen; s++) {
        const char starter_suit = suits[s];
        const uint64_t base = toss_key + keys[s];

        /* A crib flush needs all five cards suited, so the two tossed cards
         * and the starter must agree before either opponent card can matter. */
        const bool flush_possible = toss_suited && suit_a == starter_suit;

        int nobs = 0;
        for (int i = 0; i < n_jacks; i++)
            if (jack_suits[i] == starter_suit)
                nobs = 1;

        /* The opponent's two cards, drawn from everything unseen but the
         * starter. Skipping index s in place beats rebuilding the list. */
        for (int i = 0; i < n_unseen; i++) {
            if (i == s)
                continue;
            const uint64_t base_i = base + keys[i];
            const bool jack_i = !nobs && ranks[i] == CR_JACK && suits[i] == starter_suit;
            const bool flush_i = flush_possible && suits[i] == starter_suit;

            for (int j = i + 1; j < n_unseen; j++) {
                if (j == s)
                    continue;
                int score = base_lookup(base_i + keys[j]) + nobs;
                if (jack_i ||
                    (!nobs && ranks[j] == CR_JACK && suits[j] == starter_suit))
                    score += 1;
                if (flush_i && suits[j] == starter_suit)
                    score += 5;
                total += score;
            }
        }
    }

    /* Every (starter, unordered opponent pair) the loops above visited. */
    const double count = (double)n_unseen;
    return (double)total / (count * (count - 1) * (count - 2) / 2.0);
}

/* ------------------------------------------------------- modelled crib EV */

/* How many concrete two-card throws each class has in a full deck: six for a
 * same-rank pair, four suited and twelve unsuited for two different ranks. */
static inline double class_size(int low, int high, bool suited)
{
    if (low == high)
        return 6.0;
    return suited ? 4.0 : 12.0;
}

const double (*cr_opponent_weights(cr_opponent opponent, bool is_dealer))[14][2]
{
    if (opponent == CR_UNIFORM)
        return NULL;
    /* When I deal, the opponent is the pone throwing into my crib; when they
     * deal, they are feeding their own. */
    int table = (opponent == CR_POLICY) ? (is_dealer ? 0 : 1) : (is_dealer ? 2 : 3);
    return cr_opponent_tables[table];
}

double cr_crib_ev_modeled(const cr_card toss[2], const cr_card *unseen, int n_unseen,
                          const double (*weights)[14][2])
{
    const char suit_a = toss[0].suit, suit_b = toss[1].suit;
    const uint64_t toss_key = RANK_BITS[toss[0].rank] + RANK_BITS[toss[1].rank];
    const bool toss_suited = suit_a == suit_b;

    char jack_suits[2] = {0, 0};
    int n_jacks = 0;
    for (int i = 0; i < 2; i++)
        if (toss[i].rank == CR_JACK)
            jack_suits[n_jacks++] = toss[i].suit;

    /* Every throw the opponent might make that this model gives any weight to.
     * A class's probability is split evenly across the throws it has in a full
     * deck, so a class you have partly blocked -- because you hold cards it
     * needs -- keeps only the share that survives, which is what conditioning
     * on your own hand should do. The divisor is then the weight that really
     * accumulated, not the weight the class started with. */
    struct throw_option {
        double weight;
        int i, j;
        uint64_t key;
        uint8_t rank_c, rank_d;
        char suit_c, suit_d;
    };
    static _Thread_local struct throw_option throws[CR_DECK_SIZE * CR_DECK_SIZE / 2];
    int n_throws = 0;

    for (int i = 0; i < n_unseen; i++)
        for (int j = i + 1; j < n_unseen; j++) {
            int ra = unseen[i].rank, rb = unseen[j].rank;
            int low = ra <= rb ? ra : rb, high = ra <= rb ? rb : ra;
            bool suited = unseen[i].suit == unseen[j].suit;
            double weight = weights[low][high][suited ? 1 : 0];
            if (weight == 0.0)
                continue;
            struct throw_option *t = &throws[n_throws++];
            t->weight = weight / class_size(low, high, suited);
            t->i = i;
            t->j = j;
            t->key = RANK_BITS[ra] + RANK_BITS[rb];
            t->rank_c = unseen[i].rank;
            t->rank_d = unseen[j].rank;
            t->suit_c = unseen[i].suit;
            t->suit_d = unseen[j].suit;
        }

    double total = 0.0, weight_total = 0.0;

    for (int s = 0; s < n_unseen; s++) {
        const char starter_suit = unseen[s].suit;
        const uint64_t base = toss_key + RANK_BITS[unseen[s].rank];
        const bool flush_possible = toss_suited && suit_a == starter_suit;

        int nobs = 0;
        for (int k = 0; k < n_jacks; k++)
            if (jack_suits[k] == starter_suit)
                nobs = 1;

        for (int t = 0; t < n_throws; t++) {
            const struct throw_option *o = &throws[t];
            if (o->i == s || o->j == s)
                continue;
            int score = base_lookup(base + o->key) + nobs;
            if (!nobs && ((o->rank_c == CR_JACK && o->suit_c == starter_suit) ||
                          (o->rank_d == CR_JACK && o->suit_d == starter_suit)))
                score += 1;
            if (flush_possible && o->suit_c == starter_suit && o->suit_d == starter_suit)
                score += 5;
            total += o->weight * score;
            weight_total += o->weight;
        }
    }

    return total / weight_total;
}

/* -------------------------------------------------------- canonicalisation */

/* Sorting helper: the rank multiset a suit holds, plus the suit itself. */
typedef struct {
    int ranks[6];
    int n;
    char suit;
} suit_group;

/* Python compares (tuple_of_ranks, suit_char), so ranks lexicographically with
 * the shorter tuple first on a prefix tie, then the suit character -- which
 * orders C < D < H < S, not the deck's S,H,D,C. Reproducing that exactly is
 * what keeps canonical forms identical between the two implementations. */
static int compare_groups(const void *pa, const void *pb)
{
    const suit_group *a = (const suit_group *)pa;
    const suit_group *b = (const suit_group *)pb;
    int n = a->n < b->n ? a->n : b->n;
    for (int i = 0; i < n; i++)
        if (a->ranks[i] != b->ranks[i])
            return a->ranks[i] < b->ranks[i] ? -1 : 1;
    if (a->n != b->n)
        return a->n < b->n ? -1 : 1;
    return (int)a->suit - (int)b->suit;
}

/* Cards sort by rank, then by suit character, matching Python's sorted(). */
static int compare_cards(const void *pa, const void *pb)
{
    const cr_card *a = (const cr_card *)pa;
    const cr_card *b = (const cr_card *)pb;
    if (a->rank != b->rank)
        return a->rank < b->rank ? -1 : 1;
    return (int)a->suit - (int)b->suit;
}

static int compare_ints(const void *pa, const void *pb)
{
    int a = *(const int *)pa, b = *(const int *)pb;
    return a < b ? -1 : (a > b ? 1 : 0);
}

void cr_canonicalize(const cr_card *in, int n, cr_card *out, char suit_map[128])
{
    suit_group groups[CR_NSUITS];
    int n_groups = 0;

    for (int i = 0; i < CR_NSUITS; i++) {
        suit_group g = {{0}, 0, CR_SUITS[i]};
        for (int j = 0; j < n; j++)
            if (in[j].suit == CR_SUITS[i])
                g.ranks[g.n++] = in[j].rank;
        if (g.n) {
            qsort(g.ranks, (size_t)g.n, sizeof g.ranks[0], compare_ints);
            groups[n_groups++] = g;
        }
    }

    qsort(groups, (size_t)n_groups, sizeof groups[0], compare_groups);

    memset(suit_map, 0, 128);
    for (int i = 0; i < n_groups; i++)
        suit_map[(unsigned char)groups[i].suit] = CR_SUITS[i];

    for (int i = 0; i < n; i++) {
        out[i].rank = in[i].rank;
        out[i].suit = suit_map[(unsigned char)in[i].suit];
    }
    qsort(out, (size_t)n, sizeof out[0], compare_cards);
}

/* ------------------------------------------------------------- evaluation */

int cr_unseen(const cr_card *dealt, int n_dealt, cr_card *unseen)
{
    int n = 0;
    for (int i = 0; i < CR_DECK_SIZE; i++) {
        bool held = false;
        for (int j = 0; j < n_dealt; j++)
            if (cr_deck[i].rank == dealt[j].rank && cr_deck[i].suit == dealt[j].suit)
                held = true;
        if (!held)
            unseen[n++] = cr_deck[i];
    }
    return n;
}

/* The fifteen ways to keep four of six, in the order itertools.combinations
 * produces them, so ties break the same way they do in Python. */
static const uint8_t KEEP_SETS[CR_NDISCARDS][4] = {
    {0, 1, 2, 3}, {0, 1, 2, 4}, {0, 1, 2, 5}, {0, 1, 3, 4}, {0, 1, 3, 5},
    {0, 1, 4, 5}, {0, 2, 3, 4}, {0, 2, 3, 5}, {0, 2, 4, 5}, {0, 3, 4, 5},
    {1, 2, 3, 4}, {1, 2, 3, 5}, {1, 2, 4, 5}, {1, 3, 4, 5}, {2, 3, 4, 5},
};

static int compare_discards(const void *pa, const void *pb)
{
    const cr_discard *a = (const cr_discard *)pa;
    const cr_discard *b = (const cr_discard *)pb;
    if (a->total_ev != b->total_ev)
        return a->total_ev > b->total_ev ? -1 : 1;
    /* Equal value: order by the deal as dealt, so the ranking does not depend
     * on which suits happened to be used. */
    for (int i = 0; i < 4; i++)
        if (a->keep_idx[i] != b->keep_idx[i])
            return a->keep_idx[i] < b->keep_idx[i] ? -1 : 1;
    return 0;
}

int cr_evaluate_discards(const cr_card deal[6], bool is_dealer, bool include_crib,
                         cr_opponent opponent, cr_discard out[CR_NDISCARDS])
{
    cr_card unseen[CR_DECK_SIZE];
    int n_unseen = cr_unseen(deal, 6, unseen);
    const double(*weights)[14][2] = cr_opponent_weights(opponent, is_dealer);

    for (int d = 0; d < CR_NDISCARDS; d++) {
        cr_discard *r = &out[d];
        bool kept[6] = {false, false, false, false, false, false};

        for (int i = 0; i < 4; i++) {
            int idx = KEEP_SETS[d][i];
            kept[idx] = true;
            r->keep[i] = deal[idx];
            r->keep_idx[i] = (uint8_t)idx;
        }
        for (int i = 0, t = 0; i < 6; i++)
            if (!kept[i]) {
                r->toss[t] = deal[i];
                r->toss_idx[t] = (uint8_t)i;
                t++;
            }

        r->hand_ev = cr_hand_ev(r->keep, unseen, n_unseen);
        if (!include_crib)
            r->crib_ev = 0.0;
        else if (weights == NULL)
            r->crib_ev = cr_crib_ev(r->toss, unseen, n_unseen);
        else
            r->crib_ev = cr_crib_ev_modeled(r->toss, unseen, n_unseen, weights);
        r->total_ev = r->hand_ev + (is_dealer ? r->crib_ev : -r->crib_ev);
    }

    qsort(out, CR_NDISCARDS, sizeof out[0], compare_discards);
    return CR_NDISCARDS;
}
