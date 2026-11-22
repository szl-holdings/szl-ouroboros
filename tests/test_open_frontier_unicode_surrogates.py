# SPDX-License-Identifier: Apache-2.0
"""Fail-closed admission when untrusted model text contains lone surrogates."""
import json
import unittest

from scripts.run_open_frontier_review import (
    OpenReviewerError,
    admit_or_block_model_output,
    blocked_review,
    parse_single_json_object,
)


class ModelUnicodeAdmissionTests(unittest.TestCase):
    def test_literal_lone_surrogates_are_sanitized_and_blocked(self):
        for point in (0xD800, 0xDFFF):
            with self.subTest(point=hex(point)):
                raw = '{"summary":"' + chr(point) + '"}'
                with self.assertRaisesRegex(OpenReviewerError, "invalid Unicode"):
                    parse_single_json_object(raw)
                review, admitted, state, reason = admit_or_block_model_output(
                    raw, candidate_digest="d" * 64, selected_candidate_ids=[]
                )
                self.assertEqual(
                    (admitted, state, reason),
                    (False, "MODEL_OUTPUT_REJECTED_FAIL_CLOSED", "OUTPUT_INVALID_UNICODE"),
                )
                self.assertEqual(review["state"], "BLOCKED")
                self.assertEqual(review["recommendations"], [])
                self.assertTrue(all(v == "NONE" for v in review["authority"].values()))

    def test_escaped_lone_surrogate_inside_summary_is_blocked(self):
        payload = blocked_review("d" * 64)
        payload["summary"] = chr(0xD800)
        raw = json.dumps(payload, ensure_ascii=True)
        review, admitted, state, reason = admit_or_block_model_output(
            raw, candidate_digest="d" * 64, selected_candidate_ids=[]
        )
        self.assertEqual(
            (admitted, state, reason),
            (False, "MODEL_OUTPUT_REJECTED_FAIL_CLOSED", "OUTPUT_INVALID_UNICODE"),
        )
        self.assertEqual(review["state"], "BLOCKED")
        self.assertTrue(all(v == "NONE" for v in review["authority"].values()))

    def test_valid_utf8_unicode_and_ascii_still_parse(self):
        self.assertEqual(
            parse_single_json_object('{"summary":"☕ verified"}')["summary"], "☕ verified"
        )
        self.assertEqual(parse_single_json_object('{"summary":"safe"}')["summary"], "safe")


if __name__ == "__main__":
    unittest.main()
