/* test_cribbage.c -- correctness suite.
 *
 * The Python project's rule is that every real bug it found was caught by
 * differential testing: a fast implementation checked against a slow one that
 * was written a different way. This file does the same. It carries a second,
 * deliberately naive scorer that computes fifteens, pairs and runs directly,
 * and checks the table-driven one against it over every hand it can reach.
 *
 * tools/difftest.py adds the third leg: this C against cribbage.py itself.
 */

#include "cribbage.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* A tiny xorshift, so the suite is deterministic and needs nothing from the
 * platform's random number generator. */
static uint32_t next_rand(uint32_t *state)
{
    uint32_t x = *state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    return *state = x;
}

static int failures = 0;
static int checks = 0;

static void check(bool ok, const char *what)
{
    checks++;
    if (!ok) {
        failures++;
        printf("  FAIL: %s\n", what);
    }
}

static cr_card card(const char *text)
{
    cr_card c;
    if (!cr_parse_card(text, &c)) {
        fprintf(stderr, "bad card in test: %s\n", text);
        exit(2);
    }
    return c;
}

/* ------------------------------------- a slow, independent reference scorer */

static int ref_runs(const int ranks[5])
{
    int counts[CR_NRANKS + 2] = {0};
    for (int i = 0; i < 5; i++)
        counts[ranks[i]]++;

    int best = 0;
    /* Every window of three or more consecutive ranks, all present. */
    for (int start = 1; start <= CR_NRANKS; start++)
        for (int len = 3; start + len - 1 <= CR_NRANKS; len++) {
            int ways = 1, ok = 1;
            for (int r = start; r < start + len; r++) {
                if (!counts[r])
                    ok = 0;
                ways *= counts[r];
            }
            /* Maximal only: neither neighbour may extend it. */
            if (ok && !counts[start - 1] && !counts[start + len])
                best += len * ways;
        }
    return best;
}

static int reference_score(const cr_card hand[4], cr_card starter, bool is_crib)
{
    cr_card all[5];
    memcpy(all, hand, 4 * sizeof(cr_card));
    all[4] = starter;

    int ranks[5], values[5];
    for (int i = 0; i < 5; i++) {
        ranks[i] = all[i].rank;
        values[i] = all[i].rank < 10 ? all[i].rank : 10;
    }

    int score = 0;
    for (int mask = 0; mask < 32; mask++) {
        int n = 0, sum = 0;
        for (int i = 0; i < 5; i++)
            if (mask & (1 << i)) {
                n++;
                sum += values[i];
            }
        if (n >= 2 && sum == 15)
            score += 2;
    }
    for (int i = 0; i < 5; i++)
        for (int j = i + 1; j < 5; j++)
            if (ranks[i] == ranks[j])
                score += 2;

    score += ref_runs(ranks);

    bool flush4 = hand[0].suit == hand[1].suit && hand[1].suit == hand[2].suit &&
                  hand[2].suit == hand[3].suit;
    if (flush4) {
        if (hand[0].suit == starter.suit)
            score += 5;
        else if (!is_crib)
            score += 4;
    }
    for (int i = 0; i < 4; i++)
        if (hand[i].rank == CR_JACK && hand[i].suit == starter.suit)
            score += 1;

    return score;
}

/* ------------------------------------------------------------------ tests */

static void test_known_hands(void)
{
    printf("hand-checked cases\n");
    struct {
        const char *c[4];
        const char *starter;
        int expect;
        const char *what;
    } cases[] = {
        {{"5H", "5S", "5D", "JC"}, "5C", 29, "the 29 hand"},
        {{"5H", "5S", "5D", "5C"}, "JC", 28, "four fives, jack starter"},
        {{"AH", "2S", "3D", "4C"}, "6H", 6, "run of four plus a fifteen"},
        {{"AH", "2H", "3H", "4H"}, "6H", 11, "same, all one suit with starter"},
        {{"AH", "2H", "3H", "4H"}, "6S", 10, "same, four-card flush only"},
        {{"2H", "3S", "4D", "5C"}, "6H", 9, "run of five"},
        {{"KH", "QS", "JD", "10C"}, "9H", 5, "high run of five, no fifteens"},
        {{"JH", "2S", "4D", "6C"}, "8H", 1, "his nobs alone"},
        {{"2H", "4S", "6D", "8C"}, "KH", 0, "nothing at all"},
    };

    for (size_t i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        cr_card hand[4];
        for (int k = 0; k < 4; k++)
            hand[k] = card(cases[i].c[k]);
        int got = cr_score(hand, card(cases[i].starter), false);
        if (got != cases[i].expect)
            printf("  FAIL: %s -- expected %d, got %d\n", cases[i].what, cases[i].expect,
                   got);
        check(got == cases[i].expect, cases[i].what);
    }
    printf("  %d cases\n", (int)(sizeof cases / sizeof cases[0]));
}

/* Table-driven scorer vs the reference, over random hands, under both the hand
 * and the crib flush rule. */
static void test_against_reference(int trials)
{
    printf("table lookup vs direct computation, %d random hands\n", trials);
    uint32_t seed = 12345;
    int mismatches = 0;

    for (int t = 0; t < trials; t++) {
        int idx[5];
        for (int i = 0; i < 5; i++) {
        again:
            idx[i] = (int)(next_rand(&seed) % CR_DECK_SIZE);
            for (int j = 0; j < i; j++)
                if (idx[j] == idx[i])
                    goto again;
        }
        cr_card hand[4];
        for (int i = 0; i < 4; i++)
            hand[i] = cr_deck[idx[i]];
        cr_card starter = cr_deck[idx[4]];

        for (int crib = 0; crib < 2; crib++) {
            int fast = cr_score(hand, starter, crib);
            int slow = reference_score(hand, starter, crib);
            if (fast != slow) {
                if (mismatches++ < 3) {
                    char b[4];
                    printf("  FAIL:");
                    for (int i = 0; i < 4; i++) {
                        cr_format_card(hand[i], b);
                        printf(" %s", b);
                    }
                    cr_format_card(starter, b);
                    printf(" / %s  is_crib=%d  table=%d ref=%d\n", b, crib, fast, slow);
                }
            }
        }
    }
    check(mismatches == 0, "table matches reference");
    printf("  %d mismatches\n", mismatches);
}

/* Relabelling suits cannot change a score, so it cannot change any EV either.
 * This is the invariant the whole 21x reduction rests on. */
static void test_suit_invariance(void)
{
    printf("suit relabelling leaves scores alone\n");
    const char *from = "SHDC";
    const char *to = "HDCS"; /* a 4-cycle: still a permutation of the suits */
    uint32_t seed = 99;
    int mismatches = 0;

    for (int t = 0; t < 20000; t++) {
        int idx[5];
        for (int i = 0; i < 5; i++) {
        again:
            idx[i] = (int)(next_rand(&seed) % CR_DECK_SIZE);
            for (int j = 0; j < i; j++)
                if (idx[j] == idx[i])
                    goto again;
        }
        cr_card hand[4], moved[4];
        for (int i = 0; i < 4; i++) {
            hand[i] = cr_deck[idx[i]];
            moved[i] = hand[i];
            moved[i].suit = to[strchr(from, hand[i].suit) - from];
        }
        cr_card starter = cr_deck[idx[4]], starter_moved = starter;
        starter_moved.suit = to[strchr(from, starter.suit) - from];

        if (cr_score(hand, starter, false) != cr_score(moved, starter_moved, false))
            mismatches++;
    }
    check(mismatches == 0, "scores are invariant under suit relabelling");
    printf("  %d mismatches over 20000 hands\n", mismatches);
}

static void test_canonicalisation(void)
{
    printf("canonicalisation\n");
    cr_card deal[6], out[6];
    const char *text[6] = {"5C", "5D", "JH", "2S", "9S", "KD"};
    for (int i = 0; i < 6; i++)
        deal[i] = card(text[i]);

    char map[128];
    cr_canonicalize(deal, 6, out, map);

    /* Output is sorted by rank then suit, and every card survives. */
    bool sorted = true;
    for (int i = 1; i < 6; i++)
        if (out[i - 1].rank > out[i].rank ||
            (out[i - 1].rank == out[i].rank && out[i - 1].suit > out[i].suit))
            sorted = false;
    check(sorted, "canonical deal comes out sorted");

    int ranks_in = 0, ranks_out = 0;
    for (int i = 0; i < 6; i++) {
        ranks_in += deal[i].rank;
        ranks_out += out[i].rank;
    }
    check(ranks_in == ranks_out, "canonicalisation preserves ranks");

    /* Two deals differing only in which suits they use canonicalise alike. */
    cr_card other[6], other_out[6];
    const char *other_text[6] = {"5S", "5H", "JD", "2C", "9C", "KH"};
    for (int i = 0; i < 6; i++)
        other[i] = card(other_text[i]);
    cr_canonicalize(other, 6, other_out, map);

    bool same = true;
    for (int i = 0; i < 6; i++)
        if (out[i].rank != other_out[i].rank || out[i].suit != other_out[i].suit)
            same = false;
    check(same, "suit-equivalent deals share a canonical form");
}

/* The hand EV of a keep must equal the mean of its scores, and the ordering
 * the evaluator returns must actually be sorted. */
static void test_discard_ordering(void)
{
    printf("discard evaluation\n");
    cr_card deal[6];
    const char *text[6] = {"5H", "5S", "5D", "JC", "2H", "9D"};
    for (int i = 0; i < 6; i++)
        deal[i] = card(text[i]);

    cr_discard results[CR_NDISCARDS];
    cr_evaluate_discards(deal, true, false, results);

    bool ordered = true;
    for (int i = 1; i < CR_NDISCARDS; i++)
        if (results[i - 1].total_ev < results[i].total_ev - 1e-12)
            ordered = false;
    check(ordered, "discards come back best first");

    /* Recompute the winner's hand EV the long way. */
    cr_card unseen[CR_DECK_SIZE];
    int n = cr_unseen(deal, 6, unseen);
    double total = 0;
    for (int i = 0; i < n; i++)
        total += cr_score(results[0].keep, unseen[i], false);
    check(fabs(total / n - results[0].hand_ev) < 1e-9, "hand EV is the mean score");

    printf("  best keep has hand EV %.4f\n", results[0].hand_ev);
}

int main(void)
{
    cr_init();

    test_known_hands();
    test_against_reference(200000);
    test_suit_invariance();
    test_canonicalisation();
    test_discard_ordering();

    printf("\n%d checks, %d failures\n", checks, failures);
    return failures ? 1 : 0;
}
