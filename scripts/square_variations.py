#!/usr/bin/env python3
"""Validate configured Square variation IDs without printing credentials."""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env(ROOT / ".env")
token = os.environ.get("SQUARE_ACCESS_TOKEN")
environment = os.environ.get("SQUARE_ENVIRONMENT", "sandbox").lower()
if not token:
    sys.exit("SQUARE_ACCESS_TOKEN is missing")

host = "connect.squareupsandbox.com" if environment == "sandbox" else "connect.squareup.com"
request = urllib.request.Request(
    f"https://{host}/v2/catalog/list",
    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    method="GET",
)

try:
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
except urllib.error.HTTPError as error:
    details = error.read().decode(errors="replace")
    sys.exit(f"Square returned HTTP {error.code}: {details}")

products = {}

for item in payload['objects']:
    if item['type'] == 'ITEM':
        label = item['item_data']['name']
        name = '-'.join(label.lower().replace('(','').replace(')','').split())
        products[name] = {
            'label': label,
            'variations': {}
        }
        for variation in item['item_data']['variations']:
            if variation['type'] == 'ITEM_VARIATION':
                var_label = variation['item_variation_data']['name']
                var_name = '-'.join(var_label.lower().replace('(','').replace(')','').replace(',','').split())
                products[name]['variations'][var_name] = {
                    'label': var_label,
                    'variationId': variation['id']
                }
        #print(json.dumps(item, indent=4))
print(json.dumps({ 'schema':2, 'products': products }, indent=4))
