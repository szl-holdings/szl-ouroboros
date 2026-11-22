# SPDX-License-Identifier: Apache-2.0
"""Independent source-receipt JSON member ambiguity controls."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.run_open_frontier_review import OpenReviewerError, read_json_object


class SourceReceiptJsonTests(unittest.TestCase):
    def _load(self, literal: str):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic_public_receipt.json"
            path.write_text(literal, encoding="utf-8")
            return read_json_object(path, label="source receipt")

    def test_duplicate_top_level_member_is_rejected_before_receipt_validation(self):
        # Even identical values must not be silently resolved as last-wins.
        with self.assertRaises(OpenReviewerError):
            self._load('{"source_revision":"a","source_revision":"a"}')

    def test_duplicate_nested_member_is_rejected_without_key_echo(self):
        with self.assertRaises(OpenReviewerError) as caught:
            self._load('{"metadata":{"role":"deny","role":"allow"}}')
        self.assertNotIn("allow", str(caught.exception))
        self.assertNotIn("role", str(caught.exception))

    def test_distinct_nested_members_remain_readable(self):
        self.assertEqual(
            self._load('{"source_revision":"a","metadata":{"role":"deny"}}'),
            {"source_revision":"a","metadata":{"role":"deny"}},
        )


if __name__ == "__main__":
    unittest.main()
