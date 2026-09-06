#!/usr/bin/env python3
"""Upload new original images from one directory to Cloudflare R2 using boto3.

The directory is read non-recursively. Each image is uploaded to the specified
folder in ``ybyc-originals`` unless that exact object key already exists.

Examples:
  python3 scripts/upload_r2_boto3.py images/cdhr-2014-1 cdhr-2014-1
  python3 scripts/upload_r2_boto3.py images/regattas regattas --dry-run

Requires: python3 -m pip install boto3
Required in .env.local: R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY, plus
R2_ENDPOINT or CLOUDFLARE_ACCOUNT_ID.
"""

from __future__ import annotations

import argparse
import mimetypes
import sys
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

from r2_boto3 import PROJECT_ROOT, r2_client


ORIGINALS_BUCKET = "ybyc-originals"
IMAGE_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


def object_exists(client, bucket: str, key: str) -> bool:
    try:
        client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def safe_prefix(value: str) -> str:
    prefix = value.strip("/")
    if not prefix or ".." in prefix.split("/"):
        raise ValueError("Folder must be a non-empty relative path without '..'")
    return prefix


def main() -> int:
    parser = argparse.ArgumentParser(description="Upload only new images from a directory to Cloudflare R2.")
    parser.add_argument("directory", type=Path, help="Local directory of images (not recursive)")
    parser.add_argument("folder", help="Destination folder in the originals bucket")
    parser.add_argument("--bucket", default=ORIGINALS_BUCKET, help=f"Destination bucket (default: {ORIGINALS_BUCKET})")
    parser.add_argument("--dry-run", action="store_true", help="Report uploads without changing R2")
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env.local")
    args = parser.parse_args()

    directory = args.directory.resolve()
    if not directory.is_dir():
        parser.error(f"Directory not found: {args.directory}")
    try:
        prefix = safe_prefix(args.folder)
        client = r2_client(args.env_file)
        images = sorted(path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)
        if not images:
            print("No supported image files found.")
            return 0
        uploaded = skipped = 0
        for image in images:
            key = f"{prefix}/{image.name}"
            if object_exists(client, args.bucket, key):
                print(f"Skipped (already exists): {args.bucket}/{key}")
                skipped += 1
                continue
            if args.dry_run:
                print(f"Would upload: {args.bucket}/{key}")
                uploaded += 1
                continue
            content_type = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
            client.upload_file(str(image), args.bucket, key, ExtraArgs={"ContentType": content_type})
            print(f"Uploaded: {args.bucket}/{key}")
            uploaded += 1
        print(f"{'Would upload' if args.dry_run else 'Uploaded'} {uploaded}; skipped {skipped} existing image(s).")
    except (ValueError, BotoCoreError, ClientError, OSError) as error:
        print(f"Upload failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
