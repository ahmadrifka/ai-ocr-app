// Formatting and small data helpers shared by all pages.
// Category master data. It mirrors the "Kategori Transaksi" table (18 rows) and the backend enums.
// The backend validates category and sub_category separately, so the pairing is enforced here.
const UNCATEGORIZED = 'Uncategorized';
const CATEGORY_TABLE = [
  { type: 'EXPENSES', category: 'Persediaan', subCategory: 'Bahan Baku' },
  { type: 'INCOMING', category: 'Penjualan', subCategory: 'Penjualan Produk' },
  { type: 'INCOMING', category: 'Modal dan Prive', subCategory: 'Modal' },
  { type: 'EXPENSES', category: 'Modal dan Prive', subCategory: 'Prive' },
  { type: 'EXPENSES', category: 'Beban Operasional', subCategory: 'Biaya-Gaji Karyawan' },
  { type: 'EXPENSES', category: 'Beban Operasional', subCategory: 'Biaya-Konsumsi' },
  { type: 'EXPENSES', category: 'Beban Operasional', subCategory: 'Biaya-Perlengkapan Kantor dan Administrasi' },
  { type: 'EXPENSES', category: 'Beban Operasional', subCategory: 'Biaya-Transportasi' },
  { type: 'EXPENSES', category: 'Beban Operasional', subCategory: 'Biaya-Ongkir' },
  { type: 'EXPENSES', category: 'Beban Operasional', subCategory: 'Biaya-Perbaikan Bangunan' },
  { type: 'EXPENSES', category: 'Beban Operasional', subCategory: 'Biaya-Operasional' },
  { type: 'EXPENSES', category: 'Beban Operasional', subCategory: 'Biaya-Sosial' },
  { type: 'EXPENSES', category: 'Utang/Piutang', subCategory: 'Utang' },
  { type: 'INCOMING', category: 'Utang/Piutang', subCategory: 'Piutang' },
  { type: 'EXPENSES', category: 'Aset Tetap/Investasi', subCategory: 'Biaya-Pembelian Aset' },
  { type: 'EXPENSES', category: 'Pendapatan/Beban Lain', subCategory: 'Beban Lain' },
  { type: 'INCOMING', category: 'Pendapatan/Beban Lain', subCategory: 'Pendapatan Lain' },
  { type: 'EXPENSES', category: 'Pajak', subCategory: 'Pembayaran pajak' },
];
const uniqueValues = (list) => [...new Set(list)];
const CATEGORIES = [UNCATEGORIZED, ...uniqueValues(CATEGORY_TABLE.map((r) => r.category))];
const SUB_CATEGORIES = [UNCATEGORIZED, ...uniqueValues(CATEGORY_TABLE.map((r) => r.subCategory))];
const TYPE_PILL_CLASS = { EXPENSES: 'pill-expense', INCOMING: 'pill-incoming', TRANSFER: 'pill-transfer' };
const STATUS_PILL_CLASS = {
  PENDING: 'pill-pending', PROCESSING: 'pill-processing', COMPLETED: 'pill-completed',
  DUPLICATE: 'pill-duplicate', FAILED: 'pill-failed',
};

const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// The API sends amount as text ("100000.00") and it can be null.
function toNumber(value) {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function formatRupiah(value) {
  const n = toNumber(value);
  if (n === null) return null;
  return new Intl.NumberFormat('id-ID', { style: 'currency', currency: 'IDR', maximumFractionDigits: 0 }).format(n);
}

function formatDate(iso, withTime = false) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return new Intl.DateTimeFormat('id-ID', {
    timeZone: 'Asia/Jakarta', day: '2-digit', month: 'short', year: 'numeric',
    ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}),
  }).format(d);
}

function formatDuration(ms) {
  if (!Number.isFinite(ms) || ms < 0) return null;
  return `${(ms / 1000).toLocaleString('id-ID', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s`;
}

function jakartaParts(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Jakarta', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(d);
  return Object.fromEntries(parts.map((p) => [p.type, p.value]));
}
function toJakartaDay(iso) { // "YYYY-MM-DD" in WIB, for date filters and grouping
  const p = iso ? jakartaParts(iso) : null;
  return p ? `${p.year}-${p.month}-${p.day}` : null;
}
function toDatetimeLocalValue(iso) { // for <input type="datetime-local">
  const p = iso ? jakartaParts(iso) : null;
  return p ? `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}` : '';
}
function fromDatetimeLocalValue(value) { // WIB has no DST, so a fixed +07:00 offset is safe
  return value ? `${value}:00+07:00` : null;
}

// review_flags is expected to be a list of strings; tolerate other shapes.
function getReviewFlags(tx) {
  const f = tx.review_flags;
  if (!f || (Array.isArray(f) && f.length === 0)) return [];
  return (Array.isArray(f) ? f : [f]).map((x) => (typeof x === 'string' ? x : (x.code || x.flag || x.type || 'unknown')));
}

const isUncategorizedValue = (value) => !value || value === UNCATEGORIZED;
const isUncategorized = (tx) => isUncategorizedValue(tx.category) || isUncategorizedValue(tx.sub_category);

// TRANSFER is not in the category table, so it may carry any category (it only hints what the transfer was for).
const pairsForType = (type) => (type === 'EXPENSES' || type === 'INCOMING'
  ? CATEGORY_TABLE.filter((r) => r.type === type) : CATEGORY_TABLE);
function categoriesForType(type) {
  return [UNCATEGORIZED, ...uniqueValues(pairsForType(type).map((r) => r.category))];
}
function subCategoriesFor(category, type) {
  if (isUncategorizedValue(category)) return [UNCATEGORIZED];
  return [UNCATEGORIZED, ...pairsForType(type).filter((r) => r.category === category).map((r) => r.subCategory)];
}
const findPair = (category, subCategory) => CATEGORY_TABLE.find((r) => r.category === category && r.subCategory === subCategory);

// Returns null when the category fields are fine, otherwise one of:
// 'unknownCategory' (value not in the table, e.g. old data), 'pairMismatch', 'typeMismatch'.
function categoryProblem(tx) {
  if (isUncategorized(tx)) return null; // reported separately as "uncategorized"
  const known = CATEGORIES.includes(tx.category) && SUB_CATEGORIES.includes(tx.sub_category);
  if (!known) return 'unknownCategory';
  const pair = findPair(tx.category, tx.sub_category);
  if (!pair) return 'pairMismatch';
  if ((tx.transaction_type === 'EXPENSES' || tx.transaction_type === 'INCOMING') && pair.type !== tx.transaction_type) return 'typeMismatch';
  return null;
}

// Any of bank, account number or account name counts as a filled source (cash is stored as a bank value).
const hasSource = (tx) => [tx.source_bank, tx.source_account_number, tx.source_account_name].some((v) => String(v ?? '').trim() !== '');

// The worker sometimes returns no description, or just a dash. Both count as empty.
const isEmptyDescription = (value) => /^[\s\-\u2010-\u2015]*$/.test(String(value ?? ''));

// Reason codes for "needs review" (labels: LABELS.reviewReason). Backend review_flags are separate.
function getReviewReasons(tx) {
  const reasons = [];
  if (toNumber(tx.amount) === null) reasons.push('noAmount');
  if (!tx.transaction_date) reasons.push('noDate');
  if (isUncategorized(tx)) reasons.push('uncategorized');
  const problem = categoryProblem(tx);
  if (problem) reasons.push(problem);
  if (isEmptyDescription(tx.description)) reasons.push('noDescription');
  return reasons;
}
const needsReview = (tx) => getReviewReasons(tx).length > 0 || getReviewFlags(tx).length > 0;

// Bank name normalisation: the OCR spells the same bank many ways ("BNI", "Bank BNI", "bankjatim"...).
const BANK_ALIASES = [
  [/\bbni\b|negara indonesia/, 'BNI'], [/\bbri\b|rakyat indonesia/, 'BRI'], [/\bbca\b|central asia/, 'BCA'],
  [/mandiri/, 'Mandiri'], [/\bbsi\b|syariah indonesia/, 'BSI'], [/\bbtn\b|tabungan negara/, 'BTN'],
  [/cimb/, 'CIMB Niaga'], [/permata/, 'Permata'], [/danamon/, 'Danamon'], [/jatim|jawa timur/, 'Bank Jatim'],
  [/\bjago\b/, 'Bank Jago'], [/sea ?bank/, 'SeaBank'], [/\bocbc\b/, 'OCBC'], [/maybank/, 'Maybank'], [/panin/, 'Panin'],
  [/flip/, 'Flip'], [/shopee/, 'ShopeePay'], [/gopay|go-pay|gojek/, 'GoPay'], [/\bovo\b/, 'OVO'],
  [/\bdana\b/, 'DANA'], [/link ?aja/, 'LinkAja'],
];

function canonicalBankName(raw) {
  const text = String(raw ?? '').trim();
  if (!text) return '';
  const lower = text.toLowerCase();
  const hit = BANK_ALIASES.find(([pattern]) => pattern.test(lower));
  return hit ? hit[1] : text.replace(/^(pt\.?\s+)?bank\s+/i, '').trim();
}
const normalizeKey = (value) => String(value ?? '').toLowerCase().replace(/[^a-z0-9]/g, '');
const digitsOf = (value) => String(value ?? '').replace(/\D/g, '');

// Finds the registered account that a bank / number / holder name triple points to, or -1.
// The account number decides when it is present (a different number is no match, as in the backend).
// Without a number, bank and holder name must match exactly one account.
function accountMatchIndex(accounts, bank, number, name) {
  const digits = digitsOf(number);
  if (digits) return accounts.findIndex((a) => digitsOf(a.account_number) === digits);
  const bankKey = canonicalBankName(bank);
  const nameKey = normalizeKey(name);
  if (!bankKey || !nameKey) return -1;
  const hits = accounts.map((a, i) => (canonicalBankName(a.bank_name) === bankKey && normalizeKey(a.account_name) === nameKey ? i : -1)).filter((i) => i >= 0);
  return hits.length === 1 ? hits[0] : -1;
}
