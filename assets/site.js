const year = document.getElementById('year');
if (year) year.textContent = new Date().getFullYear();

// Display fallbacks. The backend replaces these with live Square catalog prices.
const CATALOG = {
  'membership-household': { label: 'Household Annual Membership', variations: { renewal: { label: 'Annual renewal', priceMoney: { amount: 38000, currency: 'USD' } }, 'new-member': { label: 'New membership with initiation', priceMoney: { amount: 48000, currency: 'USD' } } } },
  'membership-individual': { label: 'Individual Annual Membership', variations: { renewal: { label: 'Annual renewal', priceMoney: { amount: 32000, currency: 'USD' } }, 'new-member': { label: 'New membership with initiation', priceMoney: { amount: 42000, currency: 'USD' } } } },
  'membership-crew': { label: 'Student, Military or Crew Membership', variations: { default: { label: 'Annual membership', priceMoney: { amount: 13000, currency: 'USD' } } } },
  'adult-sail-member': { label: 'Adult Learn to Sail — Member', variations: { default: { label: 'Registration', priceMoney: { amount: 27000, currency: 'USD' } } } },
  'adult-sail-nonmember': { label: 'Adult Learn to Sail — Non-member', variations: { default: { label: 'Registration', priceMoney: { amount: 54000, currency: 'USD' } } } },
  'capri-club': { label: 'Capri Club', variations: { checkout: { label: 'Boat checkout', priceMoney: { amount: 2500, currency: 'USD' } }, 'wednesday-race': { label: 'Wednesday night racing', priceMoney: { amount: 6000, currency: 'USD' } }, 'daily-rental': { label: 'Daily rental', priceMoney: { amount: 7500, currency: 'USD' } }, 'seasonal-membership': { label: 'Seasonal membership', priceMoney: { amount: 15500, currency: 'USD' } } } },
  'spring-regatta': { label: 'Spring Regatta', variations: { 'us-reg': { label: 'US Sailing registration', priceMoney: { amount: 5000, currency: 'USD' } }, 'non-us-reg': { label: 'Non-US Sailing registration', priceMoney: { amount: 5700, currency: 'USD' } }, 'club-youth': { label: 'Club Youth registration', priceMoney: { amount: 2000, currency: 'USD' } }, 't-shirt': { label: 'Additional T-shirt', priceMoney: { amount: 2000, currency: 'USD' } }, 'meal-ticket': { label: 'Additional meal ticket', priceMoney: { amount: 1000, currency: 'USD' } } } },
  'fall-regatta': { label: 'Fall Regatta', variations: { 'us-reg': { label: 'US Sailing registration', priceMoney: { amount: 7500, currency: 'USD' } }, 'non-us-reg': { label: 'Non-US Sailing registration', priceMoney: { amount: 8000, currency: 'USD' } }, 'club-youth': { label: 'Club Youth registration', priceMoney: { amount: 2000, currency: 'USD' } }, 't-shirt': { label: 'Additional T-shirt', priceMoney: { amount: 2000, currency: 'USD' } }, 'meal-ticket': { label: 'Additional meal ticket', priceMoney: { amount: 1500, currency: 'USD' } } } },
  'clubhouse-rental': { label: 'Clubhouse Rental', variations: { 'half-day': { label: 'Half-day', priceMoney: { amount: 25000, currency: 'USD' } }, 'full-day': { label: 'Full day', priceMoney: { amount: 50000, currency: 'USD' } } } }
};

const money = value => value
  ? (value.amount / 100).toLocaleString('en-US', { style: 'currency', currency: value.currency || 'USD' })
  : 'Price in Square';
const sku = (productKey, variationKey) => `${productKey}:${variationKey}`;
const splitSku = value => {
  const index = value.indexOf(':');
  return [value.slice(0, index), value.slice(index + 1)];
};
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
  if (!productInfo(value)) return;
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

const nav = document.getElementById('mainNav');
if (nav) {
  nav.parentElement.insertAdjacentHTML('beforeend', `
    <a class="cart-nav-button" href="#cartDrawer" data-bs-toggle="offcanvas" role="button" aria-controls="cartDrawer" aria-label="Open shopping cart">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M3 4h2l2.2 10.2a2 2 0 0 0 2 1.6h7.9a2 2 0 0 0 2-1.6L20.5 8H6"/><circle cx="10" cy="20" r="1"/><circle cx="18" cy="20" r="1"/></svg><span class="cart-count" id="cartCount">0</span>
    </a>`);
}

document.body.insertAdjacentHTML('beforeend', `
  <aside class="offcanvas offcanvas-end cart-offcanvas" tabindex="-1" id="cartDrawer" aria-labelledby="cartDrawerLabel">
    <div class="offcanvas-header"><div><small class="d-block text-white-50 text-uppercase fw-bold mb-1">Secure Square checkout</small><h2 class="offcanvas-title serif" id="cartDrawerLabel">Your cart</h2></div><button type="button" class="btn-close btn-close-white" data-bs-dismiss="offcanvas" aria-label="Close"></button></div>
    <div class="offcanvas-body d-flex flex-column"><div id="cartItems"></div><div class="mt-auto pt-4"><div id="discountRow" class="d-none justify-content-between small text-success pb-2"><span>Discounts</span><strong id="cartDiscount">−$0.00</strong></div><div class="d-flex justify-content-between align-items-center border-top pt-3"><span class="fw-bold">Total</span><span class="cart-total" id="cartTotal">$0.00</span></div><p class="small text-secondary mt-2" id="cartStatus">Connecting to Square for current pricing…</p><div class="d-grid gap-2 mt-3"><button type="button" class="btn btn-ybyc btn-red" id="squareCheckout" disabled>Checkout securely with Square</button><a href="shop.html" class="btn btn-ybyc btn-outline-navy">Browse Ship's Store</a><button type="button" class="btn btn-sm btn-link text-secondary" id="clearCart">Clear cart</button></div></div></div>
  </aside>`);

function fallbackTotal() {
  return Object.entries(cart).reduce((sum, [value, quantity]) => sum + ((productInfo(value)?.variation.priceMoney?.amount || 0) * quantity), 0);
}

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
  document.getElementById('cartStatus').textContent = !entries.length ? 'Add an item to begin.' : quote ? 'Current price, discounts, and taxes calculated by Square.' : apiAvailable ? 'Calculating current price…' : 'Start the YBYC checkout server to use live pricing.';
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

// Upgrade exact legacy purchase links; products with choices lead to the shop.
const legacyLinks = [
  ['/store/p15/', 'shop.html#memberships'], ['/store/p14/', 'shop.html#memberships'], ['/store/p18/', 'shop.html#capri'],
  ['/store/p13/', ['membership-crew', 'default']], ['/store/p19/', ['adult-sail-member', 'default']], ['/store/p20/', ['adult-sail-nonmember', 'default']],
  ['/store/p32/', ['spring-regatta', 'us-reg']], ['/store/p3/', ['spring-regatta', 'non-us-reg']], ['/store/p4/', ['spring-regatta', 'club-youth']],
  ['/store/p9/', ['fall-regatta', 'non-us-reg']], ['/store/p11/', ['fall-regatta', 't-shirt']], ['/store/p12/', ['spring-regatta', 'meal-ticket']]
];
document.querySelectorAll('a[href*="/store/p"]').forEach(link => {
  const match = legacyLinks.find(([path]) => link.href.includes(path));
  if (!match) return;
  if (typeof match[1] === 'string') { link.href = match[1]; link.textContent = 'Choose options'; return; }
  [link.dataset.productKey, link.dataset.variationKey] = match[1];
  if (/purchase|select|registration|online/i.test(link.textContent)) link.textContent = 'Add to cart';
});

renderCart();
loadCatalog();

document.querySelectorAll('#mainNav a:not(.dropdown-toggle)').forEach(link => {
  link.addEventListener('click', () => { if (nav?.classList.contains('show')) bootstrap.Collapse.getOrCreateInstance(nav).hide(); });
});
