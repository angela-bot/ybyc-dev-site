#!/usr/bin/env python3
"""Upload the contents of a direcotry to a Cloudflare R2 bucket

Examples:
  python3 scripts/upload_r2.py ybyc-originals regattas images/

Required in .env.local (R2 S3 API credentials):
  R2_ACCESS_KEY_ID=...
  R2_SECRET_ACCESS_KEY=...

Also set either:
  R2_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com
or:
  CLOUDFLARE_ACCOUNT_ID=<account-id>

AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY and CLOUDFLARE_R2_ENDPOINT are
accepted as alternate names. A CLOUDFLARE_API_TOKEN alone cannot upload R2
objects through the S3 API.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import mimetypes
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_env_file(path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE entries without printing any secret values."""
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        if not separator or not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def setting(values: dict[str, str], *names: str) -> str | None:
    for name in names:
        if os.environ.get(name):
            return os.environ[name]
        if values.get(name):
            return values[name]
    return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def signing_key(secret: str, date_stamp: str) -> bytes:
    key = sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    key = sign(key, "auto")
    key = sign(key, "s3")
    return sign(key, "aws4_request")


def upload(source: Path, bucket: str, object_key: str, content_type: str, cache_control: str | None, config: dict[str, str]) -> None:
    access_key = setting(config, "R2_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID")
    secret_key = setting(config, "R2_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY")
    endpoint = setting(config, "R2_ENDPOINT", "CLOUDFLARE_R2_ENDPOINT")
    account_id = setting(config, "CLOUDFLARE_ACCOUNT_ID")

    if not endpoint and account_id:
        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    if not access_key or not secret_key or not endpoint:
        raise ValueError(
            "Missing R2 S3 credentials. Set R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, "
            "and R2_ENDPOINT (or CLOUDFLARE_ACCOUNT_ID) in .env.local."
        )
    if not endpoint.startswith(("http://", "https://")):
        raise ValueError("R2_ENDPOINT must include https://")
    if not object_key or object_key.startswith("/") or ".." in object_key.split("/"):
        raise ValueError("Object key must be a relative path without '..'")

    endpoint = endpoint.rstrip("/")
    host = urlsplit(endpoint).netloc
    if not host:
        raise ValueError("R2_ENDPOINT is not a valid URL")

    payload_hash = sha256_file(source)
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")
    canonical_uri = f"/{quote(bucket, safe='-_.~')}/{quote(object_key, safe='/-_.~')}"
    url = f"{endpoint}{canonical_uri}"

    headers = {
        "content-type": content_type,
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    if cache_control:
        headers["cache-control"] = cache_control

    canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in sorted(headers))
    signed_headers = ";".join(sorted(headers))
    canonical_request = "\n".join([
        "PUT", canonical_uri, "", canonical_headers, signed_headers, payload_hash
    ])
    credential_scope = f"{date_stamp}/auto/s3/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, credential_scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])
    signature = hmac.new(signing_key(secret_key, date_stamp), string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    headers["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    with source.open("rb") as body:
        response = requests.put(url, data=body, headers=headers, timeout=120)
    response.raise_for_status()
    print(f"Uploaded {source} to {bucket}/{object_key} (HTTP {response.status_code}).")


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload one directory to Cloudflare R2.")
    parser.add_argument("bucket", help="Destination R2 bucket name")
    parser.add_argument("key", help="Subfolder to upload items to")
    parser.add_argument("directory", type=Path, help="Local directory to upload")
    parser.add_argument("--content-type", help="HTTP content type (guessed from the filename by default)")
    parser.add_argument("--cache-control", help="Optional Cache-Control metadata for the object")
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env.local", help="Credentials file (default: v4/.env.local)")
    args = parser.parse_args()

    source = args.directory.resolve()
    if not source.is_dir():
        parser.error(f"Directory not found: {args.directory}")

    env_file = read_env_file(args.env_file)
    for file in source.iterdir():
        if file.is_file():
            content_type = args.content_type or mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            print(f"{args.key}/{file.name} - {content_type}")
            try:
                upload(file, args.bucket, f"{args.key}/{file.name}", content_type, args.cache_control, env_file)
            except (ValueError, requests.RequestException) as error:
                print(f"Upload failed: {error}", file=sys.stderr)
                return 1
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
