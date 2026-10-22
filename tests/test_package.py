"""Packaging tests: the stage map ships as package data (a non-editable wheel keeps it)."""

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


class PackageDataTest(unittest.TestCase):
    def test_stages_json_is_package_data(self) -> None:
        data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        package_data = data["tool"]["setuptools"]["package-data"]
        self.assertIn("stages.json", package_data["verdandi.odin3"])


if __name__ == "__main__":
    unittest.main()
