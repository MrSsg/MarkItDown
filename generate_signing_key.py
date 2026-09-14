"""Generate an Ed25519 release key pair without writing the private key to disk."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-key-output", required=True)
    parser.add_argument("--key-id", default="markitdown-ocr-v1")
    args = parser.parse_args()

    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    Path(args.public_key_output).write_text(
        json.dumps({args.key_id: base64.b64encode(public_bytes).decode("ascii")}, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Store this value only in the MARKITDOWN_OCR_SIGNING_KEY GitHub Actions Secret:")
    print(base64.b64encode(private_bytes).decode("ascii"))


if __name__ == "__main__":
    main()
