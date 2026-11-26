// Transaction detail + edit modal, shared by all pages.
// Usage: openTransactionDetail(idOrTransaction, { onSaved: (updatedTransaction) => { ... } })
const NULLABLE_FIELDS = ['transaction_id', 'source_bank', 'source_account_number', 'source_account_name',
  'beneficiary_bank', 'beneficiary_account_number', 'benecifiacry_account_name'];

let detailDialog = null;
let activeTransaction = null;
let onSavedCallback = null;

function ensureDetailDialog() {
  if (detailDialog) return detailDialog;
  detailDialog = document.createElement('dialog');
  detailDialog.className = 'modal';
  detailDialog.innerHTML = `
    <div class="modal-box max-w-5xl">
      <form method="dialog"><button class="btn btn-sm btn-circle btn-ghost absolute right-2 top-2" aria-label="${LABELS.close}">✕</button></form>
      <div id="detail-body"></div>
    </div>
    <form method="dialog" class="modal-backdrop"><button>${LABELS.close}</button></form>`;
  document.body.appendChild(detailDialog);
  return detailDialog;
}

async function openTransactionDetail(idOrTransaction, options = {}) {
  onSavedCallback = options.onSaved || null;
  const dialog = ensureDetailDialog();
  const body = dialog.querySelector('#detail-body');
  body.textContent = LABELS.loading;
  if (!dialog.open) dialog.showModal();
  try {
    activeTransaction = typeof idOrTransaction === 'object' ? idOrTransaction : await Api.getTransaction(idOrTransaction);
    renderTransactionDetail(false);
  } catch (e) {
    body.innerHTML = `<div class="callout error">${escapeHtml(LABELS.error('Gagal memuat transaksi', e.message))}</div>`;
  }
}

function detailItem(label, value, wide = false) {
  return `<div class="detail-item${wide ? ' wide' : ''}"><dt>${escapeHtml(label)}</dt><dd>${value ? escapeHtml(value) : `<span class="muted-text">${LABELS.empty}</span>`}</dd></div>`;
}

function renderTransactionDetail(editing) {
  const tx = activeTransaction;
  const F = LABELS.fields;
  const reviewItems = [...getReviewReasons(tx).map(labelReviewReason), ...getReviewFlags(tx).map(labelReviewFlag)];
  const amount = formatRupiah(tx.amount);
  const view = `
    ${reviewItems.length ? `<div class="callout">${LABELS.needsReview}: ${escapeHtml(reviewItems.join(', '))}.</div>` : ''}
    <dl class="detail-grid">
      ${detailItem(F.transaction_date, formatDate(tx.transaction_date, true))}
      ${detailItem(F.transaction_type, tx.transaction_type ? labelType(tx.transaction_type) : '')}
      ${detailItem(F.category, labelCategory(tx.category))}
      ${detailItem(F.sub_category, labelCategory(tx.sub_category))}
      ${detailItem(F.description, tx.description, true)}
      ${detailItem(F.transaction_id, tx.transaction_id)}
      ${detailItem(F.created_at, formatDate(tx.created_at, true))}
      ${detailItem(F.source_bank, [tx.source_bank, tx.source_account_number, tx.source_account_name].filter(Boolean).join(' · '), true)}
      ${detailItem(F.beneficiary_bank, [tx.beneficiary_bank, tx.beneficiary_account_number, tx.benecifiacry_account_name].filter(Boolean).join(' · '), true)}
    </dl>
    <button id="detail-edit" type="button" class="btn btn-sm btn-outline mt-4">${LABELS.edit}</button>`;
  const field = (name, max, { wide = false, free = false } = {}) => `<label class="field${wide ? ' wide' : ''}"${free ? ' data-source-free' : ''}><span>${F[name]}</span><input name="${name}" value="${escapeHtml(tx[name] ?? '')}" maxlength="${max}"></label>`;
  const form = `
    <form id="detail-form" class="edit-grid">
      <label class="field"><span>${F.transaction_date}</span><input type="datetime-local" name="transaction_date" value="${toDatetimeLocalValue(tx.transaction_date)}"></label>
      ${field('transaction_id', 255)}
      <label class="field wide"><span>${F.description}</span><textarea name="description" required maxlength="10000" rows="2">${escapeHtml(tx.description ?? '')}</textarea></label>
      <label class="field"><span>${F.transaction_type}</span><select name="transaction_type">${Object.keys(LABELS.type).map((t) => `<option value="${t}" ${t === tx.transaction_type ? 'selected' : ''}>${LABELS.type[t]}</option>`).join('')}</select></label>
      <label class="field"><span>${F.amount}</span><input type="number" name="amount" min="0" step="0.01" value="${escapeHtml(tx.amount ?? '')}"></label>
      <label class="field"><span>${F.category}</span><select name="category">${categoryOptionsHtml(categoriesForType(tx.transaction_type), tx.category)}</select></label>
      <label class="field"><span>${F.sub_category}</span><select name="sub_category">${categoryOptionsHtml(subCategoriesFor(tx.category, tx.transaction_type), tx.sub_category)}</select></label>
      <p id="category-hint" class="wide note-line" ${tx.transaction_type === 'TRANSFER' ? '' : 'hidden'}>${LABELS.categoryForm.transferHint}</p>
      <label class="field wide" id="source-picker-field"><span>${LABELS.sourcePicker.label}</span><select name="source_pick" disabled><option>${LABELS.sourcePicker.loading}</option></select></label>
      <p id="source-fill-hint" class="wide note-line" hidden>${LABELS.sourcePicker.fillHint}</p>
      <p id="source-msg" class="wide note-line" hidden></p>
      ${field('source_bank', 255, { free: true })}${field('source_account_number', 100, { free: true })}${field('source_account_name', 255, { wide: true, free: true })}
      ${field('beneficiary_bank', 255)}${field('beneficiary_account_number', 100)}${field('benecifiacry_account_name', 255, { wide: true })}
      <p id="detail-msg" class="wide text-sm" role="alert"></p>
      <div class="wide flex gap-2"><button class="btn btn-sm btn-primary" type="submit">${LABELS.save}</button><button class="btn btn-sm btn-ghost" type="button" id="detail-cancel">${LABELS.cancel}</button></div>
    </form>`;
  const confirmPanel = `
    <div id="detail-confirm" class="confirm-panel" role="group" aria-labelledby="confirm-title" hidden>
      <h3 id="confirm-title" class="confirm-title" tabindex="-1">${LABELS.confirm.title}</h3>
      <p class="note-line">${LABELS.confirm.lead}</p>
      <div id="confirm-changes"></div>
      <p id="confirm-msg" class="text-sm" role="alert"></p>
      <div class="flex gap-2 mt-3"><button class="btn btn-sm btn-primary" type="button" id="confirm-save">${LABELS.confirm.yes}</button><button class="btn btn-sm btn-ghost" type="button" id="confirm-back">${LABELS.confirm.back}</button></div>
    </div>`;
  detailDialog.querySelector('#detail-body').innerHTML = `
    <div class="detail-layout">
      <div class="receipt-frame">
        <img id="detail-image" src="${Api.receiptUrl(tx.id)}" alt="Gambar struk" class="receipt-image">
        <p id="detail-image-missing" class="muted-text" hidden>${LABELS.receiptMissing}</p>
      </div>
      <div>
        <h2 class="detail-title">Transaksi #${escapeHtml(tx.id)}</h2>
        <p class="detail-amount">${amount ? escapeHtml(amount) : `<span class="muted-text" style="font-size:16px">${LABELS.noAmount}</span>`}</p>
        ${editing ? form + confirmPanel : view}
      </div>
    </div>`;
  const img = detailDialog.querySelector('#detail-image');
  img.onerror = () => { img.hidden = true; detailDialog.querySelector('#detail-image-missing').hidden = false; };
  if (editing) {
    detailDialog.querySelector('#detail-cancel').onclick = () => renderTransactionDetail(false);
    detailDialog.querySelector('#detail-form').onsubmit = submitTransactionEdit;
    const editForm = detailDialog.querySelector('#detail-form');
    wireCategorySelects(editForm);
    setupSourcePicker(editForm, tx);
  } else {
    detailDialog.querySelector('#detail-edit').onclick = () => renderTransactionDetail(true);
  }
}

// Dependent dropdowns: category options follow the transaction type, sub category options follow the category.
// A stored value that is not in the table (old data, mismatched pair) stays visible and selected, marked as such,
// so opening the form never changes it silently.
function categoryOptionsHtml(values, selected) {
  const stale = Boolean(selected) && !values.includes(selected);
  const list = stale ? [...values, selected] : values;
  return list.map((v) => {
    const label = stale && v === selected ? LABELS.categoryForm.notInTable(v) : labelCategory(v);
    return `<option value="${escapeHtml(v)}"${v === selected ? ' selected' : ''}>${escapeHtml(label)}</option>`;
  }).join('');
}

function wireCategorySelects(form) {
  const typeSelect = form.elements.transaction_type;
  const categorySelect = form.elements.category;
  const subSelect = form.elements.sub_category;
  const hint = form.querySelector('#category-hint');
  const refreshSub = (preferred) => {
    const options = subCategoriesFor(categorySelect.value, typeSelect.value);
    let selected = UNCATEGORIZED;
    if (options.includes(preferred)) selected = preferred;
    else if (options.length === 2) selected = options[1]; // only one real choice, e.g. Persediaan > Bahan Baku
    subSelect.innerHTML = categoryOptionsHtml(options, selected);
  };
  const refreshCategory = (preferred) => {
    const options = categoriesForType(typeSelect.value);
    categorySelect.innerHTML = categoryOptionsHtml(options, options.includes(preferred) ? preferred : UNCATEGORIZED);
    refreshSub(subSelect.value);
  };
  typeSelect.onchange = () => { refreshCategory(categorySelect.value); hint.hidden = typeSelect.value !== 'TRANSFER'; };
  categorySelect.onchange = () => refreshSub(subSelect.value);
}

// "Rekening sumber": for EXPENSES and TRANSFER the money leaves one of our own accounts, so the source is picked from
// the registered accounts (or cash) and the three source_* fields are filled together. For INCOMING the sender belongs to
// someone else, so the fields stay manual. If the account list cannot be loaded, the manual fields are the fallback.
const SOURCE_FIELDS = ['source_bank', 'source_account_number', 'source_account_name'];
const sourceText = (tx) => SOURCE_FIELDS.map((name) => tx[name]).filter(Boolean).join(' · ');
const isCashSource = (tx) => normalizeKey(tx.source_bank) === normalizeKey(LABELS.cashSource);

function accountLabel(account) {
  const base = `${account.bank_name || LABELS.empty} – ${account.account_name || LABELS.empty}`;
  return digitsOf(account.account_number) ? base : `${base} (${LABELS.sourcePicker.noNumber})`;
}

// Number first, then bank and holder name (see accountMatchIndex).
const findSourceAccount = (tx, accounts) => accountMatchIndex(accounts, tx.source_bank, tx.source_account_number, tx.source_account_name);

function sourcePickerState(tx, accounts) {
  const options = [{ value: '', label: LABELS.sourcePicker.empty }, { value: 'cash', label: LABELS.cashSource },
    ...accounts.map((a, i) => ({ value: `acc:${i}`, label: accountLabel(a) }))];
  let selected = '';
  let fill = false; // recognised by bank and name only: saving stores the registered account number
  if (isCashSource(tx)) selected = 'cash';
  else if (hasSource(tx)) {
    const index = findSourceAccount(tx, accounts);
    if (index >= 0) {
      selected = `acc:${index}`;
      fill = !digitsOf(tx.source_account_number) && Boolean(digitsOf(accounts[index].account_number));
    } else { // keep what is stored, e.g. an OCR value that is not one of our accounts
      selected = 'current';
      options.push({ value: 'current', label: LABELS.sourcePicker.current(sourceText(tx)) });
    }
  }
  return { options, selected, fill };
}

const refreshFillHint = (form) => {
  const select = form.elements.source_pick;
  form.querySelector('#source-fill-hint').hidden = !(sourcePickerActive(form) && !select.disabled
    && select.dataset.fill === '1' && select.value === select.dataset.initial);
};

function applySourceMode(form) {
  const failed = form.dataset.accountsFailed === '1';
  const incoming = form.elements.transaction_type.value === 'INCOMING';
  const manual = failed || incoming;
  form.querySelector('#source-picker-field').hidden = manual;
  form.querySelectorAll('[data-source-free]').forEach((el) => { el.hidden = !manual; });
  const message = form.querySelector('#source-msg');
  message.textContent = failed ? LABELS.sourcePicker.loadError : (incoming ? LABELS.sourcePicker.incomingHint : '');
  message.hidden = !message.textContent;
  refreshFillHint(form);
}

async function setupSourcePicker(form, tx) {
  form.elements.transaction_type.addEventListener('change', () => applySourceMode(form));
  applySourceMode(form);
  const select = form.elements.source_pick;
  let accounts;
  try {
    accounts = await Api.listAccounts();
  } catch {
    if (!form.isConnected) return;
    form.dataset.accountsFailed = '1';
    applySourceMode(form);
    return;
  }
  if (!form.isConnected) return; // the form was re-rendered while the list was loading
  form._accounts = accounts;
  const { options, selected, fill } = sourcePickerState(tx, accounts);
  select.innerHTML = options.map((o) => `<option value="${escapeHtml(o.value)}"${o.value === selected ? ' selected' : ''}>${escapeHtml(o.label)}</option>`).join('');
  select.dataset.initial = selected;
  select.dataset.fill = fill ? '1' : '';
  select.disabled = false;
  select.addEventListener('change', () => refreshFillHint(form));
  refreshFillHint(form);
}

const sourcePickerActive = (form) => form.dataset.accountsFailed !== '1' && form.elements.transaction_type.value !== 'INCOMING';

// Source fields to send for the picker. Nothing is sent unless the person changed the selection,
// so saving another edit never rewrites how the OCR spelled the bank or holder name. The one exception is an account
// recognised by bank and name only: saving then stores the registered number (the form says so under the picker).
function sourceChangesFromPicker(form, tx) {
  const select = form.elements.source_pick;
  if (select.disabled || !form._accounts || select.value === 'current') return {};
  if (select.value === select.dataset.initial && select.dataset.fill !== '1') return {}; // untouched: keep the stored spelling
  let next = { source_bank: null, source_account_number: null, source_account_name: null };
  if (select.value === 'cash') next.source_bank = LABELS.cashSource;
  else if (select.value.startsWith('acc:')) {
    const account = form._accounts[Number(select.value.slice(4))];
    next = { source_bank: account.bank_name || null, source_account_number: account.account_number || null, source_account_name: account.account_name || null };
  }
  return Object.fromEntries(SOURCE_FIELDS.filter((name) => (next[name] ?? null) !== (tx[name] ?? null)).map((name) => [name, next[name]]));
}

// Only changed fields are sent; emptied optional fields become null.
// category and sub_category are always sent together, because the backend does not check them as a pair.
function buildTransactionPayload(form, tx) {
  const payload = {};
  const data = new FormData(form);
  const pickerActive = sourcePickerActive(form);
  for (const [name, raw] of data.entries()) {
    if (name === 'source_pick' || (pickerActive && SOURCE_FIELDS.includes(name))) continue;
    let value = String(raw);
    if (name === 'transaction_date') {
      if (value !== toDatetimeLocalValue(tx.transaction_date)) payload[name] = fromDatetimeLocalValue(value);
      continue;
    }
    if (NULLABLE_FIELDS.includes(name)) value = value.trim() || null;
    else if (name === 'amount') value = value === '' ? null : value;
    else if (name === 'description') value = value.trim();
    const previous = tx[name];
    const unchanged = value === null ? previous == null : String(value) === String(previous ?? '');
    if (!unchanged) payload[name] = value;
  }
  if (pickerActive) Object.assign(payload, sourceChangesFromPicker(form, tx));
  if ('category' in payload || 'sub_category' in payload) {
    payload.category = String(data.get('category'));
    payload.sub_category = String(data.get('sub_category'));
  }
  return payload;
}

// What is about to be saved, as "label: before → after" rows. The three source fields and the three destination
// fields are each shown as one row, so choosing an account reads as one change.
function changeRows(payload, tx) {
  const merged = { ...tx, ...payload };
  const F = LABELS.fields;
  const text = {
    transaction_date: (t) => formatDate(t.transaction_date, true),
    transaction_type: (t) => (t.transaction_type ? labelType(t.transaction_type) : ''),
    amount: (t) => formatRupiah(t.amount) || '',
    category: (t) => (t.category ? labelCategory(t.category) : ''),
    sub_category: (t) => (t.sub_category ? labelCategory(t.sub_category) : ''),
  };
  const single = ['transaction_date', 'transaction_id', 'description', 'transaction_type', 'amount', 'category', 'sub_category']
    .filter((name) => name in payload)
    .map((name) => ({ label: F[name], before: text[name] ? text[name](tx) : tx[name], after: text[name] ? text[name](merged) : merged[name] }));
  const joined = (t, names) => names.map((name) => t[name]).filter(Boolean).join(' · ');
  const destination = ['beneficiary_bank', 'beneficiary_account_number', 'benecifiacry_account_name'];
  const groups = [
    { label: LABELS.sourcePicker.label, names: SOURCE_FIELDS },
    { label: LABELS.confirm.destination, names: destination },
  ].filter((g) => g.names.some((name) => name in payload))
    .map((g) => ({ label: g.label, before: joined(tx, g.names), after: joined(merged, g.names) }));
  return [...single, ...groups];
}

function showSaveConfirmation(form, payload) {
  const panel = detailDialog.querySelector('#detail-confirm');
  const C = LABELS.confirm;
  const value = (v) => escapeHtml(v || LABELS.empty);
  panel.querySelector('#confirm-changes').innerHTML = changeRows(payload, activeTransaction).map((row) => `
    <div class="change-row">
      <div class="change-label">${escapeHtml(row.label)}</div>
      <div class="change-values"><span class="sr-only">${C.from}</span><span class="change-old">${value(row.before)}</span>
        <span class="change-arrow" aria-hidden="true">→</span><span class="sr-only">${C.to}</span><span class="change-new">${value(row.after)}</span></div>
    </div>`).join('');
  panel.querySelector('#confirm-msg').textContent = '';
  panel.querySelectorAll('button').forEach((b) => { b.disabled = false; });
  panel.querySelector('#confirm-save').onclick = () => saveTransactionEdit(payload);
  panel.querySelector('#confirm-back').onclick = () => { panel.hidden = true; form.hidden = false; }; // the form keeps what was typed
  form.hidden = true;
  panel.hidden = false;
  panel.querySelector('#confirm-title').focus();
}

async function saveTransactionEdit(payload) {
  const panel = detailDialog.querySelector('#detail-confirm');
  const message = panel.querySelector('#confirm-msg');
  const buttons = panel.querySelectorAll('button');
  buttons.forEach((b) => { b.disabled = true; });
  try {
    await Api.updateTransaction(activeTransaction.id, payload);
    activeTransaction = await Api.getTransaction(activeTransaction.id);
    renderTransactionDetail(false);
    if (onSavedCallback) onSavedCallback(activeTransaction);
  } catch (e) {
    message.className = 'text-sm text-error';
    message.textContent = LABELS.error('Gagal menyimpan', e.message);
    buttons.forEach((b) => { b.disabled = false; });
  }
}

// Saving always asks for confirmation first; nothing is sent until the person confirms.
function submitTransactionEdit(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const message = form.querySelector('#detail-msg');
  const payload = buildTransactionPayload(form, activeTransaction);
  if (!Object.keys(payload).length) { message.className = 'text-sm'; message.textContent = LABELS.noChanges; return; }
  message.textContent = '';
  showSaveConfirmation(form, payload);
}
