"""Validate a signed OCR release manifest and its archive."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


REQUIRED_FIELDS = (
    "version",
    "url",
    "sha256",
    "size_bytes",
    "min_app_version",
    "key_id",
    "signature",
)


def canonical_manifest_bytes(manifest: dict) -> bytes:
    payload = {key: value for key, value in manifest.items() if key != "signature"}
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _decode_base64(value: object, label: str) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} 为空")
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{label} 不是有效 Base64") from exc


def validate_manifest(
    manifest: dict,
    archive: Path | None = None,
    public_keys: dict[str, str] | None = None,
    require_release_url: bool = False,
) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in manifest]
    if missing:
        raise ValueError(f"清单缺少字段: {', '.join(missing)}")
    if not all(
        isinstance(manifest[field], str) and manifest[field]
        for field in REQUIRED_FIELDS
        if field != "size_bytes"
    ):
        raise ValueError("清单字符串字段无效")
    size = manifest["size_bytes"]
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError("size_bytes 无效")
    expected_sha256 = manifest["sha256"]
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(char not in "0123456789abcdefABCDEF" for char in expected_sha256)
    ):
        raise ValueError("sha256 无效")

    parsed = urlparse(str(manifest["url"]))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("清单 URL 必须是 HTTP(S) 地址")
    if require_release_url and parsed.hostname in {"example.invalid", "localhost"}:
        raise ValueError("正式清单不能使用占位 URL")

    signature = _decode_base64(manifest["signature"], "signature")
    if len(signature) != 64:
        raise ValueError("Ed25519 签名长度错误")

    if public_keys is not None:
        key_id = str(manifest["key_id"])
        encoded_key = public_keys.get(key_id)
        public_key = _decode_base64(encoded_key, f"公钥 {key_id}")
        if len(public_key) != 32:
            raise ValueError("Ed25519 公钥长度错误")
        try:
            Ed25519PublicKey.from_public_bytes(public_key).verify(
                signature, canonical_manifest_bytes(manifest)
            )
        except InvalidSignature as exc:
            raise ValueError("清单签名校验失败") from exc

    if archive is not None:
        if not archive.is_file():
            raise ValueError(f"找不到 OCR 归档: {archive}")
        if archive.stat().st_size != size:
            raise ValueError("清单 size_bytes 与归档不一致")
        digest = hashlib.sha256()
        with archive.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        digest_actual = digest.hexdigest()
        if digest_actual.lower() != expected_sha256.lower():
            raise ValueError("清单 sha256 与归档不一致")


def _load_public_keys(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("公钥文件必须是 JSON 对象")
    return {str(key): str(value) for key, value in data.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--public-key-file", type=Path)
    parser.add_argument("--require-release-url", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("清单必须是 JSON 对象")
    public_keys = (
        _load_public_keys(args.public_key_file) if args.public_key_file else None
    )
    validate_manifest(
        manifest,
        args.archive,
        public_keys,
        require_release_url=args.require_release_url,
    )
    print(f"OK: {manifest['version']} {manifest['key_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
