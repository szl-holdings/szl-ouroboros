#!/usr/bin/env python3
"""Keep the packaged metadata mirrors and bounded DOI observation aligned."""
from __future__ import annotations

import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE_METADATA = ROOT / "torch-ext" / "szl_ouroboros" / "metadata.json"
BUILD_METADATA = ROOT / "build" / "torch-universal" / "szl_ouroboros" / "metadata.json"

EXPECTED_DOI_PROVENANCE = {
    "lean_repo": "szl-holdings/lutar-lean",
    "doi_lutar_lean": "10.5281/zenodo.20434308",
    "doi_lutar_lean_record_status": "SUPERSEDED",
    "doi_lutar_lean_concept": "10.5281/zenodo.20434307",
    "doi_lutar_lean_concept_head_observed": "10.5281/zenodo.20517840",
    "doi_lutar_lean_concept_head_version_observed": "v18.0.0-errata",
    "doi_lutar_lean_concept_head_observed_at": "2026-08-30",
}


def _load(path: pathlib.Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


class MetadataProvenance(unittest.TestCase):
    def test_source_and_build_metadata_are_identical(self) -> None:
        self.assertEqual(_load(SOURCE_METADATA), _load(BUILD_METADATA))

    def test_lean_doi_observation_is_bounded_and_explicit(self) -> None:
        provenance = _load(SOURCE_METADATA)["provenance"]
        self.assertEqual(provenance, EXPECTED_DOI_PROVENANCE)
        self.assertNotEqual(
            provenance["doi_lutar_lean"],
            provenance["doi_lutar_lean_concept_head_observed"],
        )


if __name__ == "__main__":
    unittest.main()
