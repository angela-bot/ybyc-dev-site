#!/usr/bin/env python3
"""Synchronize R2 original images, public WebPs, and editable photo catalogs.

For every immediate folder in the originals bucket, this script creates a WebP
in the same folder of the public bucket when one is missing, then writes the
matching ``content/photo-catalog/<folder>.yml`` file. Existing catalog title,
caption, photo order, alt text, and photo captions are retained where their
original image still exists.

Examples:
  python3 scripts/sync_r2_photo_catalogs.py --dry-run
  python3 scripts/sync_r2_photo_catalogs.py
  python3 scripts/sync_r2_photo_catalogs.py --folder capri-club

Required in .env.local:
  R2_ACCESS_KEY_ID=...
  R2_SECRET_ACCESS_KEY=...
  CLOUDFLARE_ACCOUNT_ID=...       # or R2_ENDPOINT=https://....r2.cloudflarestorage.com

Install dependencies once:
  python3 -m pip install requests Pillow PyYAML
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import io
import os
import sys
import xml.etree.ElementTree as element_tree
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit

import requests
import yaml
from PIL import Image, ImageOps

from upload_r2 import PROJECT_ROOT, read_env_file, setting, signing_key


ORIGINALS_BUCKET = "ybyc-originals"
PUBLIC_BUCKET = "ybyc-public-media"
DEFAULT_PUBLIC_BASE_URL = "https://pub-ff40f0e34f5d405ab572551084bddb62.r2.dev"
IMAGE_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


class R2Client:
    """Small AWS Signature V4 client for the R2 calls this job needs."""

    def __init__(self, config: dict[str, str]) -> None:
        self.access_key = setting(config, "R2_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID")
        self.secret_key = setting(config, "R2_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY")
        self.endpoint = setting(config, "R2_ENDPOINT", "CLOUDFLARE_R2_ENDPOINT")
        account_id = setting(config, "CLOUDFLARE_ACCOUNT_ID")
        if not self.endpoint and account_id:
            self.endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
        if not self.access_key or not self.secret_key or not self.endpoint:
            raise ValueError(
                "Missing R2 S3 credentials. Set R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, "
                "and CLOUDFLARE_ACCOUNT_ID (or R2_ENDPOINT) in .env.local."
            )
        self.endpoint = self.endpoint.rstrip("/")
        self.host = urlsplit(self.endpoint).netloc
        if not self.host:
            raise ValueError("R2_ENDPOINT is not a valid URL")
        self.session = requests.Session()

    def request(
        self,
        method: str,
        bucket: str,
        key: str = "",
        *,
        query: dict[str, str] | None = None,
        body: bytes = b"",
        extra_headers: dict[str, str] | None = None,
    ) -> requests.Response:
        if key.startswith("/") or ".." in key.split("/"):
            raise ValueError(f"Unsafe object key: {key!r}")
        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(body).hexdigest()
        canonical_uri = f"/{quote(bucket, safe='-_.~')}"
        if key:
            canonical_uri += f"/{quote(key, safe='/-_.~')}"
        canonical_query = urlencode(sorted((query or {}).items()), quote_via=quote, safe="-_.~")
        headers = {
            "host": self.host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        headers.update({name.lower(): value for name, value in (extra_headers or {}).items()})
        canonical_headers = "".join(f"{name}:{headers[name].strip()}\n" for name in sorted(headers))
        signed_headers = ";".join(sorted(headers))
        canonical_request = "\n".join(
            [method, canonical_uri, canonical_query, canonical_headers, signed_headers, payload_hash]
        )
        scope = f"{date_stamp}/auto/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signature = hmac.new(
            signing_key(self.secret_key, date_stamp), string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        headers["authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        url = f"{self.endpoint}{canonical_uri}"
        if canonical_query:
            url += f"?{canonical_query}"
        response = self.session.request(method, url, data=body or None, headers=headers, timeout=180)
        response.raise_for_status()
        return response

    def list_objects(self, bucket: str) -> list[str]:
        """Return all object keys in a bucket, following R2 pagination."""
        keys: list[str] = []
        continuation: str | None = None
        while True:
            query = {"list-type": "2"}
            if continuation:
                query["continuation-token"] = continuation
            root = element_tree.fromstring(self.request("GET", bucket, query=query).content)
            namespace = "{http://s3.amazonaws.com/doc/2006-03-01/}"
            keys.extend(node.text for node in root.findall(f"{namespace}Contents/{namespace}Key") if node.text)
            if root.findtext(f"{namespace}IsTruncated") != "true":
                return keys
            continuation = root.findtext(f"{namespace}NextContinuationToken")
            if not continuation:
                raise RuntimeError("R2 listed a truncated result without a continuation token")


def public_key(original_key: str) -> str:
    """Map ``folder/photo_orig.jpg`` to ``folder/photo.webp``."""
    path = Path(original_key)
    stem = path.stem
    if stem.lower().endswith("_orig"):
        stem = stem[:-5]
    return str(path.with_name(f"{stem}.webp")).replace("\\", "/")


def image_folders(keys: list[str]) -> dict[str, list[str]]:
    """Group direct image children by their immediate folder name."""
    folders: dict[str, list[str]] = defaultdict(list)
    for key in keys:
        parts = key.split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            continue
        if Path(parts[1]).suffix.lower() in IMAGE_EXTENSIONS:
            folders[parts[0]].append(key)
    return {folder: sorted(images) for folder, images in folders.items()}


def webp_bytes(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source)
        output = io.BytesIO()
        image.save(output, format="WEBP", quality=82, method=6)
        return output.getvalue()


def load_catalog(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as source:
        loaded = yaml.safe_load(source) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Catalog {path} must contain a YAML mapping")
    return loaded


def catalog_url(base_url: str, key: str) -> str:
    return f"{base_url.rstrip('/')}/{quote(key, safe='/')}"


def friendly_title(folder: str) -> str:
    return folder.replace("-", " ").replace("_", " ").title()


def rebuilt_catalog(existing: dict, folder: str, image_keys: list[str], base_url: str) -> dict:
    """Keep existing editable fields and order, then append newly found images."""
    public_keys = [public_key(key) for key in image_keys]
    url_to_entry = {
        entry.get("url"): entry
        for entry in existing.get("photos", [])
        if isinstance(entry, dict) and isinstance(entry.get("url"), str)
    }
    by_public_key = {catalog_url(base_url, key): key for key in public_keys}
    ordered_keys = [by_public_key[url] for url in url_to_entry if url in by_public_key]
    ordered_keys.extend(key for key in public_keys if key not in ordered_keys)
    result = {name: value for name, value in existing.items() if name != "photos"}
    result.setdefault("title", f"{friendly_title(folder)} slideshow")
    photos = []
    for key in ordered_keys:
        url = catalog_url(base_url, key)
        old = url_to_entry.get(url, {})
        entry = {name: value for name, value in old.items() if name != "url"}
        entry = {"url": url, "alt": entry.pop("alt", f"{friendly_title(folder)} photo"), **entry}
        photos.append(entry)
    result["photos"] = photos
    return result


def write_catalog(path: Path, catalog: dict) -> None:
    heading = "# This catalog is generated from R2 originals; edit titles, alt text, captions, and photo order here.\n"
    rendered = yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False, default_flow_style=False)
    path.write_text(heading + rendered, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create missing R2 WebPs and rebuild editable photo catalogs.")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without uploading or writing catalogs")
    parser.add_argument("--folder", action="append", help="Only synchronize this immediate originals-bucket folder (repeatable)")
    parser.add_argument("--originals-bucket", default=ORIGINALS_BUCKET)
    parser.add_argument("--public-bucket", default=PUBLIC_BUCKET)
    parser.add_argument("--public-base-url", default=DEFAULT_PUBLIC_BASE_URL)
    parser.add_argument("--catalog-dir", type=Path, default=PROJECT_ROOT / "content/photo-catalog")
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env.local")
    args = parser.parse_args()

    try:
        client = R2Client(read_env_file(args.env_file))
        folders = image_folders(client.list_objects(args.originals_bucket))
        wanted = set(args.folder or folders)
        missing = wanted - folders.keys()
        if missing:
            raise ValueError(f"No direct image files found in originals folder(s): {', '.join(sorted(missing))}")
        public_keys = set(client.list_objects(args.public_bucket))
        args.catalog_dir.mkdir(parents=True, exist_ok=True)
        webps_changed = 0
        catalogs_changed = 0
        for folder in sorted(wanted):
            originals = folders[folder]
            print(f"{folder}: {len(originals)} original image(s)")
            for original in originals:
                destination = public_key(original)
                if destination in public_keys:
                    continue
                if args.dry_run:
                    print(f"  would create {destination}")
                    webps_changed += 1
                    continue
                converted = webp_bytes(client.request("GET", args.originals_bucket, original).content)
                client.request(
                    "PUT",
                    args.public_bucket,
                    destination,
                    body=converted,
                    extra_headers={
                        "content-type": "image/webp",
                        "cache-control": "public, max-age=31536000, immutable",
                    },
                )
                public_keys.add(destination)
                webps_changed += 1
                print(f"  created {destination}")
            catalog_path = args.catalog_dir / f"{folder}.yml"
            refreshed = rebuilt_catalog(load_catalog(catalog_path), folder, originals, args.public_base_url)
            rendered = yaml.safe_dump(refreshed, allow_unicode=True, sort_keys=False, default_flow_style=False)
            current = catalog_path.read_text(encoding="utf-8") if catalog_path.exists() else ""
            if current.endswith(rendered) and current.startswith("# This catalog is generated"):
                continue
            if args.dry_run:
                print(f"  would rebuild {catalog_path.relative_to(PROJECT_ROOT)}")
                catalogs_changed += 1
            else:
                write_catalog(catalog_path, refreshed)
                catalogs_changed += 1
                print(f"  rebuilt {catalog_path.relative_to(PROJECT_ROOT)}")
        print(
            f"{'Would create' if args.dry_run else 'Created'} {webps_changed} WebP(s); "
            f"{'would rebuild' if args.dry_run else 'rebuilt'} {catalogs_changed} catalog(s)."
        )
    except (ValueError, RuntimeError, requests.RequestException, element_tree.ParseError, OSError) as error:
        print(f"Synchronization failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
