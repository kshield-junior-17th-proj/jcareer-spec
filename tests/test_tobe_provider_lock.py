from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_tobe_provider_lock.py"
SPEC = importlib.util.spec_from_file_location("check_tobe_provider_lock", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TobeProviderLockSelection(unittest.TestCase):
    def test_exact_checked_provider_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / ".terraform.lock.hcl"
            lock.write_text(
                'provider "registry.terraform.io/hashicorp/aws" {\n'
                '  version = "6.59.0"\n'
                '  hashes = ["h1:synthetic-checksum"]\n'
                '}\n',
                encoding="utf-8",
            )
            self.assertEqual(MODULE.validate_lock(lock), [])

    def test_drifted_provider_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / ".terraform.lock.hcl"
            lock.write_text(
                'provider "registry.terraform.io/hashicorp/aws" {\n'
                '  version = "6.60.0"\n'
                '  hashes = ["h1:synthetic-checksum"]\n'
                '}\n',
                encoding="utf-8",
            )
            self.assertTrue(MODULE.validate_lock(lock))


if __name__ == "__main__":
    unittest.main()
