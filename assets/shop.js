(() => {
  // Display fallbacks. The checkout API replaces these with Square's current values.
  const CATALOG = {
    'membership---renewal': { label: 'Membership - Renewal', variations: { individual: { label: 'Individual', priceMoney: { amount: 10000, currency: 'USD' } }, household: { label: 'Household', priceMoney: { amount: 20000, currency: 'USD' } }, crew: { label: 'Crew', priceMoney: { amount: 5000, currency: 'USD' } }, 'student/military': { label: 'Student, Military', priceMoney: { amount: 2500, currency: 'USD' } } } },
    'ticket-for-annual-meeting': { label: 'Ticket for Annual Meeting', variations: { regular: { label: 'Ticket', priceMoney: { amount: 2000, currency: 'USD' } } } }
  };

  const money = value => value ? (value.amount / 100).toLocaleString('en-US', { style: 'currency', currency: value.currency || 'USD' }) : 'Price in Square';
  const sku = (productKey, variationKey) => `${productKey}:${variationKey}`;
  const splitSku = value => { const index = value.indexOf(':'); return [value.slice(0, index), value.slice(index + 1)]; };
  const productInfo = value => {
    const [productKey, variationKey] = splitSku(value);
    const product = CATALOG[productKey];
    const variation = product?.variations?.[variationKey];
    return product && variation ? { productKey, variationKey, product, variation } : null;
  };

  const STORAGE_KEY = 'ybyc-cart-v2';
  let cart = {};
  let quote = null;
  let apiAvailable = false;
  try { cart = JSON.parse(localStorage.getItem(STORAGE_KEY)) || {}; } catch { cart = {}; }

  // Remove saved items whose store section is no longer displayed.
  const availableSkus = new Set(Array.from(document.querySelectorAll('[data-product-key][data-variation-key]'), button => sku(button.dataset.productKey, button.dataset.variationKey)));
  Object.keys(cart).forEach(value => { if (!availableSkus.has(value)) delete cart[value]; });
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cart));

  function cartPayload() {
    return { items: Object.entries(cart).filter(([, quantity]) => quantity > 0).map(([value, quantity]) => { const [productKey, variationKey] = splitSku(value); return { productKey, variationKey, quantity }; }) };
  }
  function saveCart(refreshQuote = true) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(cart));
    quote = null;
    renderCart();
    if (refreshQuote) requestQuote();
  }
  function addToCart(productKey, variationKey) {
    const value = sku(productKey, variationKey);
    if (!availableSkus.has(value) || !productInfo(value) || productInfo(value).variation.inStock === false) return;
    cart[value] = (cart[value] || 0) + 1;
    saveCart();
    bootstrap.Offcanvas.getOrCreateInstance(document.getElementById('cartDrawer')).show();
  }
  function changeQuantity(value, delta) {
    if (!cart[value]) return;
    cart[value] += delta;
    if (cart[value] <= 0) delete cart[value];
    saveCart();
  }

  const shopNav = document.getElementById('mainNav');
  if (shopNav) {
    shopNav.parentElement.insertAdjacentHTML('beforeend', `
      <a class="cart-nav-button" href="#cartDrawer" data-bs-toggle="offcanvas" role="button" aria-controls="cartDrawer" aria-label="Open shopping cart">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 4h2l2.2 10.2a2 2 0 0 0 2 1.6h7.9a2 2 0 0 0 2-1.6L20.5 8H6"/><circle cx="10" cy="20" r="1"/><circle cx="18" cy="20" r="1"/></svg><span class="cart-count" id="cartCount">0</span>
      </a>`);
  }
  document.body.insertAdjacentHTML('beforeend', `
    <aside class="offcanvas offcanvas-end cart-offcanvas" tabindex="-1" id="cartDrawer" aria-labelledby="cartDrawerLabel">
      <div class="offcanvas-header"><div><small class="d-block text-white-50 text-uppercase fw-bold mb-1">Secure Square checkout</small><h2 class="offcanvas-title serif" id="cartDrawerLabel">Your cart</h2></div><button type="button" class="btn-close btn-close-white" data-bs-dismiss="offcanvas" aria-label="Close"></button></div>
      <div class="offcanvas-body d-flex flex-column"><div id="cartItems"></div><div class="mt-auto pt-4"><div id="discountRow" class="d-none justify-content-between small text-success pb-2"><span>Discounts</span><strong id="cartDiscount">−$0.00</strong></div><div class="d-flex justify-content-between align-items-center border-top pt-3"><span class="fw-bold">Total</span><span class="cart-total" id="cartTotal">$0.00</span></div><p class="small text-secondary mt-2" id="cartStatus">Connecting to Square for current pricing…</p><div class="d-grid gap-2 mt-3"><button type="button" class="btn btn-ybyc btn-red" id="squareCheckout" disabled>Checkout securely with Square</button><a href="shop.html" class="btn btn-ybyc btn-outline-navy">Browse Ship's Store</a><button type="button" class="btn btn-sm btn-link text-secondary" id="clearCart">Clear cart</button></div></div></div>
    </aside>`);

  function fallbackTotal() { return Object.entries(cart).reduce((sum, [value, quantity]) => sum + ((productInfo(value)?.variation.priceMoney?.amount || 0) * quantity), 0); }
  function renderCart() {
    const entries = Object.entries(cart).filter(([value, quantity]) => productInfo(value) && quantity > 0);
    const count = entries.reduce((sum, [, quantity]) => sum + quantity, 0);
    const countNode = document.getElementById('cartCount');
    if (countNode) { countNode.textContent = count; countNode.hidden = count === 0; }
    const items = document.getElementById('cartItems');
    if (!items) return;
    if (!entries.length) {
      items.innerHTML = '<div class="text-center py-5"><p class="serif fs-4 text-secondary">Your cart is empty.</p><a href="shop.html" class="btn btn-ybyc btn-outline-navy">Visit Ship\'s Store</a></div>';
    } else {
      items.innerHTML = entries.map(([value, quantity]) => {
        const { product, variation } = productInfo(value);
        return `<div class="cart-item"><div class="d-flex justify-content-between gap-3"><div><h3 class="cart-item-title">${product.label}</h3><span class="d-block small text-secondary">${variation.label}</span><span class="cart-item-price">${money(variation.priceMoney)}</span></div><button class="btn-close" type="button" data-cart-remove="${value}" aria-label="Remove ${product.label}"></button></div><div class="quantity-control mt-3"><button type="button" data-cart-change="${value}" data-delta="-1" aria-label="Decrease quantity">−</button><span>${quantity}</span><button type="button" data-cart-change="${value}" data-delta="1" aria-label="Increase quantity">+</button></div></div>`;
      }).join('');
    }
    const total = quote?.totalMoney || { amount: fallbackTotal(), currency: 'USD' };
    document.getElementById('cartTotal').textContent = money(total);
    const discount = quote?.totalDiscountMoney?.amount || 0;
    document.getElementById('discountRow').classList.toggle('d-none', !discount);
    document.getElementById('discountRow').classList.toggle('d-flex', Boolean(discount));
    document.getElementById('cartDiscount').textContent = `−${money({ amount: discount, currency: quote?.totalDiscountMoney?.currency || 'USD' })}`;
    const checkout = document.getElementById('squareCheckout');
    checkout.disabled = !entries.length || !apiAvailable || !quote;
    document.getElementById('cartStatus').textContent = !entries.length ? 'Add an item to begin.' : quote ? 'Current price, discounts, and taxes calculated by Square.' : apiAvailable ? 'Calculating current price…' : 'Checkout is temporarily unavailable.';
  }

  async function loadCatalog() {
    try {
      const response = await fetch('/api/catalog', { headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('Catalog unavailable');
      const payload = await response.json();
      Object.entries(payload.products || {}).forEach(([productKey, product]) => {
        if (!CATALOG[productKey]) return;
        CATALOG[productKey].label = product.label;
        Object.entries(product.variations || {}).forEach(([variationKey, variation]) => {
          if (!CATALOG[productKey].variations[variationKey]) return;
          Object.assign(CATALOG[productKey].variations[variationKey], variation);
        });
      });
      apiAvailable = true;
      document.querySelectorAll('[data-square-product][data-square-variation]').forEach(node => {
        const variation = CATALOG[node.dataset.squareProduct]?.variations?.[node.dataset.squareVariation];
        if (variation?.priceMoney) node.textContent = money(variation.priceMoney);
      });
      document.querySelectorAll('[data-product-key][data-variation-key]').forEach(button => {
        const variation = CATALOG[button.dataset.productKey]?.variations?.[button.dataset.variationKey];
        if (variation?.inStock === false) { button.disabled = true; button.setAttribute('aria-disabled', 'true'); button.textContent = 'Out of stock'; }
      });
      Object.keys(cart).forEach(value => { if (productInfo(value)?.variation.inStock === false) delete cart[value]; });
      localStorage.setItem(STORAGE_KEY, JSON.stringify(cart));
      renderCart();
      if (Object.keys(cart).length) requestQuote();
    } catch {
      apiAvailable = false;
      renderCart();
    }
  }
  async function requestQuote() {
    if (!apiAvailable || !Object.keys(cart).length) return;
    try {
      const response = await fetch('/api/cart/quote', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cartPayload()) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.errors?.[0]?.detail || 'Unable to calculate order');
      quote = payload.order;
      renderCart();
    } catch (error) {
      quote = null;
      document.getElementById('cartStatus').textContent = error.message;
    }
  }

  document.addEventListener('click', event => {
    const add = event.target.closest('[data-product-key][data-variation-key]');
    if (add) { event.preventDefault(); addToCart(add.dataset.productKey, add.dataset.variationKey); return; }
    const change = event.target.closest('[data-cart-change]');
    if (change) { changeQuantity(change.dataset.cartChange, Number(change.dataset.delta)); return; }
    const remove = event.target.closest('[data-cart-remove]');
    if (remove) { delete cart[remove.dataset.cartRemove]; saveCart(); }
  });
  document.getElementById('clearCart')?.addEventListener('click', () => { cart = {}; saveCart(false); });
  document.getElementById('squareCheckout')?.addEventListener('click', async event => {
    const button = event.currentTarget;
    button.disabled = true;
    button.textContent = 'Creating secure checkout…';
    try {
      const response = await fetch('/api/checkout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cartPayload()) });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.errors?.[0]?.detail || 'Checkout could not be created');
      window.location.assign(payload.url);
    } catch (error) {
      document.getElementById('cartStatus').textContent = error.message;
      button.disabled = false;
      button.textContent = 'Checkout securely with Square';
    }
  });
  renderCart();
  loadCatalog();
})();
