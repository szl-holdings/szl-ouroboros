# SPDX-License-Identifier: Apache-2.0
"""Untrusted source receipts must not admit non-finite JSON numbers."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.run_open_frontier_review import OpenReviewerError, read_json_object


class StrictSourceReceiptNumbersTests(unittest.TestCase):
    def _load(self, raw: str):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic_public_source.json"
            path.write_text(raw, encoding="utf-8")
            return read_json_object(path, label="source receipt")

    def test_nonfinite_source_receipt_numbers_rejected_without_value_echo(self):
        for literal in ("NaN", "Infinity", "-Infinity", "1e400", "-1e400"):
            with self.subTest(literal=literal):
                raw = '{"metadata":{"unknown":' + literal + '}}'
                with self.assertRaisesRegex(OpenReviewerError, "non-finite") as ctx:
                    self._load(raw)
                self.assertNotIn(literal, str(ctx.exception))

    def test_finite_source_receipt_numbers_remain_readable(self):
        self.assertEqual(
            self._load('{"metadata":{"rate":1.5,"count":42,"neg":-3}}'),
            {"metadata": {"rate": 1.5, "count": 42, "neg": -3}},
        )


if __name__ == "__main__":
    unittest.main()
