#!/usr/bin/env python3
"""Static site server and minimal Square hosted-checkout API for YBYC."""

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "content" / "square-catalog.json"


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


def square_host() -> str:
    environment = os.environ.get("SQUARE_ENVIRONMENT", "sandbox").lower()
    return "connect.squareupsandbox.com" if environment == "sandbox" else "connect.squareup.com"


def square_request(path: str, method: str = "GET", payload=None):
    token = os.environ.get("SQUARE_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("SQUARE_ACCESS_TOKEN is not configured")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    api_version = os.environ.get("SQUARE_API_VERSION")
    if api_version:
        headers["Square-Version"] = api_version
    request = urllib.request.Request(
        f"https://{square_host()}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            details = json.loads(error.read().decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            details = {"errors": [{"detail": f"Square returned HTTP {error.code}"}]}
        raise SquareError(error.code, details) from error


class SquareError(Exception):
    def __init__(self, status: int, payload: dict):
        super().__init__(f"Square returned HTTP {status}")
        self.status = status
        self.payload = payload


def catalog_config() -> dict:
    return json.loads(CONFIG_PATH.read_text())


def configured_variations():
    config = catalog_config()
    for product_key, product in config["products"].items():
        for variation_key, variation in product["variations"].items():
            yield product_key, product, variation_key, variation


def inventory_by_variation(variation_ids: list[str]) -> dict:
    """Return live on-hand quantities for inventory-tracked variations."""
    payload = {"catalog_object_ids": variation_ids, "states": ["IN_STOCK"]}
    location_id = os.environ.get("SQUARE_LOCATION_ID")
    if location_id:
        payload["location_ids"] = [location_id]
    response = square_request("/v2/inventory/batch-retrieve-counts", "POST", payload)
    quantities = {}
    for count in response.get("counts", []):
        variation_id = count.get("catalog_object_id")
        if not variation_id:
            continue
        quantities[variation_id] = quantities.get(variation_id, 0) + float(count.get("quantity", 0))
    return quantities


def catalog_response() -> dict:
    configured = list(configured_variations())
    square = square_request(
        "/v2/catalog/batch-retrieve",
        "POST",
        {"object_ids": [variation["variationId"] for _, _, _, variation in configured], "include_related_objects": True},
    )
    found = {obj["id"]: obj for obj in square.get("objects", []) if obj.get("type") == "ITEM_VARIATION"}
    tracked_ids = [
        variation["variationId"]
        for _, _, _, variation in configured
        if found.get(variation["variationId"], {}).get("item_variation_data", {}).get("track_inventory")
    ]
    try:
        inventory = inventory_by_variation(tracked_ids) if tracked_ids else {}
    except SquareError:
        # Catalog prices should remain available if the token lacks inventory scope.
        inventory = None
    products = {}
    for product_key, product, variation_key, variation in configured:
        obj = found.get(variation["variationId"], {})
        data = obj.get("item_variation_data", {})
        products.setdefault(product_key, {"label": product["label"], "variations": {}})
        products[product_key]["variations"][variation_key] = {
            "label": variation["label"],
            "squareName": data.get("name", variation["label"]),
            "variationId": variation["variationId"],
            "priceMoney": data.get("price_money"),
            "presentAtAllLocations": obj.get("present_at_all_locations", False),
            "inStock": not data.get("track_inventory") or inventory is None or inventory.get(variation["variationId"], 0) > 0,
        }
    return {"environment": os.environ.get("SQUARE_ENVIRONMENT", "sandbox"), "products": products}


def order_line_items(cart_payload: dict) -> list:
    config = catalog_config()["products"]
    combined = {}
    items = cart_payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("The cart is empty")
    for item in items:
        product_key = item.get("productKey")
        variation_key = item.get("variationKey")
        try:
            quantity = int(item.get("quantity", 1))
        except (TypeError, ValueError) as error:
            raise ValueError("Invalid item quantity") from error
        if quantity < 1 or quantity > 50:
            raise ValueError("Item quantity must be between 1 and 50")
        try:
            variation_id = config[product_key]["variations"][variation_key]["variationId"]
        except (KeyError, TypeError) as error:
            raise ValueError(f"Unknown product variation: {product_key}:{variation_key}") from error
        combined[variation_id] = combined.get(variation_id, 0) + quantity
    return [{"catalog_object_id": variation_id, "quantity": str(quantity)} for variation_id, quantity in combined.items()]


def order_payload(cart_payload: dict) -> dict:
    location_id = os.environ.get("SQUARE_LOCATION_ID")
    if not location_id:
        raise RuntimeError("SQUARE_LOCATION_ID is not configured")
    return {
        "location_id": location_id,
        "line_items": order_line_items(cart_payload),
        "pricing_options": {"auto_apply_discounts": True, "auto_apply_taxes": True},
    }


def money(value):
    if not value:
        return None
    return {"amount": value.get("amount", 0), "currency": value.get("currency", "USD")}


def sanitized_order(order: dict) -> dict:
    return {
        "id": order.get("id"),
        "state": order.get("state"),
        "lineItems": [
            {
                "uid": item.get("uid"),
                "name": item.get("name"),
                "variationName": item.get("variation_name"),
                "quantity": item.get("quantity"),
                "basePriceMoney": money(item.get("base_price_money")),
                "totalDiscountMoney": money(item.get("total_discount_money")),
                "totalTaxMoney": money(item.get("total_tax_money")),
                "totalMoney": money(item.get("total_money")),
            }
            for item in order.get("line_items", [])
        ],
        "discounts": [
            {"name": discount.get("name"), "percentage": discount.get("percentage"), "amountMoney": money(discount.get("amount_money"))}
            for discount in order.get("discounts", [])
        ],
        "taxes": [
            {"name": tax.get("name"), "percentage": tax.get("percentage"), "appliedMoney": money(tax.get("applied_money"))}
            for tax in order.get("taxes", [])
        ],
        "totalDiscountMoney": money(order.get("total_discount_money")),
        "totalTaxMoney": money(order.get("total_tax_money")),
        "totalMoney": money(order.get("total_money")),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def translate_path(self, path):
        """Expose archived source assets referenced by the rebuilt pages."""
        parsed_path = urlparse(path).path
        if parsed_path.startswith("/archived_site/"):
            candidate = (ROOT.parent / parsed_path.lstrip("/")).resolve()
            archive_root = (ROOT.parent / "archived_site").resolve()
            if candidate == archive_root or archive_root in candidate.parents:
                return str(candidate)
        return super().translate_path(path)

    def json_response(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 100_000:
            raise ValueError("Request body is too large")
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self):
        if urlparse(self.path).path == "/api/catalog":
            try:
                self.json_response(catalog_response())
            except SquareError as error:
                self.json_response(error.payload, 502)
            except Exception as error:
                self.json_response({"errors": [{"detail": str(error)}]}, 500)
            return
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in {"/api/cart/quote", "/api/checkout"}:
            self.json_response({"errors": [{"detail": "Not found"}]}, 404)
            return
        try:
            payload = self.read_json()
            order = order_payload(payload)
            if path == "/api/cart/quote":
                result = square_request("/v2/orders/calculate", "POST", {"order": order})
                self.json_response({"order": sanitized_order(result["order"])})
                return
            checkout_options = {}
            redirect_url = os.environ.get("CHECKOUT_REDIRECT_URL")
            if redirect_url:
                checkout_options["redirect_url"] = redirect_url
            request_payload = {"idempotency_key": str(uuid.uuid4()), "order": order}
            if checkout_options:
                request_payload["checkout_options"] = checkout_options
            result = square_request("/v2/online-checkout/payment-links", "POST", request_payload)
            payment_link = result["payment_link"]
            self.json_response({"url": payment_link["url"], "orderId": payment_link.get("order_id")}, 201)
        except ValueError as error:
            self.json_response({"errors": [{"detail": str(error)}]}, 400)
        except SquareError as error:
            self.json_response(error.payload, 502)
        except Exception as error:
            self.json_response({"errors": [{"detail": str(error)}]}, 500)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Serving YBYC at http://localhost:{port}")
    print(f"Square environment: {os.environ.get('SQUARE_ENVIRONMENT', 'sandbox')}")
    try:
        ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped")
