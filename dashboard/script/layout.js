// Shared topbar + accounts modal. Each page needs <div id="app-nav"></div> and calls renderLayout('<page>').
function renderLayout(activePage) {
  const pages = [['index.html', 'dashboard'], ['transactions.html', 'transactions'], ['uploads.html', 'uploads']];
  document.getElementById('app-nav').innerHTML = `
    <header class="topbar"><div class="shell topbar-inner">
      <a class="brand" href="index.html"><span class="brand-mark" aria-hidden="true">${escapeHtml(LABELS.appName.charAt(0))}</span>${escapeHtml(LABELS.appName)}</a>
      <nav class="topnav" aria-label="Navigasi utama">
        ${pages.map(([href, key]) => `<a href="${href}" class="${key === activePage ? 'active' : ''}" ${key === activePage ? 'aria-current="page"' : ''}>${escapeHtml(LABELS.nav[key])}</a>`).join('')}
        <button id="open-accounts" type="button">${escapeHtml(LABELS.nav.accounts)}</button>
      </nav>
      <div id="connection" class="connection"><span class="dot"></span><span></span></div>
    </div></header>`;
  document.getElementById('open-accounts').addEventListener('click', openAccountsModal);
  updateConnection();
  setInterval(updateConnection, 15000);
}

async function updateConnection() {
  const el = document.getElementById('connection');
  if (!el) return;
  const ok = await Api.health();
  el.children[0].className = `dot ${ok ? 'online' : 'offline'}`;
  el.children[1].textContent = ok ? LABELS.online : LABELS.offline;
}

/* ---------- Accounts modal ---------- */
let accountsDialog = null;
let accountList = [];
let editingAccount = null;

function ensureAccountsDialog() {
  if (accountsDialog) return accountsDialog;
  accountsDialog = document.createElement('dialog');
  accountsDialog.className = 'modal';
  accountsDialog.innerHTML = `
    <div class="modal-box max-w-2xl">
      <form method="dialog"><button class="btn btn-sm btn-circle btn-ghost absolute right-2 top-2" aria-label="${LABELS.close}">✕</button></form>
      <h2 class="text-lg font-semibold">${escapeHtml(LABELS.accounts.title)}</h2>
      <p class="text-sm text-base-content/60 mb-3">${escapeHtml(LABELS.accounts.hint)}</p>
      <div id="acc-error" class="callout error hidden" role="alert"></div>
      <div id="acc-list"></div>
      <form id="acc-form" class="hidden mt-4 grid gap-2 border-t border-base-300 pt-4">
        <label class="field"><span>${LABELS.accounts.bank_name}</span><input name="bank_name" required maxlength="255"></label>
        <label class="field"><span>${LABELS.accounts.account_name}</span><input name="account_name" required maxlength="255"></label>
        <label class="field"><span>${LABELS.accounts.account_number}</span><input name="account_number" required maxlength="100"></label>
        <div class="flex gap-2"><button class="btn btn-sm btn-primary" type="submit">${LABELS.save}</button><button class="btn btn-sm btn-ghost" type="button" id="acc-cancel">${LABELS.cancel}</button></div>
      </form>
    </div>
    <form method="dialog" class="modal-backdrop"><button>${LABELS.close}</button></form>`;
  document.body.appendChild(accountsDialog);
  accountsDialog.querySelector('#acc-cancel').onclick = () => { editingAccount = null; accountsDialog.querySelector('#acc-form').classList.add('hidden'); };
  accountsDialog.querySelector('#acc-form').onsubmit = saveAccount;
  accountsDialog.querySelector('#acc-list').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-index]');
    if (!btn) return;
    editingAccount = accountList[Number(btn.dataset.index)];
    const form = accountsDialog.querySelector('#acc-form');
    ['bank_name', 'account_name', 'account_number'].forEach((k) => { form.elements[k].value = editingAccount[k] ?? ''; });
    form.classList.remove('hidden');
  });
  return accountsDialog;
}

function showAccountsError(message) {
  const el = accountsDialog.querySelector('#acc-error');
  el.textContent = message || '';
  el.classList.toggle('hidden', !message);
}

async function loadAccounts() {
  showAccountsError('');
  const list = accountsDialog.querySelector('#acc-list');
  list.textContent = LABELS.loading;
  try {
    accountList = await Api.listAccounts();
    list.innerHTML = accountList.length ? `
      <table class="data-table"><thead><tr><th>${LABELS.accounts.bank_name}</th><th>${LABELS.accounts.account_name}</th><th>${LABELS.accounts.account_number}</th><th></th></tr></thead>
      <tbody>${accountList.map((a, i) => `<tr><td>${escapeHtml(a.bank_name)}</td><td>${escapeHtml(a.account_name)}</td><td class="num">${escapeHtml(a.account_number)}</td>
        <td><button type="button" class="btn btn-xs btn-ghost" data-index="${i}">${LABELS.edit}</button></td></tr>`).join('')}</tbody></table>`
      : `<p class="text-sm text-base-content/60">${LABELS.accounts.empty}</p>`;
  } catch (e) {
    list.textContent = '';
    showAccountsError(LABELS.error('Gagal memuat rekening', e.message));
  }
}

async function saveAccount(event) {
  event.preventDefault();
  const next = Object.fromEntries(new FormData(event.currentTarget).entries());
  Object.keys(next).forEach((k) => { next[k] = next[k].trim(); });
  if (Object.values(next).some((v) => !v)) return showAccountsError(LABELS.accounts.required);
  try {
    await Api.updateAccount({
      current_account_number: editingAccount.account_number,
      current_account_name: editingAccount.account_name,
      current_bank_name: editingAccount.bank_name,
      ...next,
    });
    editingAccount = null;
    accountsDialog.querySelector('#acc-form').classList.add('hidden');
    await loadAccounts();
  } catch (e) {
    showAccountsError(LABELS.error('Gagal menyimpan rekening', e.message));
  }
}

function openAccountsModal() {
  ensureAccountsDialog().showModal();
  loadAccounts();
}
