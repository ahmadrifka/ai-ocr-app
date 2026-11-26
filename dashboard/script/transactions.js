// Transactions page: client-side filtering over the full list (a few requests of 50).
// If the backend later supports filtering by account number and a total count, replace loadTransactions()/applyFilters().
const PAGE_CHUNK = 50;
const $ = (id) => document.getElementById(id);
let allTransactions = [];
let filteredTransactions = [];
let visibleCount = PAGE_CHUNK;
let filterAccounts = []; // registered accounts, used by the account filter
let filterAccountsLoaded = false;
let tabCounts = { review: 0, reviewed: 0, matched: 0 };
let activeTab = 'review'; // 'review' = needs review (not exported), 'reviewed' = complete (exportable)

renderLayout('transactions');

async function loadTransactions() {
  $('table-state').textContent = LABELS.loading;
  $('table-body').innerHTML = '';
  try {
    const [transactions, accounts] = await Promise.all([Api.listTransactions(), Api.listAccounts().catch(() => null)]);
    allTransactions = transactions;
    filterAccounts = accounts || [];
    filterAccountsLoaded = Boolean(accounts);
    populateFilterOptions();
    applyFilters();
  } catch (e) {
    $('table-state').textContent = LABELS.error(LABELS.transactions.loadError, e.message);
  }
}

function fillSelect(id, firstLabel, options) {
  const select = $(id);
  const current = select.value;
  select.innerHTML = `<option value="">${escapeHtml(firstLabel)}</option>` +
    options.map((o) => `<option value="${escapeHtml(o.value)}"${o.disabled ? ' disabled' : ''}>${escapeHtml(o.label)}</option>`).join('');
  select.value = options.some((o) => o.value === current && !o.disabled) ? current : '';
}

// Account filter: the options are our registered accounts and a transaction matches when its source or its
// destination is that account. The number decides when present; without a number, bank and holder name decide
// (see accountMatchIndex). The option value is the account's position in the registered list.
function fillAccountFilter() {
  $('filter-account').disabled = !filterAccountsLoaded;
  fillSelect('filter-account', filterAccountsLoaded ? LABELS.transactions.allAccounts : LABELS.transactions.accountsUnavailable,
    filterAccounts.map((a, i) => ({ value: String(i), label: accountLabel(a) })));
}

const transactionSides = (tx) => [
  [tx.source_bank, tx.source_account_number, tx.source_account_name],
  [tx.beneficiary_bank, tx.beneficiary_account_number, tx.benecifiacry_account_name],
];
const touchesAccount = (tx, index) => transactionSides(tx).some(([bank, number, name]) => accountMatchIndex(filterAccounts, bank, number, name) === index);

// Transactions recognised as one of our accounts only through bank and name, because the number is empty.
function countNameOnlyMatches() {
  return allTransactions.filter((tx) => transactionSides(tx)
    .some(([bank, number, name]) => !digitsOf(number) && accountMatchIndex(filterAccounts, bank, number, name) >= 0)).length;
}

function renderAccountNote() {
  const count = filterAccountsLoaded ? countNameOnlyMatches() : 0;
  $('account-note').textContent = count ? LABELS.transactions.nameOnlyNote(count) : '';
  $('account-note').hidden = !count;
}

// Sub categories follow the chosen category; values found in the data stay selectable (e.g. old values).
function subCategoryValues(category) {
  const fromData = allTransactions.filter((t) => !category || t.category === category).map((t) => t.sub_category).filter(Boolean);
  return uniqueValues([...(category ? subCategoriesFor(category, 'TRANSFER') : SUB_CATEGORIES), ...fromData]);
}
function fillSubCategoryFilter() {
  fillSelect('filter-subcategory', LABELS.transactions.allSubCategories,
    subCategoryValues($('filter-category').value).map((v) => ({ value: v, label: labelCategory(v) })));
}

function populateFilterOptions() {
  const categories = uniqueValues([...CATEGORIES, ...allTransactions.map((t) => t.category).filter(Boolean)]);
  fillAccountFilter();
  fillSelect('filter-category', LABELS.transactions.allCategories, categories.map((v) => ({ value: v, label: labelCategory(v) })));
  fillSubCategoryFilter();
  renderAccountNote();
}

function matchesFilters(tx, f) {
  if (f.account !== '' && !touchesAccount(tx, Number(f.account))) return false;
  if (f.category && tx.category !== f.category) return false;
  if (f.subCategory && tx.sub_category !== f.subCategory) return false;
  if (f.type && tx.transaction_type !== f.type) return false;
  if (f.from || f.to) {
    const day = toJakartaDay(tx.transaction_date);
    if (!day) return false; // transactions without a date never match a date range
    if (f.from && day < f.from) return false;
    if (f.to && day > f.to) return false;
  }
  if (f.search) {
    const haystack = [tx.description, tx.transaction_id, tx.source_bank, tx.beneficiary_bank,
      tx.source_account_name, tx.benecifiacry_account_name].join(' ').toLowerCase();
    if (!haystack.includes(f.search)) return false;
  }
  return true;
}

function sortValue(tx, mode) {
  if (mode.startsWith('date')) return tx.transaction_date ? new Date(tx.transaction_date).getTime() : null;
  return toNumber(tx.amount);
}

function applyFilters() {
  const f = {
    search: $('filter-search').value.trim().toLowerCase(),
    account: $('filter-account').value, category: $('filter-category').value, subCategory: $('filter-subcategory').value,
    type: $('filter-type').value, from: $('filter-from').value, to: $('filter-to').value,
  };
  const mode = $('filter-sort').value;
  const direction = mode.endsWith('asc') ? 1 : -1;
  const matched = allTransactions.filter((tx) => matchesFilters(tx, f)); // filters apply to both tabs
  const needReview = matched.filter(needsReview);
  tabCounts = { review: needReview.length, reviewed: matched.length - needReview.length, matched: matched.length };
  filteredTransactions = (activeTab === 'review' ? needReview : matched.filter((tx) => !needsReview(tx))).sort((a, b) => {
    const x = sortValue(a, mode), y = sortValue(b, mode);
    if (x === null && y === null) return 0;
    if (x === null) return 1; // empty values always sink to the bottom
    if (y === null) return -1;
    return (x - y) * direction;
  });
  visibleCount = PAGE_CHUNK;
  renderTabs();
  renderSummary();
  renderTable();
}

function renderTabs() {
  document.querySelectorAll('.review-tabs [data-tab]').forEach((tab) => tab.setAttribute('aria-selected', String(tab.dataset.tab === activeTab)));
  $('count-review').textContent = tabCounts.review;
  $('count-review').classList.toggle('has-items', tabCounts.review > 0);
  $('count-reviewed').textContent = tabCounts.reviewed;
  $('tab-note').textContent = LABELS.transactions.tabNote[activeTab];
  $('export-button').hidden = activeTab !== 'reviewed'; // only complete data is exported
  $('export-button').disabled = filteredTransactions.length === 0;
}

function sumByType(type) {
  return filteredTransactions.filter((t) => t.transaction_type === type).reduce((sum, t) => sum + (toNumber(t.amount) || 0), 0);
}

function renderSummary() {
  $('stat-shown').textContent = filteredTransactions.length;
  $('stat-total').textContent = `dari ${allTransactions.length} transaksi`;
  $('stat-expense').textContent = formatRupiah(sumByType('EXPENSES')) || 'Rp0';
  $('stat-income').textContent = formatRupiah(sumByType('INCOMING')) || 'Rp0';
  const net = sumByType('INCOMING') - sumByType('EXPENSES');
  $('stat-net').textContent = net > 0 ? `+${formatRupiah(net)}` : (formatRupiah(net) || 'Rp0'); // the sign is shown too, not only the colour
  $('net-item').classList.toggle('is-positive', net > 0);
  $('net-item').classList.toggle('is-negative', net < 0);
}

// "Kategori › Sub kategori"; an uncategorized category is shown once.
function categoryPath(tx) {
  if (isUncategorizedValue(tx.category)) return labelCategory(null);
  return `${labelCategory(tx.category)} › ${labelCategory(tx.sub_category)}`;
}

function renderRow(tx) {
  const amount = formatRupiah(tx.amount);
  const date = formatDate(tx.transaction_date);
  const reasons = [...getReviewReasons(tx).map(labelReviewReason), ...getReviewFlags(tx).map(labelReviewFlag)];
  return `<tr data-id="${escapeHtml(tx.id)}" tabindex="0">
    <td class="whitespace-nowrap num">${date ? escapeHtml(date) : `<span class="muted-text">${LABELS.noDate}</span>`}</td>
    <td><span class="cell-main" title="${escapeHtml(tx.description)}">${escapeHtml(tx.description) || LABELS.empty}</span><span class="cell-sub">${escapeHtml(categoryPath(tx))}</span></td>
    <td class="whitespace-nowrap">${escapeHtml(tx.source_bank) || '?'} <span class="muted-text">→</span> ${escapeHtml(tx.beneficiary_bank) || '?'}</td>
    <td>${tx.transaction_type ? `<span class="pill ${TYPE_PILL_CLASS[tx.transaction_type] || ''}">${escapeHtml(labelType(tx.transaction_type))}</span>` : ''}</td>
    <td class="amount">${amount ? escapeHtml(amount) : `<span class="muted-text">${LABELS.noAmount}</span>`}</td>
    <td>${reasons.length ? `<span class="pill pill-review" title="${escapeHtml(reasons.join(', '))}">⚠ ${reasons.length}</span>` : ''}</td>
  </tr>`;
}

function renderTable() {
  const rows = filteredTransactions.slice(0, visibleCount);
  $('table-body').innerHTML = rows.map(renderRow).join('');
  const emptyText = rows.length ? '' : (!allTransactions.length ? LABELS.transactions.emptyAll : (tabCounts.matched ? LABELS.transactions.emptyTab[activeTab] : LABELS.transactions.emptyFiltered));
  $('table-state').innerHTML = emptyText ? `<span class="empty-icon" aria-hidden="true">▤</span><strong>${escapeHtml(emptyText)}</strong>` : '';
  const more = $('more-button');
  more.classList.toggle('hidden', filteredTransactions.length <= visibleCount);
  more.textContent = LABELS.transactions.showMore(visibleCount, filteredTransactions.length);
}

function exportCsv() {
  if (activeTab !== 'reviewed') return; // data that still needs review is never exported
  const columns = ['id', 'transaction_date', 'transaction_id', 'description', 'category', 'sub_category', 'transaction_type',
    'source_bank', 'source_account_number', 'source_account_name', 'beneficiary_bank',
    'beneficiary_account_number', 'benecifiacry_account_name', 'amount'];
  // A leading = + - @ would be run as a formula by Excel, so prefix it with an apostrophe.
  const cell = (v) => { let s = String(v ?? ''); if (/^[=+\-@]/.test(s)) s = `'${s}`; return `"${s.replace(/"/g, '""')}"`; };
  const lines = [columns.join(','), ...filteredTransactions.map((tx) => columns.map((c) => cell(tx[c])).join(','))];
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob(['\ufeff' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' }));
  link.download = `${LABELS.transactions.csvFile}-${toJakartaDay(new Date().toISOString())}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

function resetFilters() {
  ['filter-search', 'filter-account', 'filter-category', 'filter-subcategory', 'filter-type', 'filter-from', 'filter-to'].forEach((id) => { $(id).value = ''; });
  fillSubCategoryFilter();
  $('filter-sort').value = 'date_desc';
  applyFilters();
}

function openRow(event) {
  const row = event.target.closest('tr[data-id]');
  if (!row) return;
  openTransactionDetail(row.dataset.id, {
    onSaved: (updated) => {
      allTransactions = allTransactions.map((t) => (String(t.id) === String(updated.id) ? updated : t));
      populateFilterOptions();
      applyFilters();
    },
  });
}

['filter-account', 'filter-subcategory', 'filter-type', 'filter-sort', 'filter-from', 'filter-to']
  .forEach((id) => $(id).addEventListener('change', applyFilters));
$('filter-category').addEventListener('change', () => { fillSubCategoryFilter(); applyFilters(); });
$('filter-search').addEventListener('input', applyFilters);
$('reset-button').addEventListener('click', resetFilters);
document.querySelector('.review-tabs').addEventListener('click', (e) => {
  const tab = e.target.closest('[data-tab]');
  if (!tab || tab.dataset.tab === activeTab) return;
  activeTab = tab.dataset.tab;
  applyFilters();
});
$('reload-button').addEventListener('click', loadTransactions);
$('export-button').addEventListener('click', exportCsv);
$('more-button').addEventListener('click', () => { visibleCount += PAGE_CHUNK; renderTable(); });
$('table-body').addEventListener('click', openRow);
$('table-body').addEventListener('keydown', (e) => { if (e.key === 'Enter') openRow(e); });

loadTransactions();
