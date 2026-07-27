#!/usr/bin/env python3
"""Emit opponent_model_data.c from the Python tables.

The Python opponent_model.py is the source of truth; this only translates it,
so regenerating the model (tools/gen_opponent_model.py in the parent) and then
re-running this keeps the two in step. Do not hand-edit the output.

Run from the c/ directory:  python3 tools/gen_opponent_model_c.py
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parent))

import opponent_model as m  # noqa: E402

TABLES = ["PONE_POLICY", "DEALER_POLICY", "PONE_NAIVE", "DEALER_NAIVE"]
OUT = HERE / "opponent_model_data.c"


def expand(table):
    """(low, high) -> (unsuited, suited) becomes [low][high][suited].

    Mirrors cribbage._expand: a same-rank pair has no suited form, because two
    cards of one rank cannot share a suit.
    """
    grid = [[[0.0, 0.0] for _ in range(14)] for _ in range(14)]
    for (low, high), (unsuited, suited) in table.items():
        grid[low][high][0] = unsuited
        if low != high:
            grid[low][high][1] = suited
    return grid


def main():
    lines = [
        "/* opponent_model_data.c -- GENERATED, do not edit.",
        " *",
        " * Translated from ../opponent_model.py by tools/gen_opponent_model_c.py.",
        " * What an opponent actually throws to the crib, measured rather than",
        " * assumed: each entry is the probability of a throw class, indexed by",
        " * [low rank][high rank][suited]. Ranks run 1 (ace) to 13 (king); index 0",
        " * is unused so ranks can index directly.",
        " */",
        "",
        '#include "cribbage.h"',
        "",
        "const double cr_opponent_tables[CR_OPP_NTABLES][14][14][2] = {",
    ]

    for name in TABLES:
        grid = expand(getattr(m, name))
        lines.append(f"    /* {name} */")
        lines.append("    {")
        for low in range(14):
            cells = ", ".join(
                f"{{{grid[low][high][0]:.6f}, {grid[low][high][1]:.6f}}}"
                for high in range(14)
            )
            lines.append(f"        {{{cells}}},")
        lines.append("    },")

    lines.append("};")
    lines.append("")

    OUT.write_text("\n".join(lines))

    total = sum(
        sum(v[0] + v[1] for v in getattr(m, name).values()) for name in TABLES
    )
    print(f"wrote {OUT.name}: {len(TABLES)} tables, probability mass {total / len(TABLES):.6f} each")


if __name__ == "__main__":
    main()
