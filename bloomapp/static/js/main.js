/* ═══════════════════════════════════════════════════════════════
   Bloomify – main.js
   Header (menu, occasions, pincode panel, search), pincode checker,
   toasts, newsletter, back-to-top, scroll reveal, modals.
   Never builds HTML from strings: user/server text goes in via textContent.
   ═══════════════════════════════════════════════════════════════ */

const PIN_KEY = 'bloomify_pincode';

function storage(action, value) {
  try {
    if (action === 'get') return JSON.parse(localStorage.getItem(PIN_KEY) || 'null');
    localStorage.setItem(PIN_KEY, JSON.stringify(value));
  } catch (e) { /* private mode or storage blocked: the checker still works, it just isn't remembered */ }
  return null;
}

function el(tag, attrs = {}, text) {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, v));
  if (text !== undefined) node.textContent = text;
  return node;
}

function iconClone(type) {
  const tpl = document.getElementById('toast-icons');
  const holder = tpl && tpl.content.querySelector(`[data-type="${type}"]`);
  return holder ? holder.firstElementChild.cloneNode(true) : document.createTextNode('');
}

function rupees(n) {
  return '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });
}

/* ─── Toasts ─────────────────────────────────────────────────── */
function showToast(message, type = 'success', duration = 5000) {
  const kinds = { success: 'Done', error: 'Something went wrong', warning: 'Please check', info: 'Note' };
  if (!kinds[type]) type = 'info';
  let container = document.getElementById('toast-container');
  if (!container) {
    container = el('div', { id: 'toast-container', class: 'toast-container', role: 'status', 'aria-live': 'polite' });
    document.body.appendChild(container);
  }
  const toast = el('div', { class: `toast ${type}` });
  const icon = el('span', { class: 'toast-icon' });
  icon.appendChild(iconClone(type));
  const body = el('div', { class: 'toast-body' });
  body.append(el('div', { class: 'toast-title' }, kinds[type]), el('div', { class: 'toast-msg' }, message));
  const close = el('button', { type: 'button', class: 'toast-close', 'aria-label': 'Dismiss' });
  close.appendChild(iconClone('close'));
  close.addEventListener('click', () => toast.remove());
  toast.append(icon, body, close);
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('hide');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}
window.showToast = showToast;

/* ─── Pincode checker ────────────────────────────────────────── */
function pinSummary(q) {
  return `Delivers to ${q.city} in ${q.eta} · from ${rupees(q.charge_from)}, free over ${rupees(q.free_above)}`;
}

function applySavedPin(q) {
  document.querySelectorAll('[data-pin-chip]').forEach(n => {
    n.textContent = q ? `Deliver to ${q.pincode}` : 'Check delivery';
  });
  document.querySelectorAll('[data-pin-bar]').forEach(n => {
    n.textContent = q ? `Deliver to ${q.pincode} · ${q.city}, ${q.eta}` : 'Check delivery to your pincode';
  });
  document.querySelectorAll('[data-pin-bar-action]').forEach(n => { n.textContent = q ? 'Change' : 'Check'; });
  document.querySelectorAll('[data-pin-check] input[name="pincode"]').forEach(inp => {
    if (q && !inp.value) inp.value = q.pincode;
  });
}

function showPinResult(form, ok, text) {
  const out = form.querySelector('.pin-result');
  out.textContent = '';
  out.className = 'pin-result ' + (ok ? 'ok' : 'no');
  out.appendChild(iconClone(ok ? 'success' : 'error'));
  out.appendChild(el('span', {}, text));
}

async function checkPincode(form) {
  const input = form.querySelector('input[name="pincode"]');
  const pin = input.value.trim();
  if (!/^[1-9]\d{5}$/.test(pin)) {
    showPinResult(form, false, 'Enter a 6-digit pincode.');
    input.focus();
    return;
  }
  try {
    const res = await fetch(`${form.action}?pincode=${encodeURIComponent(pin)}`, { headers: { Accept: 'application/json' } });
    const q = await res.json();
    if (!q.ok) { showPinResult(form, false, q.message); return; }
    showPinResult(form, true, pinSummary(q));
    storage('set', q);
    applySavedPin(q);
  } catch (e) {
    showPinResult(form, false, 'Could not check right now. Please try again.');
  }
}

/* ─── Search suggestions ─────────────────────────────────────── */
function setupSearch() {
  const input = document.getElementById('nav-search');
  const box = document.getElementById('nav-search-results');
  if (!input || !box) return;
  let timer;
  const hide = () => { box.classList.remove('open'); box.textContent = ''; };
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (q.length < 2) { hide(); return; }
    timer = setTimeout(async () => {
      try {
        const data = await (await fetch('/products/autocomplete/?q=' + encodeURIComponent(q))).json();
        box.textContent = '';
        if (!data.results.length) { hide(); return; }
        data.results.forEach(p => {
          const a = el('a', { href: p.url, role: 'option' });
          const img = el('img', { src: p.image, alt: '', width: '40', height: '40' });
          const text = el('div');
          text.append(el('div', { class: 'r-name' }, p.name), el('div', { class: 'r-meta' }, `${rupees(p.price)} · ${p.category}`));
          a.append(img, text);
          box.appendChild(a);
        });
        box.classList.add('open');
      } catch (e) { hide(); }
    }, 200);
  });
  input.addEventListener('keydown', e => { if (e.key === 'Escape') hide(); });
  document.addEventListener('click', e => { if (!box.contains(e.target) && e.target !== input) hide(); });
}

/* ─── Disclosure helper: a button that opens/closes a panel ──── */
function toggle(button, panel, open) {
  const next = open !== undefined ? open : button.getAttribute('aria-expanded') !== 'true';
  document.querySelectorAll(`[aria-controls="${panel.id}"]`).forEach(b => b.setAttribute('aria-expanded', String(next)));
  return next;
}

document.addEventListener('DOMContentLoaded', () => {
  /* Header shadow once the page scrolls */
  const navbar = document.querySelector('.navbar');
  const backTop = document.getElementById('back-to-top');
  window.addEventListener('scroll', () => {
    if (navbar) navbar.classList.toggle('scrolled', window.scrollY > 10);
    if (backTop) backTop.classList.toggle('show', window.scrollY > 600);
  }, { passive: true });
  if (backTop) backTop.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));

  /* Phone menu */
  const burger = document.getElementById('hamburger-btn');
  const menu = document.getElementById('mobile-menu');
  if (burger && menu) {
    burger.addEventListener('click', () => menu.classList.toggle('open', toggle(burger, menu)));
  }

  /* Occasions dropdown (also opens on hover/focus via CSS) */
  document.querySelectorAll('[data-dropdown]').forEach(btn => {
    const panel = document.getElementById(btn.getAttribute('aria-controls'));
    btn.addEventListener('click', () => panel.classList.toggle('open', toggle(btn, panel)));
    document.addEventListener('click', e => {
      if (!btn.contains(e.target) && !panel.contains(e.target)) { panel.classList.remove('open'); toggle(btn, panel, false); }
    });
  });

  /* Pincode panel in the header */
  const pinPanel = document.getElementById('pin-panel');
  document.querySelectorAll('[data-pin-toggle]').forEach(btn => {
    btn.addEventListener('click', () => {
      const open = toggle(btn, pinPanel);
      pinPanel.hidden = !open;
      if (open) pinPanel.querySelector('input').focus();
    });
  });
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (pinPanel && !pinPanel.hidden) { pinPanel.hidden = true; toggle(document.querySelector('[data-pin-toggle]'), pinPanel, false); }
    document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));
  });

  /* Pincode checkers (header panel, home hero, …) */
  const savedPin = storage('get');
  applySavedPin(savedPin);
  document.querySelectorAll('[data-pin-check]').forEach(form => {
    form.addEventListener('submit', e => { e.preventDefault(); checkPincode(form); });
    if (savedPin && form.hasAttribute('data-pin-auto')) checkPincode(form);
  });

  setupSearch();

  /* Newsletter */
  const nl = document.getElementById('newsletter-form');
  if (nl) {
    nl.addEventListener('submit', async e => {
      e.preventDefault();
      const msg = nl.querySelector('.newsletter-msg');
      try {
        const res = await fetch(nl.action, { method: 'POST', body: new FormData(nl) });
        const data = await res.json();
        msg.textContent = data.message || 'Subscribed. Thank you!';
        if (res.ok) nl.reset();
      } catch (err) {
        msg.textContent = 'Could not subscribe right now. Please try again.';
      }
    });
  }

  /* Django messages → toasts */
  document.querySelectorAll('.django-message').forEach(m => {
    const type = (m.dataset.type || 'info').split(' ').pop();
    showToast(m.textContent.trim(), type);
    m.remove();
  });

  /* Scroll reveal (used by pages not yet redesigned) */
  const reveal = document.querySelectorAll('.reveal, .reveal-left, .reveal-right');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) { entry.target.classList.add('visible'); observer.unobserve(entry.target); }
      });
    }, { threshold: 0.12 });
    reveal.forEach(n => observer.observe(n));
  } else {
    reveal.forEach(n => n.classList.add('visible'));
  }

  /* Modals (customer pages) */
  document.querySelectorAll('[data-modal-open]').forEach(btn => {
    btn.addEventListener('click', () => {
      const modal = document.getElementById(btn.dataset.modalOpen);
      if (modal) modal.classList.add('open');
    });
  });
  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.classList.remove('open'); });
  });
  document.querySelectorAll('[data-modal-close]').forEach(btn => {
    btn.addEventListener('click', () => { const m = btn.closest('.modal-overlay'); if (m) m.classList.remove('open'); });
  });
});

/* ─── Quantity controls (product page) ───────────────────────── */
function changeQty(inputId, delta) {
  const input = document.getElementById(inputId);
  if (!input) return;
  input.value = Math.max(1, Math.min(99, (parseInt(input.value, 10) || 1) + delta));
}
window.changeQty = changeQty;

/* ─── Slide-in cart: "Add" without leaving the page ──────────── */
(function () {
  const drawer = document.getElementById('cart-drawer');
  const backdrop = document.querySelector('.drawer-backdrop');
  let lastFocus = null;

  function setCount(n) {
    document.querySelectorAll('.cart-btn').forEach(link => {
      let badge = link.querySelector('.cart-badge');
      if (!n) { if (badge) badge.remove(); }
      else {
        if (!badge) { badge = el('span', { class: 'cart-badge', 'aria-hidden': 'true' }); link.appendChild(badge); }
        badge.textContent = n;
      }
      link.setAttribute('aria-label', n ? `Cart, ${n} item${n === 1 ? '' : 's'}` : 'Cart');
    });
  }

  function open(message, ok) {
    lastFocus = document.activeElement;
    const status = drawer.querySelector('.drawer-status');
    status.textContent = '';
    status.className = 'drawer-status' + (ok ? '' : ' error');
    if (message) { status.appendChild(iconClone(ok ? 'success' : 'error')); status.appendChild(el('span', {}, message)); }
    drawer.hidden = false; backdrop.hidden = false;
    drawer.setAttribute('role', 'dialog'); drawer.setAttribute('aria-modal', 'true');
    drawer.querySelector('[data-cart-close]').focus();
  }
  function close() {
    drawer.hidden = true; backdrop.hidden = true;
    if (lastFocus) lastFocus.focus();
  }

  document.addEventListener('submit', async e => {
    const form = e.target.closest('form[data-ajax-cart]');
    if (!form || !drawer) return;          // logged out: let the form post and redirect to log in
    e.preventDefault();
    const btn = e.submitter || form.querySelector('[type="submit"]');
    if (btn) btn.disabled = true;
    try {
      const res = await fetch(form.action, {
        method: 'POST', body: new FormData(form),
        headers: { 'X-Requested-With': 'XMLHttpRequest', Accept: 'application/json' },
      });
      if (res.redirected || !(res.headers.get('content-type') || '').includes('json')) {
        window.location.href = res.url;      // e.g. session expired → login page
        return;
      }
      const data = await res.json();
      // Server-rendered partial (Django escapes all data in it).
      drawer.querySelector('[data-cart-body]').innerHTML = data.html;
      setCount(data.cart_count);
      open(data.message, data.ok);
    } catch (err) {
      form.submit();                          // network hiccup: fall back to a normal post
    } finally {
      if (btn) btn.disabled = false;
    }
  });

  if (drawer) {
    document.querySelectorAll('[data-cart-close]').forEach(b => b.addEventListener('click', close));
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && !drawer.hidden) close(); });
  }
})();
