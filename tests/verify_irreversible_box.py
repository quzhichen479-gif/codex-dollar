"""Exact identity-preserving certificate for the irreversible eight-state box.

Standard library only; run ``python tests/verify_irreversible_box.py``.
No files, network resources, or external programs are modified.
"""

from collections import Counter, deque
import unittest


# Each entry is (visible output, next state), indexed by current state - 1.
BUTTONS = {
    "P": ((0, 3), (0, 1), (0, 2), (0, 8), (0, 4), (0, 7), (0, 6), (1, 5)),
    "Q": ((0, 6), (0, 8), (0, 6), (0, 1), (0, 1), (0, 1), (1, 5), (0, 1)),
    "R": ((0, 3), (0, 1), (0, 6), (0, 8), (0, 2), (0, 2), (1, 8), (0, 7)),
}

# Beliefs are ordered tuples of (ORIGINAL identity, current machine state).
# Distinct original identities are never removed by set-deduplicating states.
ROOT = tuple((i, i) for i in range(1, 9))


def branches(belief, button):
    result = {}
    for original, current in belief:
        bit, next_state = BUTTONS[button][current - 1]
        result.setdefault(bit, []).append((original, next_state))
    return {bit: tuple(pairs) for bit, pairs in result.items()}


def identity_collision(belief):
    """Two different originals in the same current state can never separate."""
    return len({current for _, current in belief}) != len(belief)


def safe_branches(belief, button):
    result = branches(belief, button)
    if any(identity_collision(child) for child in result.values()):
        return None
    return result


def reachable_identity_graph(root=ROOT):
    """Enumerate every reachable safe identity mapping, not just state sets."""
    seen = {root}
    queue = deque([root])
    graph = {}
    while queue:
        belief = queue.popleft()
        options = {}
        if len(belief) > 1:
            for button in BUTTONS:
                children = safe_branches(belief, button)
                if children is None:
                    continue
                options[button] = children
                for child in children.values():
                    if child not in seen:
                        seen.add(child)
                        queue.append(child)
        graph[belief] = options
    return graph


def minimum_depths(graph, informative_only=False):
    """Least fixed point of the minimax recurrence, with infinite depth absent.

    Singleton ORIGINAL-identity beliefs terminate.  A depth-d policy exists iff
    an allowed action has every nonempty observation branch solved by depth
    d-1.  Each round uses only solutions from previous rounds.  Colliding actions
    are excluded because at least one original identity would become impossible
    to distinguish under every future deterministic action sequence.
    """
    depths = {belief: 0 for belief in graph if len(belief) == 1}
    optimal = {}
    depth = 0
    while True:
        depth += 1
        newly_solved = {}
        for belief, options in graph.items():
            if belief in depths:
                continue
            good = tuple(
                button for button, children in options.items()
                if (not informative_only or len(children) == 2)
                and all(child in depths for child in children.values())
            )
            if good:
                newly_solved[belief] = depth
                optimal[belief] = good
        if not newly_solved:
            return depths, optimal
        depths.update(newly_solved)


def published_policy():
    """Complete optimal policy; terminal integers are ORIGINAL identities."""
    return ("P", {
        1: 8,
        0: ("R", {
            1: 6,
            0: ("P", {
                1: 5,
                0: ("R", {
                    1: 1,
                    0: ("P", {0: ("R", {
                        1: 3,
                        0: ("P", {0: ("Q", {
                            1: 2,
                            0: ("P", {1: 4, 0: 7}),
                        })}),
                    })}),
                }),
            }),
        }),
    })


def simulate_policy(initial, policy):
    current = initial
    history = []
    while isinstance(policy, tuple):
        button, children = policy
        bit, current = BUTTONS[button][current - 1]
        history.append((button, bit))
        policy = children[bit]
    return policy, tuple(history)


def certificate_summary():
    graph = reachable_identity_graph()
    depths, optimal = minimum_depths(graph)
    informative_depths, _ = minimum_depths(graph, informative_only=True)
    return {
        "reachable_original_to_current_mappings": len(graph),
        "root_minimum_worst_case_depth": depths[ROOT],
        "optimal_first_buttons": optimal[ROOT],
        "solvable_if_every_action_has_two_possible_outputs": ROOT in informative_depths,
        "counts_by_exact_minimum_depth": dict(sorted(Counter(depths.values()).items())),
        "initial_state_policy_traces": {
            i: simulate_policy(i, published_policy()) for i in range(1, 9)
        },
    }


class IrreversibleBoxCertificateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = reachable_identity_graph()
        cls.depths, cls.optimal = minimum_depths(cls.graph)

    def test_root_has_exactly_one_safe_button(self):
        self.assertEqual(tuple(self.graph[ROOT]), ("P",))
        self.assertIsNone(safe_branches(ROOT, "Q"))
        self.assertIsNone(safe_branches(ROOT, "R"))

    def test_irreversible_collision_keeps_both_original_labels(self):
        child = branches(((5, 5), (6, 6)), "R")[0]
        self.assertEqual(child, ((5, 2), (6, 2)))
        self.assertEqual(len(child), 2)
        self.assertTrue(identity_collision(child))

    def test_exact_nine_step_minimax_certificate(self):
        self.assertEqual(len(self.graph), 1383)
        self.assertEqual(len(self.depths), 1383)
        self.assertEqual(self.depths[ROOT], 9)
        self.assertEqual(self.optimal[ROOT], ("P",))
        self.assertEqual(dict(Counter(self.depths.values())), {
            0: 43, 1: 160, 2: 430, 3: 392, 4: 210,
            5: 120, 6: 24, 7: 2, 8: 1, 9: 1,
        })

    def test_all_eight_initial_identities_and_every_policy_branch(self):
        lengths = []
        for initial in range(1, 9):
            reported, history = simulate_policy(initial, published_policy())
            self.assertEqual(reported, initial)
            lengths.append(len(history))
        self.assertEqual(lengths, [4, 8, 6, 9, 3, 2, 9, 1])
        self.assertEqual(max(lengths), self.depths[ROOT])

    def test_forbidding_predictable_outputs_makes_guaranteed_success_impossible(self):
        depths, _ = minimum_depths(self.graph, informative_only=True)
        self.assertNotIn(ROOT, depths)
        self.assertEqual(len(depths), 473)

    def test_two_predictable_steps_on_optimal_longest_branch(self):
        belief = ROOT
        policy = published_policy()
        predictable_steps = []
        step = 0
        while isinstance(policy, tuple):
            step += 1
            button, children = policy
            next_beliefs = safe_branches(belief, button)
            self.assertIsNotNone(next_beliefs)
            if len(next_beliefs) == 1:
                predictable_steps.append(step)
            belief = next_beliefs[0]
            policy = children[0]
        self.assertEqual(predictable_steps, [5, 7])
        self.assertEqual(belief, ((7, 7),))
        self.assertEqual(policy, 7)


if __name__ == "__main__":
    import json

    print(json.dumps(certificate_summary(), ensure_ascii=False, indent=2))
    unittest.main(verbosity=2)
