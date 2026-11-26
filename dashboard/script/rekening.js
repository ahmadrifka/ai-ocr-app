// Rekening (accounts) page – list, add, edit, delete.
(() => {
  let accounts = [];
  let editingAccount = null; // null = add mode, object = edit mode
  let deletingAccount = null;

  const $ = (sel) => document.querySelector(sel);

  // --- Load & render ---
  async function load() {
    const errorEl = $('#load-error');
    const tbody = $('#table-body');
    const state = $('#table-state');
    errorEl.hidden = true;
    tbody.innerHTML = '';
    state.textContent = LABELS.loading;
    try {
      accounts = await Api.listAccounts();
      state.textContent = '';
      if (!accounts.length) {
        state.innerHTML = `<span class="empty-icon">📋</span><strong>Belum ada rekening terdaftar.</strong><span>Tambah rekening perusahaan untuk memulai.</span>`;
        return;
      }
      tbody.innerHTML = accounts.map((a, i) => `
        <tr>
          <td>${escapeHtml(a.bank_name ?? '')}</td>
          <td>${escapeHtml(a.account_name ?? '')}</td>
          <td class="num">${escapeHtml(a.account_number ?? '')}</td>
          <td class="flex gap-1 justify-end">
            <button type="button" class="btn btn-xs btn-ghost" data-edit="${i}">Ubah</button>
            <button type="button" class="btn btn-xs btn-ghost text-red-600" data-delete="${i}">Hapus</button>
          </td>
        </tr>`).join('');
    } catch (e) {
      state.textContent = '';
      errorEl.textContent = LABELS.error('Gagal memuat rekening', e.message);
      errorEl.hidden = false;
    }
  }

  // --- Add / Edit dialog ---
  function openDialog(account) {
    editingAccount = account || null;
    const dialog = $('#account-dialog');
    const form = $('#account-form');
    const errorEl = $('#dialog-error');
    errorEl.classList.add('hidden');
    errorEl.textContent = '';
    $('#dialog-title').textContent = editingAccount ? 'Ubah rekening' : 'Tambah rekening';
    $('#dialog-submit').textContent = editingAccount ? 'Simpan perubahan' : 'Tambah';
    form.elements.bank_name.value = editingAccount?.bank_name ?? '';
    form.elements.account_name.value = editingAccount?.account_name ?? '';
    form.elements.account_number.value = editingAccount?.account_number ?? '';
    dialog.showModal();
  }

  async function saveAccount(e) {
    e.preventDefault();
    const form = $('#account-form');
    const errorEl = $('#dialog-error');
    errorEl.classList.add('hidden');
    const data = {
      bank_name: form.elements.bank_name.value.trim(),
      account_name: form.elements.account_name.value.trim(),
      account_number: form.elements.account_number.value.trim(),
    };
    if (!data.bank_name || !data.account_name || !data.account_number) {
      errorEl.textContent = LABELS.accounts.required;
      errorEl.classList.remove('hidden');
      return;
    }
    try {
      if (editingAccount) {
        await Api.updateAccount({
          current_account_number: editingAccount.account_number,
          current_account_name: editingAccount.account_name,
          current_bank_name: editingAccount.bank_name,
          ...data,
        });
      } else {
        await Api.createAccount(data);
      }
      $('#account-dialog').close();
      await load();
    } catch (err) {
      errorEl.textContent = LABELS.error('Gagal menyimpan rekening', err.message);
      errorEl.classList.remove('hidden');
    }
  }

  // --- Delete dialog ---
  function openDelete(account) {
    deletingAccount = account;
    const errorEl = $('#delete-error');
    errorEl.classList.add('hidden');
    errorEl.textContent = '';
    $('#delete-desc').textContent = `${account.bank_name ?? ''} — ${account.account_name ?? ''} (${account.account_number ?? ''})`;
    $('#delete-dialog').showModal();
  }

  async function confirmDelete() {
    if (!deletingAccount) return;
    const errorEl = $('#delete-error');
    errorEl.classList.add('hidden');
    try {
      await Api.deleteAccount({
        account_number: deletingAccount.account_number,
        account_name: deletingAccount.account_name,
        bank_name: deletingAccount.bank_name,
      });
      deletingAccount = null;
      $('#delete-dialog').close();
      await load();
    } catch (err) {
      errorEl.textContent = LABELS.error('Gagal menghapus rekening', err.message);
      errorEl.classList.remove('hidden');
    }
  }

  // --- Wire up ---
  renderLayout('rekening');

  $('#reload-button').addEventListener('click', load);
  $('#add-button').addEventListener('click', () => openDialog(null));
  $('#account-form').addEventListener('submit', saveAccount);
  $('#dialog-cancel').addEventListener('click', () => $('#account-dialog').close());
  $('#delete-confirm').addEventListener('click', confirmDelete);
  $('#delete-cancel').addEventListener('click', () => $('#delete-dialog').close());

  $('#table-body').addEventListener('click', (e) => {
    const editBtn = e.target.closest('[data-edit]');
    if (editBtn) return openDialog(accounts[Number(editBtn.dataset.edit)]);
    const delBtn = e.target.closest('[data-delete]');
    if (delBtn) return openDelete(accounts[Number(delBtn.dataset.delete)]);
  });

  load();
})();
