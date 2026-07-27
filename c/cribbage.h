/* cribbage.h -- hand scoring and discard analysis in C.
 *
 * A straight port of cribbage.py. The algorithms are the same ones and the
 * comments explaining *why* they look like this live next to the code that
 * implements them, in cribbage.c. Results are intended to match the Python
 * exactly, not approximately; tools/difftest.py checks that they do.
 *
 * Ranks are 1..13 (ace..king). Suits are the characters 'S', 'H', 'D', 'C',
 * stored as characters rather than indices because canonicalisation orders
 * suits by their character, and matching Python's ordering matters.
 */
#ifndef CRIBBAGE_H
#define CRIBBAGE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define CR_NRANKS 13
#define CR_NSUITS 4
#define CR_DECK_SIZE 52
#define CR_JACK 11
#define CR_NDISCARDS 15 /* C(6,4) ways to keep four of six */

typedef struct {
    uint8_t rank; /* 1..13 */
    char suit;    /* 'S', 'H', 'D', 'C' */
} cr_card;

/* One of the fifteen ways to discard, with what it is worth. */
typedef struct {
    cr_card keep[4];
    cr_card toss[2];
    uint8_t keep_idx[4]; /* positions in the deal as passed in */
    uint8_t toss_idx[2];
    double hand_ev;
    double crib_ev;
    double total_ev; /* hand_ev +/- crib_ev, sign by whose crib it is */
} cr_discard;

/* Build the base-score table. Call once before anything else. */
void cr_init(void);

/* The 52-card deck, in the same order as Python's _DECK: suits S,H,D,C
 * outermost, ranks 1..13 within each. Valid after cr_init(). */
extern const cr_card cr_deck[CR_DECK_SIZE];

/* "5H", "10S", "TS", "ad" -> card. Returns false if unparseable. */
bool cr_parse_card(const char *text, cr_card *out);

/* Writes at most 4 bytes ("10S" plus NUL) into buf. */
void cr_format_card(cr_card card, char buf[4]);

/* Score four cards against a starter. is_crib applies the crib flush rule,
 * where four matching suits in hand score nothing without the starter. */
int cr_score(const cr_card hand[4], cr_card starter, bool is_crib);

/* Mean hand score over every unseen starter. */
double cr_hand_ev(const cr_card keep[4], const cr_card *unseen, int n_unseen);

/* Mean crib score for a two-card throw, over every starter and every pair the
 * opponent might contribute, drawn uniformly from the unseen cards. This is
 * where a sweep spends essentially all of its time. */
double cr_crib_ev(const cr_card toss[2], const cr_card *unseen, int n_unseen);

/* Which opponent the crib is priced against. Uniform treats their two cards as
 * a random draw -- the usual approximation, and the right one for *choosing* a
 * discard. Policy models an opponent who weighs the crib; naive one who ignores
 * it. Modelling shifts crib EV by about half a point but rarely changes which
 * discard wins; see ../ANALYSIS.md. */
typedef enum {
    CR_UNIFORM = 0,
    CR_POLICY = 1,
    CR_NAIVE = 2,
} cr_opponent;

/* Four tables: pone and dealer, policy and naive. Generated from
 * ../opponent_model.py by tools/gen_opponent_model_c.py. */
#define CR_OPP_NTABLES 4
extern const double cr_opponent_tables[CR_OPP_NTABLES][14][14][2];

/* The distribution facing you this deal, or NULL for uniform. When you deal,
 * the opponent is the pone throwing into your crib; when they deal, they are
 * feeding their own. */
const double (*cr_opponent_weights(cr_opponent opponent, bool is_dealer))[14][2];

/* Crib EV against an opponent who chooses. Same enumeration as cr_crib_ev,
 * except each throw carries the probability this opponent actually makes it. */
double cr_crib_ev_modeled(const cr_card toss[2], const cr_card *unseen, int n_unseen,
                          const double (*weights)[14][2]);

/* Relabel suits into canonical order. out receives n cards; suit_map, indexed
 * by the original suit character, receives the canonical character it became.
 * Permuting suits cannot change any score, so this collapses the 20,358,520
 * six-card deals to 962,988 distinct ones. */
void cr_canonicalize(const cr_card *in, int n, cr_card *out, char suit_map[128]);

/* Rank all fifteen discards from a six-card deal, best first. out must have
 * room for CR_NDISCARDS entries. Returns the number written (always 15).
 * opponent is ignored unless include_crib is set. */
int cr_evaluate_discards(const cr_card deal[6], bool is_dealer, bool include_crib,
                         cr_opponent opponent, cr_discard out[CR_NDISCARDS]);

/* Fills unseen with the 46 cards not in the deal. Returns the count. */
int cr_unseen(const cr_card *dealt, int n_dealt, cr_card *unseen);

#endif /* CRIBBAGE_H */
