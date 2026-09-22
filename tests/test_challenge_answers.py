"""Bind the published question bank to independently checked answer certificates."""

import json
from fractions import Fraction
from pathlib import Path
import unittest

from verify_epistemic import (
    CARD_ROWS,
    EXPECTED_CARD_TRACE,
    FiniteReasoningCertificateTests,
)
from verify_lie_game import verify as verify_lie_game
from verify_fixed_queries import verify as verify_fixed_queries, QUERIES
from verify_irreversible_box import BUTTONS, IrreversibleBoxCertificateTests
from verify_sensor_selection import TESTS, verify as verify_sensor_selection
from verify_probability import exact_solution, check_by_literal_history


def question_bank():
    source = (Path(__file__).resolve().parents[1] / "src/codex_meter/static/benchmarks.js").read_text(encoding="utf-8")
    rows, _ = json.JSONDecoder().raw_decode(source.split("const questions = ", 1)[1])
    return {row["id"]: row for row in rows}


class PublishedChallengeTests(unittest.TestCase):
    def test_fixed_query_construction_corrects_all_three_error_patterns(self):
        self.assertEqual(verify_fixed_queries(), (6273, 7))
        question = question_bank()["fixed-three-lies"]
        self.assertIn("最少16问", question["reference"])
        self.assertIn("至多说3次假话", question["prompt"])
        self.assertIn("|S_i|≤3", question["prompt"])
        for query in QUERIES:
            self.assertIn("".join(map(str, query)), question["reference"])

    def test_published_card_table_and_intermediate_answers_match_certificate(self):
        question = question_bank()["public-knowledge"]
        for i, (x, y, z) in enumerate(CARD_ROWS, 1):
            self.assertIn(f"{i:02d}:{x},{y},{z}", question["prompt"])
        for i, states in enumerate(EXPECTED_CARD_TRACE, 1):
            self.assertIn(f"S{i}=" + ",".join(f"{n:02d}" for n in states), question["reference"])

    def test_published_black_box_table_matches_verified_dynamics(self):
        question = question_bank()["irreversible-black-box"]
        for i in range(1, 9):
            row = str(i) + "|" + "|".join(f"{BUTTONS[b][i-1][0]}/{BUTTONS[b][i-1][1]}" for b in "PQR")
            self.assertIn(row, question["prompt"])
        self.assertIn("最小最坏次数9", question["reference"])

    def test_sensor_selection_optima_and_counterfactual(self):
        result = verify_sensor_selection()
        self.assertEqual(result["minimum_tests"], 12)
        self.assertEqual(result["when_test_2_is_unavailable"]["minimum_tests"], 13)
        question = question_bank()["fault-test-selection"]
        for i, group in enumerate(TESTS, 1):
            self.assertIn(f"T{i}={{" + ",".join(map(str, group)) + "}", question["prompt"])
        for optimum in result["optimal_selections"]:
            self.assertIn("{" + ",".join(map(str, optimum)) + "}", question["reference"])

    def test_two_lies_strategy_handles_every_legal_error_schedule(self):
        self.assertEqual(verify_lie_game(), (504, 10))
        question = question_bank()["bounded-two-lies"]
        self.assertIn("至多说两次假话", question["prompt"])
        self.assertIn("|S|≤3", question["prompt"])
        self.assertIn("最少10次", question["reference"])

    def test_probability_reference_has_exact_conditional_answers(self):
        probability, weighted_time, expected_time, answers = exact_solution()
        expected = {
            "P(W)": Fraction(154365, 320138),
            "P(initial A | W)": Fraction(259297, 463095),
            "E[N | W]": Fraction(20815361171, 3529864455),
            "E[N]": Fraction(1006983, 160069),
        }
        self.assertEqual(answers, expected)
        self.assertLess(check_by_literal_history(probability, weighted_time, expected_time), 1e-12)
        question = question_bank()["hidden-coin"]
        for label in ("P(W)", "P(initial A | W)", "E[N | W]"):
            self.assertIn(str(expected[label]), question["reference"])
        for condition in ("A每次正面H的概率为2/3", "B为1/3", "以1/4的概率换", "以3/4的概率保留"):
            self.assertIn(condition, question["prompt"])


if __name__ == "__main__":
    unittest.main()
