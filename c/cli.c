/* cli.c -- command line front end.
 *
 *   crib score  <4 cards> <starter>   score a hand
 *   crib hand   <6 cards>             rank the fifteen discards, hand EV only
 *   crib crib   <6 cards> [pone] [policy|naive]
 *                                     rank them with crib EV too (slower)
 *
 * Cards are written "5H", "10S" or "TS", "AD". Case does not matter.
 */

#include "cribbage.h"

#include <stdio.h>
#include <string.h>

static int read_cards(char **argv, int n, cr_card *out)
{
    for (int i = 0; i < n; i++)
        if (!cr_parse_card(argv[i], &out[i])) {
            fprintf(stderr, "unrecognized card: %s\n", argv[i]);
            return 0;
        }
    return 1;
}

static void print_cards(const cr_card *cards, int n)
{
    char buf[4];
    for (int i = 0; i < n; i++) {
        cr_format_card(cards[i], buf);
        printf("%s%s", i ? " " : "", buf);
    }
}

static int usage(void)
{
    fprintf(stderr,
            "usage:\n"
            "  crib score <c1> <c2> <c3> <c4> <starter>\n"
            "  crib hand  <c1> ... <c6>\n"
            "  crib crib  <c1> ... <c6> [pone] [policy|naive]\n");
    return 2;
}

static int show_discards(char **cards_argv, bool include_crib, bool is_dealer,
                         cr_opponent opponent)
{
    cr_card deal[6];
    if (!read_cards(cards_argv, 6, deal))
        return 1;

    for (int i = 0; i < 6; i++)
        for (int j = i + 1; j < 6; j++)
            if (deal[i].rank == deal[j].rank && deal[i].suit == deal[j].suit) {
                fprintf(stderr, "duplicate cards in deal\n");
                return 1;
            }

    cr_discard results[CR_NDISCARDS];
    cr_evaluate_discards(deal, is_dealer, include_crib, opponent, results);

    printf("%-4s %-16s %-8s %8s %8s %8s\n", "", "keep", "toss", "hand", "crib", "total");
    for (int i = 0; i < CR_NDISCARDS; i++) {
        char keep_text[32] = {0}, toss_text[16] = {0}, buf[4];
        for (int k = 0; k < 4; k++) {
            cr_format_card(results[i].keep[k], buf);
            if (k)
                strcat(keep_text, " ");
            strcat(keep_text, buf);
        }
        for (int t = 0; t < 2; t++) {
            cr_format_card(results[i].toss[t], buf);
            if (t)
                strcat(toss_text, " ");
            strcat(toss_text, buf);
        }
        printf("%-4d %-16s %-8s %8.4f %8.4f %8.4f\n", i + 1, keep_text, toss_text,
               results[i].hand_ev, results[i].crib_ev, results[i].total_ev);
    }
    return 0;
}

int main(int argc, char **argv)
{
    cr_init();

    if (argc < 2)
        return usage();

    if (strcmp(argv[1], "score") == 0) {
        if (argc != 7)
            return usage();
        cr_card cards[5];
        if (!read_cards(&argv[2], 5, cards))
            return 1;
        printf("%d\n", cr_score(cards, cards[4], false));
        return 0;
    }

    if (strcmp(argv[1], "hand") == 0) {
        if (argc != 8)
            return usage();
        return show_discards(&argv[2], false, true, CR_UNIFORM);
    }

    if (strcmp(argv[1], "crib") == 0) {
        if (argc < 8)
            return usage();
        bool is_dealer = true;
        cr_opponent opponent = CR_UNIFORM;
        for (int i = 8; i < argc; i++) {
            if (strcmp(argv[i], "pone") == 0)
                is_dealer = false;
            else if (strcmp(argv[i], "policy") == 0)
                opponent = CR_POLICY;
            else if (strcmp(argv[i], "naive") == 0)
                opponent = CR_NAIVE;
            else
                return usage();
        }
        return show_discards(&argv[2], true, is_dealer, opponent);
    }

    (void)print_cards;
    return usage();
}
