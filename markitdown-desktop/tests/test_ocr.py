import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.ocr import (
    OcrComponentError,
    OcrComponentManager,
    canonical_manifest_bytes,
    count_visible_characters,
    parse_jsonl_event,
    verify_manifest_signature,
)


class OcrComponentManagerTests(unittest.TestCase):
    def setUp(self):
        self.private_key = Ed25519PrivateKey.generate()
        public = self.private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        import base64
        self.public_keys = {"test": base64.b64encode(public).decode("ascii")}

    def _manifest(self, archive: Path, version="1.0.0"):
        import base64
        manifest = {
            "version": version, "url": "https://example.invalid/ocr-engine.zip",
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "size_bytes": archive.stat().st_size, "min_app_version": "1.0.0", "key_id": "test",
        }
        manifest["signature"] = base64.b64encode(self.private_key.sign(canonical_manifest_bytes(manifest))).decode("ascii")
        return manifest
    def _archive(self, directory: Path, entries: dict[str, bytes]) -> Path:
        archive = directory / "ocr-engine.zip"
        with zipfile.ZipFile(archive, "w") as package:
            for name, content in entries.items():
                package.writestr(name, content)
        return archive

    def test_installs_verified_offline_component(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = self._archive(root, {"ocr-engine.exe": b"engine"})
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps(self._manifest(archive)), encoding="utf-8")
            manager = OcrComponentManager(root / "components", self.public_keys, health_check=lambda _path: None)

            info = manager.install_offline_archive(archive, manifest)

            self.assertTrue(info.installed)
            self.assertEqual("1.0.0", manager.status().version)
            self.assertTrue(manager.status().path.is_file())

    def test_rejects_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = self._archive(root, {"ocr-engine.exe": b"engine"})
            manager = OcrComponentManager(root / "components", self.public_keys, health_check=lambda _path: None)
            with self.assertRaises(OcrComponentError):
                manager.install_archive(archive, "1.0.0", "0" * 64)

    def test_rejects_archive_path_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = self._archive(root, {"../ocr-engine.exe": b"engine"})
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            manager = OcrComponentManager(root / "components", self.public_keys, health_check=lambda _path: None)
            with self.assertRaises(OcrComponentError):
                manager.install_archive(archive, "1.0.0", digest)

    def test_rejects_unsigned_or_tampered_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = self._archive(root, {"ocr-engine.exe": b"engine"})
            manifest = self._manifest(archive)
            manifest["version"] = "2.0.0"
            with self.assertRaises(OcrComponentError):
                verify_manifest_signature(manifest, self.public_keys)


class OcrProtocolTests(unittest.TestCase):
    def test_protocol_requires_type(self):
        self.assertEqual(parse_jsonl_event('{"type":"progress","request_id":"a","current":1}')["type"], "progress")
        with self.assertRaises(OcrComponentError):
            parse_jsonl_event('{"current":1}')

    def test_protocol_requires_request_id_for_engine_events(self):
        with self.assertRaisesRegex(OcrComponentError, "request_id") as raised:
            parse_jsonl_event('{"type":"error","code":"INPUT_NOT_FOUND"}')
        self.assertEqual("PROTOCOL_INVALID", raised.exception.code)

    def test_low_text_threshold_helper(self):
        self.assertEqual(count_visible_characters(" 中 文\nA "), 3)


if __name__ == "__main__":
    unittest.main()
