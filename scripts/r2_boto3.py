"""Shared Cloudflare R2 connection helpers for the boto3 scripts."""

from __future__ import annotations

import os
from pathlib import Path

import boto3
from botocore.config import Config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read_env_file(path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE entries without exposing their values."""
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


def r2_client(env_file: Path):
    """Create an S3-compatible boto3 client using v4/.env.local settings."""
    values = read_env_file(env_file)
    access_key = setting(values, "R2_ACCESS_KEY_ID", "AWS_ACCESS_KEY_ID")
    secret_key = setting(values, "R2_SECRET_ACCESS_KEY", "AWS_SECRET_ACCESS_KEY")
    endpoint = setting(values, "R2_ENDPOINT", "CLOUDFLARE_R2_ENDPOINT")
    account_id = setting(values, "CLOUDFLARE_ACCOUNT_ID")
    if not endpoint and account_id:
        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    if not access_key or not secret_key or not endpoint:
        raise ValueError(
            "Missing R2 S3 credentials. Set R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, "
            "and R2_ENDPOINT (or CLOUDFLARE_ACCOUNT_ID) in .env.local."
        )
    if not endpoint.startswith(("http://", "https://")):
        raise ValueError("R2_ENDPOINT must include https://")
    return boto3.client(
        "s3",
        endpoint_url=endpoint.rstrip("/"),
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="auto",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
