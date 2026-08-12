# Square checkout configuration

## Files to edit

- `content/square-catalog.json` maps the cart's stable product keys to Square Catalog variation IDs.
- `.env` holds Square credentials and must never be committed.
- `.env.example` documents the required environment variables without containing secrets.

The HTML and cart use the product and variation keys in `content/square-catalog.json`. Keep those keys in sync with the page bindings when adding or renaming products.

## Run locally

The checkout requires the included backend; a plain static file server cannot securely contact Square.

```bash
cd v3
python3 server.py
```

Open `http://localhost:8000/shop.html`. The server provides:

- `GET /api/catalog` for current Square catalog prices;
- `POST /api/cart/quote` for automatic discounts, taxes, and totals;
- `POST /api/checkout` for one hosted Square checkout link.

The access token is read only by `server.py` and is never delivered to the browser.

## Sandbox setup

1. Create matching items and variations in the Square sandbox catalog.
2. Copy each **item variation ID** into `content/square-catalog.json`. Do not use the parent item ID.
3. Copy `.env.example` to `.env` and enter the sandbox application ID, location ID, and access token.
4. Run `python3 scripts/inspect_square_catalog.py` and confirm every variation validates.
5. Test order creation and payment using Square's sandbox test cards.

Products with choices use named variations. For example, `capri-club` has separate checkout-fee, wednesday-night-racing, daily-rental, and annual-membership mappings.

## Production switch

1. Recreate or confirm the equivalent production catalog items.
2. Replace the sandbox variation IDs in `content/square-catalog.json` with the production variation IDs.
3. Set `SQUARE_ENVIRONMENT=production` in the deployed environment.
4. Replace the sandbox application ID, location ID, and access token with production values.
5. Deploy `server.py` or equivalent API handlers behind HTTPS.
6. Run a low-value live transaction before opening checkout publicly.

The webhook signature key is optional for creating hosted checkouts. Add it later when implementing asynchronous payment confirmation, fulfillment automation, or server-verified receipts.

Variation IDs are identifiers, not secrets, and may remain in source control. Access tokens and webhook signature keys are secrets and belong only in `.env` or the hosting provider's encrypted environment settings.
