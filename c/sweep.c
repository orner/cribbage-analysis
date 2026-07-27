/* sweep.c -- evaluate every deal in the game.
 *
 *   crib_sweep hand [threads]    best discard by hand EV, all 962,988 deals
 *   crib_sweep crib [threads]    ... with crib EV as well (much slower)
 *
 * There are C(52,6) = 20,358,520 six-card deals, but permuting the four suits
 * maps the deck onto itself and so cannot change any score. Keeping one
 * representative per equivalence class leaves 962,988 -- a 21.1x reduction,
 * and the single thing that makes a full sweep affordable. Each canonical deal
 * carries the multiplicity of the class it stands for, so weighting by it
 * recovers a statistic over the whole deck.
 */

#include "cribbage.h"

#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* -------------------------------------------- enumerating canonical deals */

/* A canonical deal packed as six deck indices, one byte each. */
typedef struct {
    uint64_t key;
    uint32_t multiplicity;
} canonical_deal;

#define DEAL_TABLE_BITS 21 /* 2,097,152 slots for ~963k deals */
#define DEAL_TABLE_SIZE (1u << DEAL_TABLE_BITS)
#define DEAL_TABLE_MASK (DEAL_TABLE_SIZE - 1u)

static canonical_deal *deal_table;
static size_t deal_count;

static inline uint32_t deal_slot(uint64_t key)
{
    return (uint32_t)((key * 0x9E3779B97F4A7C15ULL) >> (64 - DEAL_TABLE_BITS));
}

static void deal_add(uint64_t key)
{
    uint32_t slot = deal_slot(key);
    for (;;) {
        if (deal_table[slot].multiplicity == 0) {
            deal_table[slot].key = key;
            deal_table[slot].multiplicity = 1;
            deal_count++;
            return;
        }
        if (deal_table[slot].key == key) {
            deal_table[slot].multiplicity++;
            return;
        }
        slot = (slot + 1) & DEAL_TABLE_MASK;
    }
}

/* Canonical key for a deal given as ascending deck indices. Indices arrive
 * sorted, so each suit's ranks are already in order; the suits are then
 * relabelled by the sorted order of the rank lists they hold. */
static uint64_t canonical_key(const int idx[6])
{
    int ranks[CR_NSUITS][6];
    int n[CR_NSUITS] = {0, 0, 0, 0};

    for (int i = 0; i < 6; i++) {
        int suit = idx[i] / CR_NRANKS;
        ranks[suit][n[suit]++] = idx[i] % CR_NRANKS;
    }

    /* Order the non-empty suits by (rank list, suit index), matching the
     * Python. Only four of them, so a selection sort is plenty. */
    int order[CR_NSUITS], n_groups = 0;
    for (int s = 0; s < CR_NSUITS; s++)
        if (n[s])
            order[n_groups++] = s;

    for (int i = 0; i < n_groups; i++)
        for (int j = i + 1; j < n_groups; j++) {
            int a = order[i], b = order[j];
            int len = n[a] < n[b] ? n[a] : n[b], cmp = 0;
            for (int k = 0; k < len && !cmp; k++)
                cmp = ranks[a][k] - ranks[b][k];
            if (!cmp)
                cmp = n[a] - n[b];
            if (!cmp)
                cmp = a - b;
            if (cmp > 0) {
                order[i] = b;
                order[j] = a;
            }
        }

    uint64_t key = 0;
    int written = 0;
    for (int g = 0; g < n_groups; g++) {
        int s = order[g];
        for (int k = 0; k < n[s]; k++) {
            uint64_t byte = (uint64_t)(g * CR_NRANKS + ranks[s][k]);
            key |= byte << (8 * written);
            written++;
        }
    }
    return key;
}

static void enumerate_deals(void)
{
    deal_table = calloc(DEAL_TABLE_SIZE, sizeof *deal_table);
    if (!deal_table) {
        fprintf(stderr, "out of memory\n");
        exit(1);
    }

    int idx[6];
    for (idx[0] = 0; idx[0] < CR_DECK_SIZE; idx[0]++)
        for (idx[1] = idx[0] + 1; idx[1] < CR_DECK_SIZE; idx[1]++)
            for (idx[2] = idx[1] + 1; idx[2] < CR_DECK_SIZE; idx[2]++)
                for (idx[3] = idx[2] + 1; idx[3] < CR_DECK_SIZE; idx[3]++)
                    for (idx[4] = idx[3] + 1; idx[4] < CR_DECK_SIZE; idx[4]++)
                        for (idx[5] = idx[4] + 1; idx[5] < CR_DECK_SIZE; idx[5]++)
                            deal_add(canonical_key(idx));
}

/* Unpack a canonical key back into six cards, sorted by rank then suit. */
static void key_to_cards(uint64_t key, cr_card out[6])
{
    static const char suits[] = "SHDC";
    for (int i = 0; i < 6; i++) {
        int byte = (int)((key >> (8 * i)) & 0xFF);
        out[i].rank = (uint8_t)(byte % CR_NRANKS + 1);
        out[i].suit = suits[byte / CR_NRANKS];
    }
    for (int i = 1; i < 6; i++) /* insertion sort, six elements */
        for (int j = i; j > 0; j--) {
            bool swap = out[j].rank < out[j - 1].rank ||
                        (out[j].rank == out[j - 1].rank && out[j].suit < out[j - 1].suit);
            if (!swap)
                break;
            cr_card tmp = out[j];
            out[j] = out[j - 1];
            out[j - 1] = tmp;
        }
}

/* ------------------------------------------------------------ the sweep */

typedef struct {
    canonical_deal *deals;
    size_t start, end;
    bool include_crib;
    cr_opponent opponent;
    /* accumulated, weighted by multiplicity */
    double dealer_hand, dealer_crib, dealer_total;
    double pone_hand, pone_crib, pone_total;
    double weight;
    size_t differ; /* deals where the two roles keep different cards */
    size_t done;
} worker;

static size_t total_deals_for_progress;
static pthread_mutex_t progress_lock = PTHREAD_MUTEX_INITIALIZER;
static size_t progress_done;

static void *run_worker(void *arg)
{
    worker *w = (worker *)arg;
    cr_discard dealer[CR_NDISCARDS], pone[CR_NDISCARDS];

    for (size_t i = w->start; i < w->end; i++) {
        cr_card deal[6];
        key_to_cards(w->deals[i].key, deal);
        double m = (double)w->deals[i].multiplicity;

        cr_evaluate_discards(deal, true, w->include_crib, w->opponent, dealer);
        cr_evaluate_discards(deal, false, w->include_crib, w->opponent, pone);

        w->dealer_hand += m * dealer[0].hand_ev;
        w->dealer_crib += m * dealer[0].crib_ev;
        w->dealer_total += m * dealer[0].total_ev;
        w->pone_hand += m * pone[0].hand_ev;
        w->pone_crib += m * pone[0].crib_ev;
        w->pone_total += m * pone[0].total_ev;
        w->weight += m;

        bool same = true;
        for (int k = 0; k < 4; k++)
            if (dealer[0].keep_idx[k] != pone[0].keep_idx[k])
                same = false;
        if (!same)
            w->differ += w->deals[i].multiplicity;

        if ((++w->done & 0x3FF) == 0) {
            pthread_mutex_lock(&progress_lock);
            progress_done += 1024;
            if ((progress_done % (total_deals_for_progress / 20 + 1)) < 1024)
                fprintf(stderr, "  %zu%%\n",
                        100 * progress_done / total_deals_for_progress);
            pthread_mutex_unlock(&progress_lock);
        }
    }
    return NULL;
}

int main(int argc, char **argv)
{
    bool include_crib = argc > 1 && strcmp(argv[1], "crib") == 0;
    if (argc > 1 && strcmp(argv[1], "hand") != 0 && !include_crib) {
        fprintf(stderr, "usage: crib_sweep hand|crib [threads] [policy|naive]\n");
        return 2;
    }
    cr_opponent opponent = CR_UNIFORM;
    for (int i = 2; i < argc; i++) {
        if (strcmp(argv[i], "policy") == 0)
            opponent = CR_POLICY;
        else if (strcmp(argv[i], "naive") == 0)
            opponent = CR_NAIVE;
    }
    int threads = argc > 2 && atoi(argv[2]) > 0 ? atoi(argv[2]) : 4;
    if (threads < 1)
        threads = 1;

    cr_init();

    fprintf(stderr, "enumerating canonical deals...\n");
    clock_t t0 = clock();
    enumerate_deals();
    fprintf(stderr, "  %zu canonical deals in %.1fs\n", deal_count,
            (double)(clock() - t0) / CLOCKS_PER_SEC);

    /* Compact the hash table into a dense array the threads can slice. */
    canonical_deal *deals = malloc(deal_count * sizeof *deals);
    size_t n = 0;
    for (size_t i = 0; i < DEAL_TABLE_SIZE; i++)
        if (deal_table[i].multiplicity)
            deals[n++] = deal_table[i];
    free(deal_table);

    total_deals_for_progress = n;
    fprintf(stderr, "sweeping with %d thread(s), opponent=%s%s...\n", threads,
            opponent == CR_UNIFORM ? "uniform" : (opponent == CR_POLICY ? "policy" : "naive"),
            include_crib ? " (crib EV: this takes a while)" : "");

    worker *workers = calloc((size_t)threads, sizeof *workers);
    pthread_t *tids = malloc((size_t)threads * sizeof *tids);
    for (int t = 0; t < threads; t++) {
        workers[t].deals = deals;
        workers[t].start = n * (size_t)t / (size_t)threads;
        workers[t].end = n * (size_t)(t + 1) / (size_t)threads;
        workers[t].include_crib = include_crib;
        workers[t].opponent = opponent;
        pthread_create(&tids[t], NULL, run_worker, &workers[t]);
    }

    worker sum = {0};
    for (int t = 0; t < threads; t++) {
        pthread_join(tids[t], NULL);
        sum.dealer_hand += workers[t].dealer_hand;
        sum.dealer_crib += workers[t].dealer_crib;
        sum.dealer_total += workers[t].dealer_total;
        sum.pone_hand += workers[t].pone_hand;
        sum.pone_crib += workers[t].pone_crib;
        sum.pone_total += workers[t].pone_total;
        sum.weight += workers[t].weight;
        sum.differ += workers[t].differ;
    }

    printf("\ncanonical deals   %zu\n", n);
    printf("weighted deals    %.0f   (C(52,6) = 20358520)\n", sum.weight);
    printf("\n%-10s %10s %10s %10s\n", "", "hand EV", "crib EV", "total");
    printf("%-10s %10.3f %10.3f %10.3f\n", "as dealer", sum.dealer_hand / sum.weight,
           sum.dealer_crib / sum.weight, sum.dealer_total / sum.weight);
    printf("%-10s %10.3f %10.3f %10.3f\n", "as pone", sum.pone_hand / sum.weight,
           sum.pone_crib / sum.weight, sum.pone_total / sum.weight);
    printf("\nroles keep different cards in %.1f%% of deals\n",
           100.0 * (double)sum.differ / sum.weight);

    free(deals);
    free(workers);
    free(tids);
    return 0;
}
