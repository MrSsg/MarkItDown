# SPDX-License-Identifier: MIT
"""Create a signed OCR component manifest from a release-only private key."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical_manifest_bytes(manifest: dict) -> bytes:
    return json.dumps(
        {key: value for key, value in manifest.items() if key != "signature"},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--version", default="1.1.0")
    parser.add_argument("--min-app-version", default="1.2.0")
    parser.add_argument("--key-id", default="markitdown-ocr-v1")
    parser.add_argument("--private-key", required=True, help="base64-encoded 32-byte Ed25519 private key")
    args = parser.parse_args()
    archive = Path(args.archive)
    manifest = {
        "version": args.version,
        "url": args.url,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "size_bytes": archive.stat().st_size,
        "min_app_version": args.min_app_version,
        "key_id": args.key_id,
    }
    private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(args.private_key))
    manifest["signature"] = base64.b64encode(private_key.sign(canonical_manifest_bytes(manifest))).decode("ascii")
    Path(args.output).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
