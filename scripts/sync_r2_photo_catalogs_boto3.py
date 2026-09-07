#!/usr/bin/env python3
"""Create missing public WebPs and rebuild editable photo catalogs using boto3.

Examples:
  python3 scripts/sync_r2_photo_catalogs_boto3.py --dry-run
  python3 scripts/sync_r2_photo_catalogs_boto3.py --folder capri-club
  python3 scripts/sync_r2_photo_catalogs_boto3.py --refresh-rights

Requires: python3 -m pip install boto3 Pillow PyYAML
"""

from __future__ import annotations

import argparse
import io
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

import yaml
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image, ImageOps

from r2_boto3 import PROJECT_ROOT, r2_client


ORIGINALS_BUCKET = "ybyc-originals"
PUBLIC_BUCKET = "ybyc-public-media"
DEFAULT_PUBLIC_BASE_URL = "https://pub-ff40f0e34f5d405ab572551084bddb62.r2.dev"
IMAGE_EXTENSIONS = {".avif", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
DEFAULT_RIGHTS = {
    "creator": "Yaquina Bay Yacht Club",
    "copyright": "© Yaquina Bay Yacht Club",
    "rights": "All rights reserved. No AI training or machine-learning use.",
}


def list_keys(client, bucket: str) -> list[str]:
    paginator = client.get_paginator("list_objects_v2")
    return [
        item["Key"]
        for page in paginator.paginate(Bucket=bucket)
        for item in page.get("Contents", [])
    ]


def image_folders(keys: list[str]) -> dict[str, list[str]]:
    folders: dict[str, list[str]] = defaultdict(list)
    for key in keys:
        parts = key.split("/")
        if len(parts) == 2 and parts[0] and parts[1] and Path(parts[1]).suffix.lower() in IMAGE_EXTENSIONS:
            folders[parts[0]].append(key)
    return {folder: sorted(images) for folder, images in folders.items()}


def public_key(original_key: str) -> str:
    path = Path(original_key)
    stem = path.stem.removesuffix("_orig").removesuffix("_ORIG")
    return str(path.with_name(f"{stem}.webp")).replace("\\", "/")


def webp_bytes(data: bytes, rights: dict[str, str]) -> bytes:
    with Image.open(io.BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source)
        exif = image.getexif()
        exif[270] = rights["rights"]  # ImageDescription
        exif[315] = rights["creator"]  # Artist
        exif[33432] = rights["copyright"]  # Copyright
        output = io.BytesIO()
        image.save(output, format="WEBP", quality=82, method=6, exif=exif.tobytes())
        return output.getvalue()


def catalog_url(base_url: str, key: str) -> str:
    return f"{base_url.rstrip('/')}/{quote(key, safe='/')}"


def friendly_title(folder: str) -> str:
    return folder.replace("-", " ").replace("_", " ").title()


def load_catalog(path: Path) -> dict:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Catalog {path} must contain a YAML mapping")
    return loaded


def rebuilt_catalog(existing: dict, folder: str, originals: list[str], base_url: str) -> dict:
    public_keys = [public_key(key) for key in originals]
    old_entries = {
        entry.get("url"): entry
        for entry in existing.get("photos", [])
        if isinstance(entry, dict) and isinstance(entry.get("url"), str)
    }
    url_to_key = {catalog_url(base_url, key): key for key in public_keys}
    ordered_keys = [url_to_key[url] for url in old_entries if url in url_to_key]
    ordered_keys.extend(key for key in public_keys if key not in ordered_keys)
    catalog = {name: value for name, value in existing.items() if name != "photos"}
    catalog.setdefault("title", f"{friendly_title(folder)} slideshow")
    for name, value in DEFAULT_RIGHTS.items():
        catalog.setdefault(name, value)
    catalog["photos"] = []
    for key in ordered_keys:
        url = catalog_url(base_url, key)
        old = old_entries.get(url, {})
        rest = {name: value for name, value in old.items() if name not in {"url", "alt"}}
        catalog["photos"].append({"url": url, "alt": old.get("alt", f"{friendly_title(folder)} photo"), **rest})
    return catalog


def rights_metadata(catalog: dict) -> dict[str, str]:
    """Return non-empty, human-editable catalog rights fields for an image."""
    metadata = {}
    for name, default in DEFAULT_RIGHTS.items():
        value = catalog.get(name, default)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Catalog {name!r} must be a non-empty string")
        metadata[name] = value.strip()
    return metadata


def r2_metadata(rights: dict[str, str]) -> dict[str, str]:
    """R2/S3 user-metadata values are HTTP headers and therefore ASCII-only."""
    return {
        name: value.replace("©", "(c)").encode("ascii", "replace").decode("ascii")
        for name, value in rights.items()
    }


def write_catalog(path: Path, catalog: dict) -> None:
    heading = "# This catalog is generated from R2 originals; edit titles, alt text, captions, and photo order here.\n"
    path.write_text(heading + yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize R2 originals, public WebPs, and photo catalogs.")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing to R2 or disk")
    parser.add_argument(
        "--refresh-rights",
        action="store_true",
        help="Regenerate existing public WebPs with the catalog's embedded and R2 rights metadata",
    )
    parser.add_argument("--folder", action="append", help="Only synchronize this immediate originals folder (repeatable)")
    parser.add_argument("--originals-bucket", default=ORIGINALS_BUCKET)
    parser.add_argument("--public-bucket", default=PUBLIC_BUCKET)
    parser.add_argument("--public-base-url", default=DEFAULT_PUBLIC_BASE_URL)
    parser.add_argument("--catalog-dir", type=Path, default=PROJECT_ROOT / "content/photo-catalog")
    parser.add_argument("--env-file", type=Path, default=PROJECT_ROOT / ".env.local")
    args = parser.parse_args()

    try:
        client = r2_client(args.env_file)
        folders = image_folders(list_keys(client, args.originals_bucket))
        requested = set(args.folder or folders)
        missing_folders = requested - folders.keys()
        if missing_folders:
            raise ValueError(f"No direct images in originals folder(s): {', '.join(sorted(missing_folders))}")
        public_keys = set(list_keys(client, args.public_bucket))
        webps_changed = catalogs_changed = 0
        args.catalog_dir.mkdir(parents=True, exist_ok=True)
        for folder in sorted(requested):
            originals = folders[folder]
            print(f"{folder}: {len(originals)} original image(s)")
            path = args.catalog_dir / f"{folder}.yml"
            catalog = rebuilt_catalog(load_catalog(path), folder, originals, args.public_base_url)
            rights = rights_metadata(catalog)
            for original in originals:
                destination = public_key(original)
                exists = destination in public_keys
                if exists and not args.refresh_rights:
                    continue
                if args.dry_run:
                    action = "refresh" if exists else "create"
                    print(f"  would {action} {destination}")
                else:
                    original_bytes = client.get_object(Bucket=args.originals_bucket, Key=original)["Body"].read()
                    client.put_object(
                        Bucket=args.public_bucket,
                        Key=destination,
                        Body=webp_bytes(original_bytes, rights),
                        ContentType="image/webp",
                        CacheControl="public, max-age=31536000, immutable",
                        Metadata=r2_metadata(rights),
                    )
                    public_keys.add(destination)
                    action = "refreshed" if exists else "created"
                    print(f"  {action} {destination}")
                webps_changed += 1
            rendered = yaml.safe_dump(catalog, allow_unicode=True, sort_keys=False)
            current = path.read_text(encoding="utf-8") if path.exists() else ""
            if current.startswith("# This catalog is generated") and current.endswith(rendered):
                continue
            if args.dry_run:
                print(f"  would rebuild {path.relative_to(PROJECT_ROOT)}")
            else:
                write_catalog(path, catalog)
                print(f"  rebuilt {path.relative_to(PROJECT_ROOT)}")
            catalogs_changed += 1
        print(f"{'Would create' if args.dry_run else 'Created'} {webps_changed} WebP(s); {'would rebuild' if args.dry_run else 'rebuilt'} {catalogs_changed} catalog(s).")
    except (ValueError, BotoCoreError, ClientError, OSError, yaml.YAMLError) as error:
        print(f"Synchronization failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
