"""Exhaustively verify the fault-identification benchmark using only stdlib.

Run: python tests/verify_sensor_selection.py

Exactly one of faults 1..9 exists. Test Ti answers 1 precisely for the faults
in TESTS[i - 1]. Select distinct tests before seeing any answers. At most two
selected answers may be flipped. A selection works iff every pair of fault
codewords has Hamming distance at least 5: disjoint radius-2 Hamming balls are
both necessary and sufficient for unique correction.

The exhaustive search visits all 2**18 selections, including every smaller
selection. A second, direct enumeration checks the received answer strings of
each reported optimum, independently of the pair-distance search.
"""

from collections import Counter
from itertools import combinations
import json
from math import ceil, comb


FAULTS = tuple(range(1, 10))
TESTS = (
    (2, 7, 8),
    (6, 8, 9),
    (3, 7, 9),
    (2, 6, 7),
    (1, 6, 7),
    (1, 5, 7),
    (5, 7, 8),
    (1, 5, 9),
    (4, 5, 7),
    (3, 5, 6),
    (3, 4, 8),
    (1, 2, 9),
    (1, 2, 4),
    (1, 4, 7),
    (1, 3, 4),
    (3, 5, 9),
    (2, 3, 6),
    (1, 7, 8),
)
MAX_ERRORS = 2
FORBIDDEN_TEST = 2
EXPECTED_OPTIMA = (
    (1, 2, 3, 5, 8, 9, 10, 11, 12, 13, 15, 17),
    (2, 3, 5, 8, 9, 10, 11, 12, 13, 15, 17, 18),
)
EXPECTED_COUNTS = {12: 2, 13: 131, 14: 603, 15: 486, 16: 138, 17: 18, 18: 1}
EXPECTED_FORBIDDEN_COUNTS = {13: 8, 14: 45, 15: 45, 16: 12, 17: 1}


def selected_tests(mask):
    return tuple(i + 1 for i in range(len(TESTS)) if mask & (1 << i))


def check_received_words(selection):
    """Construct every possible observed string; reject ambiguous decoding."""
    owners = {}
    for fault in FAULTS:
        true_word = sum(
            (1 << position)
            for position, test in enumerate(selection)
            if fault in TESTS[test - 1]
        )
        for error_count in range(MAX_ERRORS + 1):
            for positions in combinations(range(len(selection)), error_count):
                observed = true_word ^ sum(1 << position for position in positions)
                if observed in owners and owners[observed] != fault:
                    raise AssertionError((selection, observed, owners[observed], fault))
                owners[observed] = fault
    expected = len(FAULTS) * sum(comb(len(selection), i) for i in range(MAX_ERRORS + 1))
    assert len(owners) == expected
    return len(owners)


def verify():
    distance = 2 * MAX_ERRORS + 1
    # One bit per available test, set iff that test distinguishes this pair.
    pair_masks = sorted(
        (
            sum(
                1 << index
                for index, test in enumerate(TESTS)
                if (first in test) != (second in test)
            )
            for first, second in combinations(FAULTS, 2)
        ),
        key=int.bit_count,
    )
    feasible = Counter()
    forbidden_feasible = Counter()
    optimum = len(TESTS) + 1
    forbidden_optimum = len(TESTS) + 1
    optimal_selections = []
    forbidden_selections = []
    visited = 0
    for selection_mask in range(1 << len(TESTS)):
        visited += 1
        if any((selection_mask & pair).bit_count() < distance for pair in pair_masks):
            continue
        size = selection_mask.bit_count()
        feasible[size] += 1
        if size < optimum:
            optimum, optimal_selections = size, []
        if size == optimum:
            optimal_selections.append(selected_tests(selection_mask))
        if not selection_mask & (1 << (FORBIDDEN_TEST - 1)):
            forbidden_feasible[size] += 1
            if size < forbidden_optimum:
                forbidden_optimum, forbidden_selections = size, []
            if size == forbidden_optimum:
                forbidden_selections.append(selected_tests(selection_mask))

    optimal_selections.sort()
    forbidden_selections.sort()
    assert visited == 262144
    assert dict(feasible) == EXPECTED_COUNTS
    assert dict(forbidden_feasible) == EXPECTED_FORBIDDEN_COUNTS
    assert tuple(optimal_selections) == EXPECTED_OPTIMA
    assert optimum == 12 and forbidden_optimum == 13
    mandatory = sorted(set.intersection(*(set(s) for s in optimal_selections)))
    assert mandatory == [2, 3, 5, 8, 9, 10, 11, 12, 13, 15, 17]
    for selection in optimal_selections + forbidden_selections:
        check_received_words(selection)
    counting_bound = ceil(
        comb(len(FAULTS), 2) * distance
        / max(len(test) * (len(FAULTS) - len(test)) for test in TESTS)
    )
    assert counting_bound == 10
    return {
        "selections_checked": visited,
        "simple_pair_counting_lower_bound": counting_bound,
        "minimum_tests": optimum,
        "optimal_selections": optimal_selections,
        "mandatory_tests": mandatory,
        "feasible_selection_counts_by_size": dict(sorted(feasible.items())),
        "when_test_2_is_unavailable": {
            "minimum_tests": forbidden_optimum,
            "optimal_selections": forbidden_selections,
            "feasible_selection_counts_by_size": dict(sorted(forbidden_feasible.items())),
        },
        "direct_received_word_checks": len(optimal_selections) + len(forbidden_selections),
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
