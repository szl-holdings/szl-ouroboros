# SPDX-License-Identifier: Apache-2.0
"""Fail-closed admission when untrusted model text contains lone surrogates."""
import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.run_open_frontier_review import (
    OpenReviewerError,
    admit_or_block_model_output,
    blocked_review,
    parse_single_json_object,
    write_execution_receipt,
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


    def test_literal_invalid_unicode_still_writes_honest_blocked_receipt(self):
        for point in (0xD800, 0xDFFF):
            with self.subTest(point=hex(point)):
                raw = '{"summary":"' + chr(point) + '"}'
                review, admitted, state, failure = admit_or_block_model_output(
                    raw, candidate_digest="d" * 64, selected_candidate_ids=[]
                )
                self.assertFalse(admitted)
                self.assertEqual(failure, "OUTPUT_INVALID_UNICODE")
                with TemporaryDirectory() as folder:
                    output_path = Path(folder) / "blocked.json"
                    receipt = write_execution_receipt(
                        output_path=output_path,
                        source={"source_revision": "a" * 40,
                                "candidate_set_sha256": "d" * 64,
                                "candidate_count": 0},
                        selected_ids=[],
                        messages=[{"role": "user", "content": "public synthetic fixture"}],
                        raw_output=raw,
                        review=review,
                        provider_metadata={"provider": "synthetic", "model": "none"},
                        model_output_admitted=admitted,
                        admission_state=state,
                        failure_code=failure,
                    )
                    self.assertEqual(
                        json.loads(output_path.read_text(encoding="utf-8")), receipt
                    )
                self.assertEqual(receipt["state"], "OPEN_WEIGHT_REVIEW_BLOCKED_FAIL_CLOSED")
                self.assertIsNone(receipt["raw_output_sha256"])
                self.assertEqual(receipt["raw_output_hash_state"], "UNAVAILABLE_INVALID_UNICODE")
                self.assertEqual(len(receipt["receipt_sha256"]), 64)
                self.assertTrue(all(v == "NONE" for v in receipt["authority"].values()))

    def test_escaped_invalid_unicode_preserves_valid_raw_text_hash(self):
        payload = blocked_review("d" * 64)
        payload["summary"] = chr(0xD800)
        raw = json.dumps(payload, ensure_ascii=True)
        review, admitted, state, failure = admit_or_block_model_output(
            raw, candidate_digest="d" * 64, selected_candidate_ids=[]
        )
        self.assertFalse(admitted)
        self.assertEqual(failure, "OUTPUT_INVALID_UNICODE")
        with TemporaryDirectory() as folder:
            receipt = write_execution_receipt(
                output_path=Path(folder) / "blocked.json",
                source={"source_revision": "a" * 40,
                        "candidate_set_sha256": "d" * 64, "candidate_count": 0},
                selected_ids=[], messages=[],
                raw_output=raw, review=review,
                provider_metadata={"provider": "synthetic", "model": "none"},
                model_output_admitted=admitted,
                admission_state=state,
                failure_code=failure,
            )
        self.assertEqual(
            receipt["raw_output_sha256"],
            hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        )
        self.assertNotIn("raw_output_hash_state", receipt)

    def test_invalid_unicode_cannot_write_an_admitted_receipt(self):
        raw = '{"summary":"' + chr(0xD800) + '"}'
        with TemporaryDirectory() as folder:
            with self.assertRaisesRegex(OpenReviewerError, "requires blocked admission"):
                write_execution_receipt(
                    output_path=Path(folder) / "not_admitted.json",
                    source={"source_revision": "a" * 40,
                            "candidate_set_sha256": "d" * 64, "candidate_count": 0},
                    selected_ids=[], messages=[], raw_output=raw,
                    review=blocked_review("d" * 64),
                    provider_metadata={"provider": "synthetic", "model": "none"},
                    model_output_admitted=True,
                    admission_state="MODEL_OUTPUT_ADMITTED",
                    failure_code=None,
                )

if __name__ == "__main__":
    unittest.main()
