"""Independent, CPU-only finite-model certificates for two reasoning puzzles.

Run directly with ``python tests/verify_epistemic.py``.  Uses only the standard
library, performs no network access, and writes no artifacts.
"""

from itertools import combinations
import unittest


# Tuple position denotes the private observation of A, B, and C respectively.
CARD_ROWS = (
    (1, 3, 7), (1, 4, 3), (1, 6, 1), (1, 6, 2), (1, 6, 3),
    (2, 3, 2), (2, 3, 5), (2, 6, 3), (3, 2, 6), (3, 6, 7),
    (4, 1, 4), (4, 2, 6), (4, 3, 6), (4, 5, 6), (4, 7, 1),
    (5, 3, 7), (5, 5, 2), (5, 7, 4), (6, 3, 4), (6, 6, 5),
    (6, 7, 4), (7, 1, 6), (7, 7, 4), (7, 7, 6),
)

EXPECTED_CARD_TRACE = (
    (6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24),
    (6, 7, 9, 11, 12, 13, 14, 16, 17, 19, 22),
    (6, 9, 11, 12, 13, 14, 17, 19, 22),
    (6, 9, 17, 19, 22),
    (9, 17, 22),
    (17,),
)


def possibilities(worlds, person, card):
    """Worlds compatible with one person's private coordinate and public past."""
    value = CARD_ROWS[card - 1][person]
    return {w for w in worlds if CARD_ROWS[w - 1][person] == value}


def unknown_worlds(worlds, person):
    return {w for w in worlds if len(possibilities(worlds, person, w)) > 1}


def knows_event(worlds, person, event):
    """Universal knowledge, rather than truth at the actual card only."""
    return {w for w in worlds if possibilities(worlds, person, w) <= event}


def epistemic_trace():
    worlds = set(range(1, len(CARD_ROWS) + 1))
    trace = []
    for speaker, other in ((0, 1), (1, 2)):
        # Both conjuncts are evaluated before this entire public announcement.
        own_ignorance = unknown_worlds(worlds, speaker)
        others_ignorance = unknown_worlds(worlds, other)
        worlds = own_ignorance & knows_event(worlds, speaker, others_ignorance)
        trace.append(tuple(sorted(worlds)))
    worlds = unknown_worlds(worlds, 2)
    trace.append(tuple(sorted(worlds)))
    for speaker in (0, 1, 2):
        worlds = worlds - unknown_worlds(worlds, speaker)
        trace.append(tuple(sorted(worlds)))
    return tuple(trace)


# Entries: (visible output bit, successor state), indexed by current state - 1.
BUTTONS = {
    "P": ((1, 8), (0, 6), (0, 3), (0, 4), (0, 7), (0, 1), (1, 2), (0, 5)),
    "Q": ((1, 2), (0, 7), (0, 8), (0, 6), (0, 3), (0, 5), (0, 1), (0, 4)),
    "R": ((0, 1), (0, 8), (0, 6), (0, 7), (0, 4), (0, 3), (0, 5), (1, 2)),
}


def successors(states, button):
    """Both possible next belief states, omitting impossible output branches."""
    table = BUTTONS[button]
    return {
        bit: frozenset(table[s - 1][1] for s in states if table[s - 1][0] == bit)
        for bit in (0, 1)
        if any(table[s - 1][0] == bit for s in states)
    }


def minimum_diagnostic_depths():
    """Exact minimax depths for all 255 nonempty current-state subsets.

    Each button's transition is a permutation.  Thus along any known action /
    output history, current-state labels correspond bijectively to the still
    possible original labels.  The finite belief-state dynamic program is
    therefore sufficient even though the question asks for the original state.
    New depth-d solutions can use only depth-(d-1) or shallower child solutions.
    """
    universe = tuple(range(1, 9))
    statesets = tuple(
        frozenset(c)
        for size in range(1, len(universe) + 1)
        for c in combinations(universe, size)
    )
    depths = {s: 0 for s in statesets if len(s) == 1}
    optimal_buttons = {}
    depth = 0
    while True:
        depth += 1
        newly_solved = {}
        for states in statesets:
            if states in depths:
                continue
            feasible = tuple(
                button for button in BUTTONS
                if all(child in depths for child in successors(states, button).values())
            )
            if feasible:
                newly_solved[states] = depth
                optimal_buttons[states] = feasible
        if not newly_solved:
            break
        depths.update(newly_solved)
    return depths, optimal_buttons


def published_policy():
    """A complete policy tree: (button, {bit: subtree or initial-state label})."""
    return ("P", {
        1: ("R", {1: 1, 0: 7}),
        0: ("P", {
            1: ("R", {1: 6, 0: 5}),
            0: ("P", {
                1: ("R", {1: 2, 0: 8}),
                0: ("Q", {0: ("R", {1: 3, 0: 4})}),
            }),
        }),
    })


def simulate_policy(initial, policy):
    state = initial
    history = []
    while isinstance(policy, tuple):
        button, children = policy
        bit, state = BUTTONS[button][state - 1]
        history.append((button, bit))
        policy = children[bit]
    return policy, tuple(history)


class FiniteReasoningCertificateTests(unittest.TestCase):
    def test_all_public_announcement_stages(self):
        self.assertEqual(epistemic_trace(), EXPECTED_CARD_TRACE)
        self.assertEqual(CARD_ROWS[16], (5, 5, 2))

    def test_nested_knowledge_is_stronger_than_actual_ignorance(self):
        worlds = set(range(1, 25))
        actual_ignorance = unknown_worlds(worlds, 1)
        self.assertTrue({1, 3, 4, 5} <= actual_ignorance)
        self.assertFalse({1, 3, 4, 5} & knows_event(worlds, 0, actual_ignorance))

    def test_transitions_preserve_original_identity(self):
        for table in BUTTONS.values():
            self.assertEqual(sorted(nxt for _, nxt in table), list(range(1, 9)))

    def test_exact_diagnostic_optimum_and_all_first_buttons(self):
        depths, buttons = minimum_diagnostic_depths()
        root = frozenset(range(1, 9))
        self.assertEqual(len(depths), 255)
        self.assertEqual(depths[root], 5)
        self.assertEqual(buttons[root], ("P",))
        costs = {
            button: 1 + max(depths[s] for s in successors(root, button).values())
            for button in BUTTONS
        }
        self.assertEqual(costs, {"P": 5, "Q": 6, "R": 6})

    def test_every_policy_leaf_reports_correct_original_state(self):
        lengths = []
        for initial in range(1, 9):
            reported, history = simulate_policy(initial, published_policy())
            self.assertEqual(reported, initial)
            lengths.append(len(history))
        self.assertEqual(lengths, [2, 4, 5, 5, 3, 3, 2, 4])

    def test_human_lower_bound_certificate(self):
        depths, _ = minimum_diagnostic_depths()
        expected = {
            (3, 4): 2,
            (1, 3, 4, 7): 3,
            (1, 3, 4, 5, 6, 7): 4,
            (3, 4, 7): 3,
            (1, 3, 6, 8): 3,
            (1, 3, 4, 5, 7): 4,
            (1, 3, 4, 5, 6, 8): 4,
            (1, 3, 4, 5, 6, 7, 8): 5,
        }
        for states, depth in expected.items():
            self.assertEqual(depths[frozenset(states)], depth, states)


if __name__ == "__main__":
    unittest.main(verbosity=2)
