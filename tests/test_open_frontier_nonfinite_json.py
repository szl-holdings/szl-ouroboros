# SPDX-License-Identifier: Apache-2.0
"""Strict JSON-number admission controls for untrusted open reviewer output."""
import unittest

from scripts.run_open_frontier_review import (
    OpenReviewerError,
    admit_or_block_model_output,
    parse_single_json_object,
)


class NonFiniteReviewerJsonTests(unittest.TestCase):
    def test_nonfinite_numeric_tokens_fail_closed_without_model_echo(self):
        for token in ("NaN", "Infinity", "-Infinity", "1e400", "-1e400"):
            with self.subTest(token=token):
                raw = '{"field":{"nested":' + token + '}}'
                with self.assertRaisesRegex(OpenReviewerError, "non-finite number"):
                    parse_single_json_object(raw)
                review, admitted, admission, failure = admit_or_block_model_output(
                    raw, candidate_digest="d" * 64, selected_candidate_ids=[]
                )
                self.assertFalse(admitted)
                self.assertEqual(admission, "MODEL_OUTPUT_REJECTED_FAIL_CLOSED")
                self.assertEqual(failure, "OUTPUT_NONFINITE_JSON_NUMBER")
                self.assertEqual(review["state"], "BLOCKED")
                self.assertEqual(review["recommendations"], [])
                self.assertTrue(all(v == "NONE" for v in review["authority"].values()))

    def test_oversized_json_integer_is_blocked_not_uncaught(self):
        # A model can emit a syntactically valid integer beyond Python's
        # conversion limit. The admission boundary must not leak ValueError.
        raw = '{"field":{"nested":' + ("9" * 5000) + '}}'
        with self.assertRaisesRegex(OpenReviewerError, "integer digit ceiling"):
            parse_single_json_object(raw)
        review, admitted, admission, failure = admit_or_block_model_output(
            raw, candidate_digest="d" * 64, selected_candidate_ids=[]
        )
        self.assertFalse(admitted)
        self.assertEqual(admission, "MODEL_OUTPUT_REJECTED_FAIL_CLOSED")
        self.assertEqual(failure, "OUTPUT_JSON_INTEGER_TOO_LONG")
        self.assertEqual(review["state"], "BLOCKED")
        self.assertEqual(review["recommendations"], [])
        self.assertTrue(all(v == "NONE" for v in review["authority"].values()))

    def test_normal_json_integer_still_parses(self):
        self.assertEqual(parse_single_json_object('{"a":{"b":42}}'), {"a": {"b": 42}})

    def test_finite_json_number_still_parses(self):
        self.assertEqual(parse_single_json_object('{"x":{"y":1.5}}'), {"x": {"y": 1.5}})

    def test_duplicate_key_rejection_still_holds(self):
        with self.assertRaisesRegex(OpenReviewerError, "duplicate object member"):
            parse_single_json_object('{"a": 1, "a": 2}')


if __name__ == "__main__":
    unittest.main()
