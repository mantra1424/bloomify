/* ═══════════════════════════════════════
   Bloomify – admin.js  (Charts + CRUD)
   ═══════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {

  /* ─── Admin sidebar toggle (mobile) ──── */
  const sidebarToggle = document.getElementById('sidebar-toggle');
  const adminSidebar  = document.querySelector('.admin-sidebar');
  if (sidebarToggle && adminSidebar) {
    sidebarToggle.addEventListener('click', () => {
      adminSidebar.classList.toggle('open');
    });
  }

  /* ─── Admin search filter ───────────── */
  const searchInput = document.getElementById('admin-search');
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      const q = searchInput.value.toLowerCase();
      document.querySelectorAll('.admin-table tbody tr').forEach(row => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(q) ? '' : 'none';
      });
    });
  }

  /* ─── Confirm delete ────────────────── */
  document.querySelectorAll('[data-confirm]').forEach(el => {
    el.addEventListener('click', (e) => {
      if (!confirm(el.dataset.confirm || 'Are you sure?')) {
        e.preventDefault();
      }
    });
  });

  /* ─── Load analytics charts ─────────── */
  if (document.getElementById('revenueChart')) {
    loadAdminCharts();
  }

  /* ─── Modal open/close ──────────────── */
  document.querySelectorAll('[data-modal-open]').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.modalOpen;
      openModal(id);
    });
  });
  document.querySelectorAll('[data-modal-close], .modal-overlay').forEach(el => {
    el.addEventListener('click', (e) => {
      if (e.target === el) closeAllModals();
    });
  });
});

function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.add('open');
}
function closeAllModals() {
  document.querySelectorAll('.modal-overlay').forEach(m => m.classList.remove('open'));
}

/* ─── Fill edit modal with data ─────────── */
function fillEditModal(data) {
  const modal = document.getElementById('edit-modal');
  if (!modal) return;
  Object.entries(data).forEach(([key, val]) => {
    const el = modal.querySelector(`[name="${key}"]`);
    if (el) {
      if (el.type === 'checkbox') el.checked = !!val;
      else el.value = val;
    }
  });
  openModal('edit-modal');
}

async function loadAdminCharts() {
  try {
    const res = await fetch('/admin-panel/api/analytics/');
    const data = await res.json();
    renderCharts(data);
  } catch (e) {
    console.warn('Analytics load failed', e);
  }
}

function renderCharts(data) {
  const palette = {
    pink:  ['rgba(232,86,122,0.85)', 'rgba(212,64,106,0.85)', 'rgba(255,143,163,0.85)'],
    green: ['rgba(76,175,124,0.85)', 'rgba(56,160,101,0.85)'],
    gradient: null,
  };

  /* Revenue Bar Chart */
  const revCtx = document.getElementById('revenueChart').getContext('2d');
  const grad = revCtx.createLinearGradient(0, 0, 0, 300);
  grad.addColorStop(0, 'rgba(232,86,122,0.85)');
  grad.addColorStop(1, 'rgba(212,64,106,0.2)');

  new Chart(revCtx, {
    type: 'bar',
    data: {
      labels: data.revenue.labels,
      datasets: [{
        label: 'Revenue (₹)',
        data: data.revenue.data,
        backgroundColor: grad,
        borderColor: 'rgba(212,64,106,1)',
        borderWidth: 2,
        borderRadius: 8,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        y: { grid: { color: 'rgba(0,0,0,0.04)' }, ticks: { font: { size: 11 } } },
        x: { grid: { display: false }, ticks: { font: { size: 11 } } }
      }
    }
  });

  /* Category Doughnut */
  const catCtx = document.getElementById('categoryChart').getContext('2d');
  new Chart(catCtx, {
    type: 'doughnut',
    data: {
      labels: data.categories.labels,
      datasets: [{
        data: data.categories.data,
        backgroundColor: [
          'rgba(232,86,122,0.85)', 'rgba(76,175,124,0.85)',
          'rgba(251,191,36,0.85)', 'rgba(99,102,241,0.85)',
          'rgba(236,72,153,0.85)',
        ],
        borderWidth: 2, borderColor: 'white',
        hoverOffset: 8,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } }
      },
      cutout: '65%',
    }
  });

  /* Signups Line Chart */
  const sigCtx = document.getElementById('signupsChart');
  if (sigCtx) {
    new Chart(sigCtx.getContext('2d'), {
      type: 'line',
      data: {
        labels: data.signups.labels,
        datasets: [{
          label: 'New Users',
          data: data.signups.data,
          borderColor: 'rgba(76,175,124,1)',
          backgroundColor: 'rgba(76,175,124,0.12)',
          borderWidth: 2.5,
          pointBackgroundColor: 'white',
          pointBorderColor: 'rgba(76,175,124,1)',
          pointBorderWidth: 2,
          pointRadius: 5,
          tension: 0.42, fill: true,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: { grid: { color: 'rgba(0,0,0,0.04)' }, ticks: { font: { size: 11 } } },
          x: { grid: { display: false }, ticks: { font: { size: 11 } } }
        }
      }
    });
  }
}
