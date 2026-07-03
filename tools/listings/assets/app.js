'use strict';

// API base URL.
// When the backend serves this page directly (default setup), keep this empty
// so requests go to the same origin. If you host the frontend separately,
// change this to the full URL of your backend, e.g.
//   const API = 'https://api.yoursite.com';
const API = '';

// DOM refs
const form        = document.getElementById('listingForm');
const generateBtn = document.getElementById('generateBtn');
const copyBtn     = document.getElementById('copyBtn');
const copyText    = document.getElementById('copyText');

const emptyState   = document.getElementById('emptyState');
const listingOutput = document.getElementById('listingOutput');
const listingDesc  = document.getElementById('listingDesc');
const listingQuals = document.getElementById('listingQuals');
const errorState   = document.getElementById('errorState');
const errorMsg     = document.getElementById('errorMsg');

const charMeter    = document.getElementById('charMeter');
const totalCount   = document.getElementById('totalCount');
const descCount    = document.getElementById('descCount');
const qualCount    = document.getElementById('qualCount');
const progressFill = document.getElementById('progressFill');

const outputBody = document.getElementById('outputBody');

const headlineText     = document.getElementById('headlineText');
const headlineBlock    = document.getElementById('headlineBlock');
const headlineChars    = document.getElementById('headlineCharsDisplay');
const copyHeadlineBtn  = document.getElementById('copyHeadlineBtn');
const copyHeadlineText = document.getElementById('copyHeadlineText');

let currentFull = '';
let currentHeadline = '';

// Make sure only empty state shows on initial load
(function init() {
  emptyState.hidden = false;
  listingOutput.hidden = true;
  errorState.hidden = true;
  errorState.style.display = 'none';
  charMeter.hidden = true;
  copyBtn.disabled = true;
})();

// ---- Generate ----
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  await generate();
});

async function generate() {
  const data = {
    property_type: v('property_type'),
    beds:          v('beds'),
    baths:         v('baths'),
    available:     v('available'),
    neighborhood:  v('neighborhood'),
    interior:      v('interior'),
    exterior:      v('exterior'),
    area:          v('area'),
    extras:        v('extras'),
  };

  // Require at least some input
  const hasInput = Object.values(data).some(x => x.trim().length > 0);
  if (!hasInput) {
    showError('Please fill in at least one field before generating.');
    return;
  }

  setLoading(true);
  hideAll();
  showShimmer();

  try {
    const res = await fetch(`generate`, {
      // Same-origin call when API is empty
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Server error ${res.status}`);
    }

    const result = await res.json();
    showResult(result);
  } catch (err) {
    showError(err.message || 'Something went wrong. Please try again.');
  } finally {
    setLoading(false);
  }
}

function showResult(result) {
  clearShimmer();
  emptyState.hidden = true;
  errorState.hidden = true;
  listingOutput.hidden = false;

  // Headline
  currentHeadline = result.headline || '';
  if (currentHeadline) {
    headlineBlock.hidden = false;
    headlineText.textContent = currentHeadline;
    headlineChars.textContent = result.headline_chars + ' / 80 chars';
  } else {
    headlineBlock.hidden = true;
  }

  listingDesc.textContent = result.description;
  listingQuals.textContent = result.qualifications;
  currentFull = result.full_listing;

  // Update meter
  charMeter.hidden = false;
  const total = result.total_chars;
  const pct = Math.min((total / 1000) * 100, 100);

  totalCount.textContent = total;
  descCount.textContent = result.desc_chars;
  qualCount.textContent = result.qual_chars;
  progressFill.style.width = pct + '%';

  totalCount.classList.remove('warn', 'over');
  progressFill.classList.remove('warn', 'over');

  if (total > 1000) {
    totalCount.classList.add('over');
    progressFill.classList.add('over');
  } else if (total > 900) {
    totalCount.classList.add('warn');
    progressFill.classList.add('warn');
  }

  copyBtn.disabled = false;
}

function showError(msg) {
  clearShimmer();
  emptyState.hidden = true;
  listingOutput.hidden = true;
  errorState.hidden = false;
  errorState.style.display = '';
  errorMsg.textContent = msg;
  charMeter.hidden = true;
  copyBtn.disabled = true;
}

function hideAll() {
  emptyState.hidden = true;
  listingOutput.hidden = true;
  errorState.hidden = true;
  errorState.style.display = 'none';
}

function setLoading(on) {
  generateBtn.disabled = on;
  generateBtn.classList.toggle('loading', on);
  const spinner = generateBtn.querySelector('.btn-spinner');
  if (spinner) spinner.hidden = !on;
}

// ---- Shimmer ----
function showShimmer() {
  clearShimmer();
  const shimmerContainer = document.createElement('div');
  shimmerContainer.id = 'shimmerContainer';
  for (let i = 0; i < 6; i++) {
    const d = document.createElement('div');
    d.className = 'shimmer';
    shimmerContainer.appendChild(d);
  }
  outputBody.appendChild(shimmerContainer);
}

function clearShimmer() {
  const s = document.getElementById('shimmerContainer');
  if (s) s.remove();
}

// ---- Copy ----
copyBtn.addEventListener('click', () => {
  if (!currentFull) return;
  copyToClipboard(currentFull, copyBtn, copyText);
});

// ---- Copy headline ----
copyHeadlineBtn.addEventListener('click', () => {
  if (!currentHeadline) return;
  copyToClipboard(currentHeadline, copyHeadlineBtn, copyHeadlineText);
});

function copyToClipboard(text, btn, labelEl) {
  navigator.clipboard.writeText(text).then(() => {
    btn.classList.add('copied');
    labelEl.textContent = 'Copied';
    setTimeout(() => {
      btn.classList.remove('copied');
      labelEl.textContent = 'Copy';
    }, 2000);
  }).catch(() => {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    btn.classList.add('copied');
    labelEl.textContent = 'Copied';
    setTimeout(() => {
      btn.classList.remove('copied');
      labelEl.textContent = 'Copy';
    }, 2000);
  });
}

// ---- Helpers ----
function v(id) {
  const el = document.getElementById(id);
  return el ? el.value.trim() : '';
}

// ---- Dark mode ----
(function () {
  const btn = document.querySelector('[data-theme-toggle]');
  const root = document.documentElement;
  const prefersDark = matchMedia('(prefers-color-scheme: dark)').matches;
  let theme = prefersDark ? 'dark' : 'light';
  root.setAttribute('data-theme', theme);
  updateIcon();

  btn && btn.addEventListener('click', () => {
    theme = theme === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', theme);
    updateIcon();
  });

  function updateIcon() {
    if (!btn) return;
    btn.setAttribute('aria-label', `Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`);
    btn.innerHTML = theme === 'dark'
      ? '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>'
      : '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
  }
})();
