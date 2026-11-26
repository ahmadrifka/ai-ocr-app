// Dashboard page: everything is computed client-side from the full transaction list.
const $ = (id) => document.getElementById(id);
const compactNumber = new Intl.NumberFormat('id-ID', { notation: 'compact', maximumFractionDigits: 1 });
const COLORS = { expense: '#a83a34', income: '#087c72', bar: '#087c72' };
let transactions = [];
let uploads = null; // null = could not be loaded
let trendMode = 'daily';
let categoryMode = 'category';
let groupMode = 'list'; // 'list' or 'pie' in the group card
let trendFrom = ''; // optional day range chosen in the cash-flow card, always inside the active period
let trendTo = '';
let trendEnd = null; // last bucket of the trend window; null = the latest bucket that has transactions
const TREND_WINDOW = { daily: 10, weekly: 8, monthly: 12 };
const charts = {};

renderLayout('dashboard');
Chart.defaults.font.family = "'IBM Plex Sans', system-ui, sans-serif";
Chart.defaults.color = '#60757b';

const amountOf = (tx) => toNumber(tx.amount) || 0;
const dayOf = (tx) => toJakartaDay(tx.transaction_date);

function shiftDay(day, delta) {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + delta);
  return d.toISOString().slice(0, 10);
}

// The active period as day bounds; null for "all time".
function periodRange() {
  const period = $('period').value;
  if (period === 'all') return null;
  const today = toJakartaDay(new Date().toISOString());
  return { from: period === 'month' ? `${today.slice(0, 8)}01` : shiftDay(today, -(Number(period) - 1)), to: today };
}

function currentRows() {
  const range = periodRange();
  if (!range) return transactions;
  return transactions.filter((tx) => { const d = dayOf(tx); return d && d >= range.from && d <= range.to; });
}

async function loadData() {
  $('load-error').hidden = true;
  try {
    [transactions, uploads] = await Promise.all([Api.listTransactions(), Api.listUploads().catch(() => null)]);
    render();
  } catch (e) {
    $('load-error').hidden = false;
    $('load-error').textContent = LABELS.error(LABELS.dashboard.loadError, e.message);
  }
}

function render() {
  const rows = currentRows();
  renderKpis(rows);
  renderGroups(rows);
  renderCategoryChart(rows);
  renderTrendChart(rows);
  renderCompleteness(rows);
  renderComposition(rows);
}

const sumOf = (rows, type) => rows.filter((t) => t.transaction_type === type).reduce((s, t) => s + amountOf(t), 0);

function renderKpis(rows) {
  const review = rows.filter(needsReview).length;
  const transfers = rows.filter((t) => t.transaction_type === 'TRANSFER').length;
  $('kpi-expense').textContent = formatRupiah(sumOf(rows, 'EXPENSES')) || 'Rp0';
  $('kpi-income').textContent = formatRupiah(sumOf(rows, 'INCOMING')) || 'Rp0';
  $('kpi-count').textContent = rows.length;
  $('kpi-count-note').textContent = LABELS.dashboard.transferNote(transfers);
  $('kpi-review').textContent = review;
  $('kpi-review').closest('.summary-item').classList.toggle('is-alert', review > 0); // soft red only when something needs review
  const noAmount = rows.filter((t) => toNumber(t.amount) === null).length;
  const noDate = rows.filter((t) => !t.transaction_date).length;
  $('excluded-note').textContent = noAmount || noDate ? LABELS.dashboard.excludedNote(noAmount, noDate) : '';
}

function drawChart(name, boxId, config, isEmpty) {
  const box = $(boxId);
  const canvas = box.querySelector('canvas');
  const message = box.querySelector('.empty-state');
  canvas.hidden = isEmpty;
  message.hidden = !isEmpty;
  message.textContent = isEmpty ? LABELS.dashboard.noData : '';
  if (charts[name]) charts[name].destroy();
  charts[name] = isEmpty ? null : new Chart(canvas, config);
}

const moneyAxis = { ticks: { callback: (v) => compactNumber.format(v) }, grid: { color: '#e8eeec' } };

// Chart label for a transaction: its category, or its sub category in the detailed view.
function categoryBucket(tx) {
  if (categoryMode === 'category') return labelCategory(tx.category);
  if (!isUncategorizedValue(tx.sub_category)) return tx.sub_category;
  return isUncategorizedValue(tx.category) ? labelCategory(null) : `${tx.category} › ${labelCategory(null)}`;
}

function renderCategoryChart(rows) {
  const totals = new Map();
  rows.filter((t) => t.transaction_type === 'EXPENSES' && toNumber(t.amount) !== null)
    .forEach((t) => { const key = categoryBucket(t); totals.set(key, (totals.get(key) || 0) + amountOf(t)); });
  const sorted = [...totals.entries()].sort((a, b) => b[1] - a[1]);
  $('category-box').style.minHeight = `${Math.max(280, sorted.length * 30 + 48)}px`; // room for every bar; the box grows further to fill the card
  drawChart('category', 'category-box', {
    type: 'bar',
    data: { labels: sorted.map(([k]) => k), datasets: [{ data: sorted.map(([, v]) => v), backgroundColor: COLORS.bar, borderRadius: 2, maxBarThickness: 34 }] },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => formatRupiah(c.parsed.x) } } },
      scales: {
        x: { ...moneyAxis, title: { display: true, text: LABELS.dashboard.categoryAxisTitle, padding: { top: 8 } } },
        y: { grid: { display: false }, ticks: { callback(value) { const label = this.getLabelForValue(value); return label.length > 28 ? `${label.slice(0, 27)}…` : label; } } },
      },
    },
  }, sorted.length === 0);
}

// Groups for the "per kelompok" panel. Expenses include owner withdrawals, loan payments, assets and tax,
// so the groups show how much of the cash out is business cost. Uncategorized or mismatched rows are kept apart.
const EXPENSE_GROUPS = {
  Persediaan: 'business', 'Beban Operasional': 'business', 'Pendapatan/Beban Lain': 'business',
  Pajak: 'tax', 'Aset Tetap/Investasi': 'asset', 'Modal dan Prive': 'owner', 'Utang/Piutang': 'owner',
};
const INCOME_GROUPS = { Penjualan: 'sales', 'Modal dan Prive': 'capital', 'Utang/Piutang': 'capital', 'Pendapatan/Beban Lain': 'other' };
const GROUP_ORDER = { EXPENSES: ['business', 'tax', 'asset', 'owner'], INCOMING: ['sales', 'capital', 'other'] };

function groupOf(tx) {
  if (isUncategorized(tx) || categoryProblem(tx)) return 'unclassified';
  return (tx.transaction_type === 'INCOMING' ? INCOME_GROUPS : EXPENSE_GROUPS)[tx.category] || 'unclassified';
}

// Red family for money out, teal family for money in, grey for "not categorised" in both.
const PIE_COLORS = {
  EXPENSES: { business: '#a83a34', tax: '#d9776b', asset: '#e8a97e', owner: '#7c3a36', unclassified: '#9aa8a4' },
  INCOMING: { sales: '#087c72', capital: '#3a9d93', other: '#8cc7bf', unclassified: '#9aa8a4' },
};
const groupKeys = (type, sums) => [...GROUP_ORDER[type], ...(sums.get('unclassified') ? ['unclassified'] : [])];

function groupSums(rows, type) {
  const sums = new Map();
  rows.filter((t) => t.transaction_type === type && toNumber(t.amount) !== null)
    .forEach((t) => sums.set(groupOf(t), (sums.get(groupOf(t)) || 0) + amountOf(t)));
  return { sums, total: [...sums.values()].reduce((a, b) => a + b, 0) };
}

const groupLabels = (type) => LABELS.dashboard.groups[type === 'EXPENSES' ? 'expense' : 'income'];

function renderGroupList(rows, type, boxId) {
  const labels = groupLabels(type);
  const { sums, total } = groupSums(rows, type);
  $(boxId).innerHTML = total ? groupKeys(type, sums).map((key) => `<div class="stat-row"><span>${escapeHtml(labels[key].title)}<span class="cell-sub">${escapeHtml(labels[key].note)}</span></span>
      <strong class="num">${formatRupiah(sums.get(key) || 0) || 'Rp0'}</strong></div>`).join('')
    : `<p class="note-line">${LABELS.dashboard.noData}</p>`;
}

// Whole-number percentages that add up to exactly 100 (largest remainder). A slice under 1% reads "<1%"
// and is left out of the sum, so the other slices still add up.
function pieShares(values) {
  const total = values.reduce((a, b) => a + b, 0);
  const raw = values.map((v) => (total ? (v / total) * 100 : 0));
  const isTiny = raw.map((p) => p > 0 && p < 1);
  const target = Math.round(raw.reduce((sum, p, i) => sum + (isTiny[i] ? 0 : p), 0));
  const floors = raw.map((p, i) => (isTiny[i] ? 0 : Math.floor(p)));
  let left = target - floors.reduce((a, b) => a + b, 0);
  raw.map((p, i) => [i, p - Math.floor(p)]).filter(([i]) => !isTiny[i]).sort((a, b) => b[1] - a[1])
    .forEach(([i]) => { if (left > 0) { floors[i] += 1; left -= 1; } });
  return raw.map((p, i) => LABELS.dashboard.groups.share(isTiny[i] ? '<1' : floors[i]));
}

// Picks white or dark text, whichever contrasts more with the slice colour.
function readableTextColor(hex) {
  const channel = (offset) => { const c = parseInt(hex.slice(offset, offset + 2), 16) / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  const luminance = 0.2126 * channel(1) + 0.7152 * channel(3) + 0.0722 * channel(5);
  return 1.05 / (luminance + 0.05) >= (luminance + 0.05) / 0.075 ? '#ffffff' : '#1f2d2a';
}

// Writes each slice's percentage inside the slice. A slice under 6% is too small for text, so its label goes just outside.
const pieLabelsPlugin = {
  id: 'pieLabels',
  afterDatasetsDraw(chart) {
    const { texts, colors } = chart.options.plugins.pieLabels;
    const { ctx } = chart;
    chart.getDatasetMeta(0).data.forEach((arc, i) => {
      const { x, y, startAngle, endAngle, outerRadius } = arc.getProps(['x', 'y', 'startAngle', 'endAngle', 'outerRadius'], true);
      const share = (endAngle - startAngle) / (2 * Math.PI);
      const angle = (startAngle + endAngle) / 2;
      const inside = share >= 0.06;
      const distance = share > 0.99 ? 0 : (inside ? outerRadius * 0.62 : outerRadius + 16);
      ctx.save();
      ctx.font = `600 13px ${(Chart.defaults.font && Chart.defaults.font.family) || 'sans-serif'}`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = inside ? colors[i] : '#2f3f3c';
      ctx.fillText(texts[i], x + Math.cos(angle) * distance, y + Math.sin(angle) * distance);
      ctx.restore();
    });
  },
};

function renderGroupPie(rows, type, name, boxId) {
  const labels = groupLabels(type);
  const { sums, total } = groupSums(rows, type);
  const keys = groupKeys(type, sums).filter((key) => sums.get(key) > 0);
  const values = keys.map((key) => sums.get(key));
  const colors = keys.map((key) => PIE_COLORS[type][key]);
  drawChart(name, boxId, {
    type: 'pie',
    data: {
      labels: keys.map((key) => labels[key].title),
      datasets: [{ data: values, backgroundColor: colors, borderColor: '#ffffff', borderWidth: 2 }],
    },
    plugins: [pieLabelsPlugin],
    options: {
      responsive: true, maintainAspectRatio: false,
      layout: { padding: 24 }, // room for the labels of small slices
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 10 } },
        pieLabels: { texts: pieShares(values), colors: colors.map(readableTextColor) },
        tooltip: { callbacks: { label: (c) => `${c.label}: ${formatRupiah(c.parsed) || 'Rp0'}` } },
      },
    },
  }, total === 0);
}

// Pies are drawn only while their tab is visible, because a chart created in a hidden box has no size.
function renderGroups(rows) {
  renderGroupList(rows, 'EXPENSES', 'group-expense');
  renderGroupList(rows, 'INCOMING', 'group-income');
  if (groupMode === 'pie') {
    renderGroupPie(rows, 'EXPENSES', 'pieExpense', 'pie-expense-box');
    renderGroupPie(rows, 'INCOMING', 'pieIncome', 'pie-income-box');
  }
  $('group-note').textContent = LABELS.dashboard.groups.note;
}

function weekStart(day) {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7)); // Monday
  return d.toISOString().slice(0, 10);
}

function trendKey(day) {
  if (trendMode === 'weekly') return weekStart(day);
  if (trendMode === 'monthly') return `${day.slice(0, 7)}-01`;
  return day;
}

function trendLabel(key) {
  const d = new Date(`${key}T00:00:00Z`);
  if (trendMode === 'monthly') return new Intl.DateTimeFormat('id-ID', { month: 'short', year: 'numeric', timeZone: 'UTC' }).format(d);
  const text = new Intl.DateTimeFormat('id-ID', { day: '2-digit', month: 'short', timeZone: 'UTC' }).format(d);
  return trendMode === 'weekly' ? `${LABELS.dashboard.weekPrefix} ${text}` : text;
}

// Moves a bucket key (a day, a Monday or the first of a month) by n buckets.
function stepKey(key, n) {
  if (trendMode === 'monthly') {
    const d = new Date(`${key}T00:00:00Z`);
    d.setUTCMonth(d.getUTCMonth() + n);
    return d.toISOString().slice(0, 10);
  }
  return shiftDay(key, trendMode === 'weekly' ? n * 7 : n);
}

function trendRangeText(startKey, endKey) {
  const format = (key, options) => new Intl.DateTimeFormat('id-ID', { ...options, timeZone: 'UTC' }).format(new Date(`${key}T00:00:00Z`));
  const dayOptions = { day: 'numeric', month: 'short' };
  if (trendMode === 'monthly') {
    const monthOptions = { month: 'short', year: 'numeric' };
    return LABELS.dashboard.trend.range(format(startKey, monthOptions), format(endKey, monthOptions));
  }
  const lastDay = trendMode === 'weekly' ? shiftDay(endKey, 6) : endKey; // a week bucket runs Monday to Sunday
  const sameYear = startKey.slice(0, 4) === lastDay.slice(0, 4);
  return LABELS.dashboard.trend.range(format(startKey, sameYear ? dayOptions : { ...dayOptions, year: 'numeric' }), format(lastDay, { ...dayOptions, year: 'numeric' }));
}

const isTrendRow = (t) => t.transaction_date && toNumber(t.amount) !== null
  && (t.transaction_type === 'EXPENSES' || t.transaction_type === 'INCOMING');

// Days the date pickers may choose from: the active period, or the first to last transaction day for "all time".
function trendBounds(rows) {
  const range = periodRange();
  if (range) return range;
  const days = rows.filter(isTrendRow).map(dayOf).sort();
  return days.length ? { from: days[0], to: days[days.length - 1] } : null;
}

function dayRangeText(fromDay, toDay) {
  const format = (day, options) => new Intl.DateTimeFormat('id-ID', { ...options, timeZone: 'UTC' }).format(new Date(`${day}T00:00:00Z`));
  const sameYear = fromDay.slice(0, 4) === toDay.slice(0, 4);
  return LABELS.dashboard.trend.range(format(fromDay, sameYear ? { day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short', year: 'numeric' }),
    format(toDay, { day: 'numeric', month: 'short', year: 'numeric' }));
}

// The days a bar covers, cut at the edges of the selected range or period. Weeks always say it, months only when cut.
function coverageText(key, clipFrom, clipTo) {
  if (trendMode === 'daily') return '';
  const last = trendMode === 'weekly' ? shiftDay(key, 6) : new Date(Date.UTC(Number(key.slice(0, 4)), Number(key.slice(5, 7)), 0)).toISOString().slice(0, 10);
  const from = clipFrom && clipFrom > key ? clipFrom : key;
  const to = clipTo && clipTo < last ? clipTo : last;
  if (trendMode === 'monthly' && from === key && to === last) return '';
  return LABELS.dashboard.trend.covers(dayRangeText(from, to));
}

function syncTrendRange(rows) {
  const bounds = trendBounds(rows);
  const clamp = (day) => {
    if (!day || !bounds) return '';
    return day < bounds.from ? bounds.from : (day > bounds.to ? bounds.to : day);
  };
  trendFrom = clamp(trendFrom);
  trendTo = clamp(trendTo);
  for (const [id, value] of [['trend-from', trendFrom], ['trend-to', trendTo]]) {
    const input = $(id);
    input.min = bounds ? bounds.from : '';
    input.max = bounds ? bounds.to : '';
    input.disabled = !bounds;
    input.value = value;
  }
  $('trend-range-reset').hidden = !(trendFrom || trendTo);
}

// Shows a limited window of buckets (10 days, 8 weeks or 12 months) that ends at the latest bucket with transactions,
// inside the range chosen in the card. Buckets without transactions inside the window stay visible as empty bars.
// The vertical axis follows the window.
function renderTrendChart(allRows) {
  syncTrendRange(allRows);
  const rows = allRows.filter((t) => isTrendRow(t) && (!trendFrom || dayOf(t) >= trendFrom) && (!trendTo || dayOf(t) <= trendTo));
  const buckets = new Map();
  rows.forEach((t) => {
    const key = trendKey(dayOf(t));
    const bucket = buckets.get(key) || { expense: 0, income: 0, count: 0 };
    bucket[t.transaction_type === 'EXPENSES' ? 'expense' : 'income'] += amountOf(t);
    bucket.count += 1;
    buckets.set(key, bucket);
  });
  const dataKeys = [...buckets.keys()].sort();
  const keys = [];
  let canPrev = false;
  let canNext = false;
  if (dataKeys.length) {
    const size = TREND_WINDOW[trendMode];
    const firstKey = dataKeys[0];
    const lastKey = dataKeys[dataKeys.length - 1];
    const earliestEnd = [stepKey(firstKey, size - 1), lastKey].sort()[0]; // the first page starts at the first bucket with data
    let end = trendEnd && trendEnd <= lastKey ? trendEnd : lastKey;
    if (end < earliestEnd) end = earliestEnd;
    trendEnd = end;
    let start = stepKey(end, -(size - 1));
    if (start < firstKey) start = firstKey;
    for (let key = start; key <= end; key = stepKey(key, 1)) keys.push(key);
    canPrev = start > firstKey;
    canNext = end < lastKey;
  }
  $('trend-prev').disabled = !canPrev;
  $('trend-next').disabled = !canNext;
  $('trend-range').textContent = keys.length ? trendRangeText(keys[0], keys[keys.length - 1]) : '';
  const C = LABELS.dashboard.trend.caption;
  $('trend-caption').textContent = trendMode === 'weekly'
    ? C.weekly(keys.length ? `${trendLabel(keys[0])} = ${dayRangeText(keys[0], shiftDay(keys[0], 6))}` : '')
    : C[trendMode];
  const bounds = periodRange();
  const clipFrom = trendFrom || (bounds && bounds.from) || '';
  const clipTo = trendTo || (bounds && bounds.to) || '';
  const coverage = keys.map((k) => coverageText(k, clipFrom, clipTo));
  const counts = keys.map((k) => (buckets.get(k) || { count: 0 }).count);
  const valueOf = (k, field) => (buckets.get(k) || { [field]: 0 })[field];
  const S = LABELS.dashboard.series;
  drawChart('trend', 'trend-box', {
    type: 'bar',
    data: {
      labels: keys.map(trendLabel),
      datasets: [
        { label: S.expense, data: keys.map((k) => valueOf(k, 'expense')), backgroundColor: COLORS.expense, borderRadius: 2 },
        { label: S.income, data: keys.map((k) => valueOf(k, 'income')), backgroundColor: COLORS.income, borderRadius: 2 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 10 } },
        tooltip: {
          // An empty bucket says so once, instead of listing Rp0 for both series.
          filter: (item) => counts[item.dataIndex] > 0 || item.datasetIndex === 0,
          callbacks: {
            afterTitle: (items) => coverage[items[0].dataIndex] || '',
            label: (c) => (counts[c.dataIndex] === 0 ? LABELS.dashboard.trend.noTransactions : `${c.dataset.label}: ${formatRupiah(c.parsed.y) || 'Rp0'}`),
          },
        },
      },
      scales: { y: moneyAxis, x: { grid: { display: false } } },
    },
  }, keys.length === 0);
}

// A transaction is complete when amount, date, description, category and sub category are filled and consistent.
// The source account is not required. It does not check whether the filled values are correct.
function renderCompleteness(rows) {
  const C = LABELS.dashboard.completeness;
  const total = rows.length;
  const issues = rows.map(getReviewReasons);
  const incomplete = issues.filter((list) => list.length).length;
  const done = total - incomplete;
  const percent = total ? Math.floor((done / total) * 100) : 0; // rounded down so 100% means every transaction
  $('complete-sentence').innerHTML = total ? `<span class="num">${percent}%</span> ${C.sentence}` : escapeHtml(C.empty);
  $('complete-detail').textContent = total ? C.detail(done, total) : '';
  $('complete-bar').innerHTML = total
    ? `<span class="seg-complete" style="width:${(done / total) * 100}%"></span><span class="seg-incomplete" style="width:${(incomplete / total) * 100}%"></span>` : '';
  const counts = new Map();
  issues.flat().forEach((code) => counts.set(code, (counts.get(code) || 0) + 1));
  const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]);
  const capital = (text) => text.charAt(0).toUpperCase() + text.slice(1);
  $('complete-list-title').hidden = !sorted.length;
  $('complete-list-title').textContent = C.listTitle;
  $('complete-list').innerHTML = sorted.length
    ? sorted.map(([code, count]) => `<div class="stat-row"><span>${escapeHtml(capital(labelReviewReason(code)))}</span><strong class="num">${count}</strong></div>`).join('')
    : (total ? `<p class="note-line">${C.allDone}</p>` : '');
  $('complete-note').textContent = total ? C.note : '';
}

function renderComposition(rows) {
  const types = ['EXPENSES', 'INCOMING', 'TRANSFER'];
  const counts = types.map((t) => rows.filter((r) => r.transaction_type === t).length);
  const total = counts.reduce((a, b) => a + b, 0) || 1;
  $('type-bar').innerHTML = types.map((t, i) => `<span class="seg-${t.toLowerCase()}" style="width:${(counts[i] / total) * 100}%"></span>`).join('');
  $('type-legend').innerHTML = types.map((t, i) => `<span class="pill ${TYPE_PILL_CLASS[t]}">${labelType(t)} · ${counts[i]}</span>`).join('');
  const P = LABELS.dashboard.pipelineLabels;
  if (!uploads) { $('pipeline-list').innerHTML = `<p class="note-line">${LABELS.dashboard.pipelineUnavailable}</p>`; return; }
  const by = (...s) => uploads.filter((u) => s.includes(u.status)).length;
  const row = (label, value) => `<div class="stat-row"><span>${label}</span><strong class="num">${value}</strong></div>`;
  $('pipeline-list').innerHTML = row(P.completed, by('COMPLETED')) + row(P.active, by('PENDING', 'PROCESSING'))
    + row(P.duplicate, by('DUPLICATE')) + row(P.failed, by('FAILED'));
}

$('period').addEventListener('change', () => { trendFrom = ''; trendTo = ''; trendEnd = null; render(); });
$('reload-button').addEventListener('click', () => { trendFrom = ''; trendTo = ''; trendEnd = null; loadData(); });
$('group-toggle').addEventListener('click', (e) => {
  const button = e.target.closest('button[data-mode]');
  if (!button) return;
  groupMode = button.dataset.mode;
  $('group-toggle').querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b === button)));
  $('group-view-list').hidden = groupMode !== 'list';
  $('group-view-pie').hidden = groupMode !== 'pie';
  renderGroups(currentRows());
});
$('category-toggle').addEventListener('click', (e) => {
  const button = e.target.closest('button[data-mode]');
  if (!button) return;
  categoryMode = button.dataset.mode;
  $('category-toggle').querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b === button)));
  renderCategoryChart(currentRows());
});
$('trend-from').addEventListener('change', () => {
  trendFrom = $('trend-from').value;
  if (trendFrom && trendTo && trendFrom > trendTo) trendTo = trendFrom; // keep the range valid: the field just edited wins
  trendEnd = null; renderTrendChart(currentRows());
});
$('trend-to').addEventListener('change', () => {
  trendTo = $('trend-to').value;
  if (trendFrom && trendTo && trendFrom > trendTo) trendFrom = trendTo;
  trendEnd = null; renderTrendChart(currentRows());
});
$('trend-range-reset').addEventListener('click', () => { trendFrom = ''; trendTo = ''; trendEnd = null; renderTrendChart(currentRows()); });
$('trend-prev').addEventListener('click', () => { trendEnd = stepKey(trendEnd, -TREND_WINDOW[trendMode]); renderTrendChart(currentRows()); });
$('trend-next').addEventListener('click', () => { trendEnd = stepKey(trendEnd, TREND_WINDOW[trendMode]); renderTrendChart(currentRows()); });
$('trend-toggle').addEventListener('click', (e) => {
  const button = e.target.closest('button[data-mode]');
  if (!button) return;
  trendMode = button.dataset.mode;
  trendEnd = null;
  $('trend-toggle').querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b === button)));
  renderTrendChart(currentRows());
});

loadData();
