import base64
import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "ocr_manifest_validator", ROOT / "ocr-engine" / "validate_manifest.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReleaseManifestTests(unittest.TestCase):
    def test_valid_manifest_matches_archive_and_signature(self):
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "ocr-engine.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("ocr-engine.exe", b"engine")
            manifest = {
                "version": "1.0.0",
                "url": "https://github.com/example/release/ocr-engine.zip",
                "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                "size_bytes": archive.stat().st_size,
                "min_app_version": "1.2.2",
                "key_id": "test",
            }
            manifest["signature"] = base64.b64encode(
                private.sign(MODULE.canonical_manifest_bytes(manifest))
            ).decode("ascii")
            MODULE.validate_manifest(
                manifest,
                archive,
                {"test": base64.b64encode(public).decode("ascii")},
                require_release_url=True,
            )

    def test_placeholder_release_url_is_rejected(self):
        manifest = {
            "version": "1.0.0",
            "url": "https://example.invalid/ocr-engine.zip",
            "sha256": "0" * 64,
            "size_bytes": 1,
            "min_app_version": "1.2.2",
            "key_id": "test",
            "signature": base64.b64encode(b"x" * 64).decode("ascii"),
        }
        with self.assertRaises(ValueError):
            MODULE.validate_manifest(manifest, require_release_url=True)


if __name__ == "__main__":
    unittest.main()
