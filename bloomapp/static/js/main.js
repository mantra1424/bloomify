/* ═══════════════════════════════════════════════════
   Bloomify – main.js  (Navbar · Toasts · Scroll fx)
   ═══════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {

  /* ─── Sticky navbar shadow ───────────────────────── */
  const navbar = document.querySelector('.navbar');
  if (navbar) {
    window.addEventListener('scroll', () => {
      navbar.classList.toggle('scrolled', window.scrollY > 20);
    });
  }

  /* ─── Hamburger menu ─────────────────────────────── */
  const hamburger = document.querySelector('.hamburger');
  const mobileMenu = document.querySelector('.mobile-menu');
  if (hamburger && mobileMenu) {
    hamburger.addEventListener('click', () => {
      mobileMenu.classList.toggle('open');
    });
  }

  /* ─── Button ripple effect ───────────────────────── */
  document.querySelectorAll('.btn').forEach(btn => {
    btn.addEventListener('click', function(e) {
      const rect = this.getBoundingClientRect();
      const ripple = document.createElement('span');
      ripple.classList.add('ripple');
      const size = Math.max(rect.width, rect.height);
      ripple.style.cssText = `
        width:${size}px; height:${size}px;
        left:${e.clientX - rect.left - size/2}px;
        top:${e.clientY - rect.top - size/2}px;
      `;
      this.appendChild(ripple);
      setTimeout(() => ripple.remove(), 600);
    });
  });

  /* ─── Scroll reveal animations ───────────────────── */
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });

  document.querySelectorAll('.reveal, .reveal-left, .reveal-right').forEach(el => {
    observer.observe(el);
  });

  /* ─── Floating petals (hero only) ───────────────── */
  const heroSection = document.querySelector('.hero-section');
  if (heroSection) {
    const petals = ['🌸', '🌺', '🌼', '🌷', '🌹', '💐'];
    for (let i = 0; i < 18; i++) {
      const petal = document.createElement('div');
      petal.classList.add('petal');
      petal.textContent = petals[Math.floor(Math.random() * petals.length)];
      petal.style.cssText = `
        left: ${Math.random() * 100}%;
        font-size: ${0.8 + Math.random() * 1.2}rem;
        animation-duration: ${6 + Math.random() * 8}s;
        animation-delay: ${Math.random() * 8}s;
      `;
      heroSection.appendChild(petal);
    }
  }

  /* ─── Auto-dismiss Django messages as toasts ─────── */
  document.querySelectorAll('.django-message').forEach(msgEl => {
    const type = msgEl.dataset.type || 'info';
    const text = msgEl.textContent.trim();
    showToast(text, type);
    msgEl.remove();
  });

  /* ─── Page enter animation ───────────────────────── */
  document.body.classList.add('page-enter');
});

/* ─── Toast System ───────────────────────────────────── */
function showToast(message, type = 'success', duration = 4000) {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.classList.add('toast-container');
    document.body.appendChild(container);
  }

  const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
  const titles = { success: 'Success', error: 'Error', warning: 'Warning', info: 'Info' };

  const toast = document.createElement('div');
  toast.classList.add('toast', type);
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || '🌸'}</span>
    <div class="toast-body">
      <div class="toast-title">${titles[type] || 'Notice'}</div>
      <div class="toast-msg">${message}</div>
    </div>
    <button class="toast-close" onclick="this.closest('.toast').remove()">✕</button>
  `;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('hide');
    setTimeout(() => toast.remove(), 350);
  }, duration);
}

/* ─── Quantity Controls ──────────────────────────────── */
function changeQty(inputId, delta) {
  const input = document.getElementById(inputId);
  if (!input) return;
  let val = parseInt(input.value) + delta;
  val = Math.max(1, Math.min(99, val));
  input.value = val;
}

/* ─── Modal System (customer pages) ─────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  // Open
  document.querySelectorAll('[data-modal-open]').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.modalOpen;
      const modal = document.getElementById(id);
      if (modal) modal.classList.add('open');
    });
  });
  // Close via backdrop or close button
  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.classList.remove('open');
    });
  });
  document.querySelectorAll('[data-modal-close]').forEach(btn => {
    btn.addEventListener('click', () => {
      const modal = btn.closest('.modal-overlay');
      if (modal) modal.classList.remove('open');
    });
  });
  // ESC key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      document.querySelectorAll('.modal-overlay.open').forEach(m => m.classList.remove('open'));
    }
  });
});
