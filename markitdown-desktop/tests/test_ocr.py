import hashlib
import json
import sys
import tempfile
import unittest.mock as mock
import unittest
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.ocr import (
    OcrComponentError,
    OcrComponentManager,
    OcrEngineClient,
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
            "version": version,
            "url": "https://example.invalid/ocr-engine.zip",
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "size_bytes": archive.stat().st_size,
            "min_app_version": "1.0.0",
            "key_id": "test",
        }
        manifest["signature"] = base64.b64encode(
            self.private_key.sign(canonical_manifest_bytes(manifest))
        ).decode("ascii")
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
            manager = OcrComponentManager(
                root / "components", self.public_keys, health_check=lambda _path: None
            )

            info = manager.install_offline_archive(archive, manifest)

            self.assertTrue(info.installed)
            self.assertEqual("1.0.0", manager.status().version)
            self.assertTrue(manager.status().path.is_file())

    def test_manifest_install_skips_download_when_current_version_is_latest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = self._archive(root, {"ocr-engine.exe": b"engine"})
            manifest = self._manifest(archive, version="1.0.0")
            manager = OcrComponentManager(
                root / "components", self.public_keys, health_check=lambda _path: None
            )
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            manager.install_offline_archive(archive, manifest_path)

            class Response:
                headers = {}

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

                def read(self):
                    return json.dumps(manifest).encode("utf-8")

            with mock.patch("app.ocr.urllib.request.urlopen", return_value=Response()), mock.patch.object(
                manager, "_download", side_effect=AssertionError("latest component was downloaded")
            ):
                info = manager.install_from_manifest_url("https://example.invalid/manifest.json")

            self.assertTrue(info.installed)
            self.assertEqual("1.0.0", info.version)
            self.assertIn("最新版", info.message)

    def test_rejects_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = self._archive(root, {"ocr-engine.exe": b"engine"})
            manager = OcrComponentManager(
                root / "components", self.public_keys, health_check=lambda _path: None
            )
            with self.assertRaises(OcrComponentError):
                manager.install_archive(archive, "1.0.0", "0" * 64)

    def test_rejects_invalid_component_version(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = self._archive(root, {"ocr-engine.exe": b"engine"})
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            manager = OcrComponentManager(
                root / "components", self.public_keys, health_check=lambda _path: None
            )
            with self.assertRaises(OcrComponentError) as raised:
                manager.install_archive(archive, "..", digest)
            self.assertEqual("VERSION_INVALID", raised.exception.code)

    def test_rejects_archive_path_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = self._archive(root, {"../ocr-engine.exe": b"engine"})
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            manager = OcrComponentManager(
                root / "components", self.public_keys, health_check=lambda _path: None
            )
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

    def test_rejects_malformed_ed25519_material(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = self._archive(root, {"ocr-engine.exe": b"engine"})
            manifest = self._manifest(archive)
            with self.assertRaises(OcrComponentError) as raised:
                verify_manifest_signature(manifest, {"test": "not-base64"})
            self.assertEqual("SIGNATURE_INVALID", raised.exception.code)


class OcrProtocolTests(unittest.TestCase):
    def test_protocol_requires_type(self):
        self.assertEqual(
            parse_jsonl_event('{"type":"progress","request_id":"a","current":1}')[
                "type"
            ],
            "progress",
        )
        with self.assertRaises(OcrComponentError):
            parse_jsonl_event('{"current":1}')

    def test_protocol_requires_request_id_for_engine_events(self):
        with self.assertRaisesRegex(OcrComponentError, "request_id") as raised:
            parse_jsonl_event('{"type":"error","code":"INPUT_NOT_FOUND"}')
        self.assertEqual("PROTOCOL_INVALID", raised.exception.code)

    def test_low_text_threshold_helper(self):
        self.assertEqual(count_visible_characters(" 中 文\nA "), 3)

    def test_engine_client_reuses_jsonl_process(self):
        script = """
import json
import sys

count = 0
for line in sys.stdin:
    request = json.loads(line)
    count += 1
    request_id = request.get("request_id", "")
    print(json.dumps({"type": "progress", "request_id": request_id, "current": 1, "total": 1}), flush=True)
    print(json.dumps({"type": "result", "request_id": request_id, "pages": [{"number": 1, "markdown": f"run-{count}"}]}), flush=True)
"""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = root / "fake_engine.py"
            fake.write_text(script, encoding="utf-8")
            client = OcrEngineClient(
                fake,
                launcher=[sys.executable, str(fake)],
                timeout_seconds=10,
            )
            try:
                first = client.recognise("first.png", "image", request_id="first")
                second = client.recognise("second.png", "image", request_id="second")
            finally:
                client.close()
            self.assertEqual("run-1", first["pages"][0]["markdown"])
            self.assertEqual("run-2", second["pages"][0]["markdown"])


if __name__ == "__main__":
    unittest.main()
