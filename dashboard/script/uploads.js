// Uploads page: raw receipt images from Telegram with their processing status.
const PAGE_CHUNK = 25;
const REFRESH_MS = 5000;
const STATUSES = ['PENDING', 'PROCESSING', 'COMPLETED', 'DUPLICATE', 'FAILED'];
const $ = (id) => document.getElementById(id);
let jobs = [];
let statusFilter = '';
let visibleCount = PAGE_CHUNK;
let signature = '';
let openJobId = null;
let uploadKey = null; // reused if the same file is retried, so the backend can dedupe
let tick = 0;

renderLayout('uploads');

const shortId = (id) => String(id).slice(0, 8);
const isActive = (job) => job.status === 'PENDING' || job.status === 'PROCESSING';

async function loadJobs({ quiet = false } = {}) {
  if (!quiet) $('table-state').textContent = LABELS.loading;
  try {
    const rows = await Api.listUploads();
    rows.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    const next = rows.map((j) => [j.upload_id, j.status, j.attempt_count, j.transaction_record_id, j.ai_analysis_duration_ms].join('|')).join(';');
    jobs = rows;
    $('last-updated').textContent = LABELS.uploads.updatedAt(new Intl.DateTimeFormat('id-ID', { timeZone: 'Asia/Jakarta', hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(new Date()));
    if (!quiet || next !== signature) { signature = next; render(); }
  } catch (e) {
    if (!quiet) $('table-state').textContent = LABELS.error(LABELS.uploads.loadError, e.message);
  }
}

function render() {
  renderChips();
  const rows = jobs.filter((j) => !statusFilter || j.status === statusFilter);
  $('table-body').innerHTML = rows.slice(0, visibleCount).map(renderRow).join('');
  const emptyText = rows.length ? '' : (jobs.length ? LABELS.uploads.emptyFiltered : LABELS.uploads.empty);
  $('table-state').innerHTML = emptyText ? `<span class="empty-icon" aria-hidden="true">▧</span><strong>${escapeHtml(emptyText)}</strong>` : '';
  const more = $('more-button');
  more.classList.toggle('hidden', rows.length <= visibleCount);
  more.textContent = LABELS.uploads.showMore(visibleCount, rows.length);
  const job = openJobId && jobs.find((j) => j.upload_id === openJobId);
  if (job && $('job-dialog').open) renderJobDetail(job);
}

function renderChips() {
  const chip = (value, label, count) => `<button type="button" class="chip" data-status="${value}" aria-pressed="${statusFilter === value}">${escapeHtml(label)} <span class="num">${count}</span></button>`;
  $('status-chips').innerHTML = chip('', LABELS.uploads.all, jobs.length)
    + STATUSES.map((s) => chip(s, labelStatus(s), jobs.filter((j) => j.status === s).length)).join('');
}

function renderRow(job) {
  const duration = formatDuration(job.ai_analysis_duration_ms);
  const error = job.status === 'FAILED' ? `<span class="error-text">${escapeHtml(labelJobError(job.last_error))}</span>` : '';
  const tx = job.transaction_record_id != null
    ? `<button type="button" class="link-quiet" data-tx="${escapeHtml(job.transaction_record_id)}">#${escapeHtml(job.transaction_record_id)}</button>`
    : `<span class="muted-text">${LABELS.empty}</span>`;
  return `<tr data-id="${escapeHtml(job.upload_id)}" tabindex="0">
    <td><img class="thumb" loading="lazy" src="${Api.uploadImageUrl(job.upload_id)}" alt=""></td>
    <td class="num" title="${escapeHtml(job.upload_id)}">${escapeHtml(shortId(job.upload_id))}</td>
    <td><span class="pill ${STATUS_PILL_CLASS[job.status] || 'pill-pending'}">${escapeHtml(labelStatus(job.status))}</span>${error}</td>
    <td class="amount num">${escapeHtml(job.attempt_count ?? LABELS.empty)}</td>
    <td class="whitespace-nowrap num">${escapeHtml(formatDate(job.created_at, true) || LABELS.empty)}</td>
    <td class="amount num">${duration ? escapeHtml(duration) : `<span class="muted-text">${LABELS.empty}</span>`}</td>
    <td>${tx}</td>
  </tr>`;
}

function openTransactionFromJob(txId) {
  $('job-dialog').close();
  openTransactionDetail(txId);
}

function jobItem(label, value, wide = false) {
  return `<div class="detail-item${wide ? ' wide' : ''}"><dt>${escapeHtml(label)}</dt><dd>${value || value === 0 ? value : `<span class="muted-text">${LABELS.empty}</span>`}</dd></div>`;
}

function renderJobDetail(job) {
  const F = LABELS.uploads.fields;
  const isDuplicateMatch = job.status === 'DUPLICATE' && job.transaction_record_id != null;
  const imageUrl = Api.uploadImageUrl(job.upload_id);
  const tx = job.transaction_record_id != null
    ? `<button type="button" class="link-quiet" data-open-tx="${escapeHtml(job.transaction_record_id)}">#${escapeHtml(job.transaction_record_id)}</button>` : '';
  $('job-body').innerHTML = `
    <div class="detail-layout">
      <div>
        <div class="receipt-frame">
          <img id="job-image" class="receipt-image" src="${imageUrl}" alt="Gambar unggahan">
          <p id="job-image-missing" class="muted-text" hidden>${LABELS.uploads.imageMissing}</p>
        </div>
        <a class="link-quiet inline-block mt-2" href="${imageUrl}" target="_blank" rel="noopener">${LABELS.uploads.openImage}</a>
      </div>
      <div>
        <h2 class="detail-title">${escapeHtml(LABELS.uploads.jobTitle(shortId(job.upload_id)))}</h2>
        <p class="my-3"><span class="pill ${STATUS_PILL_CLASS[job.status] || 'pill-pending'}">${escapeHtml(labelStatus(job.status))}</span></p>
        ${isDuplicateMatch ? `<div class="callout">${escapeHtml(LABELS.uploads.duplicateNote(job.transaction_record_id))}</div>` : ''}
        ${job.status === 'FAILED' ? `<div class="callout error">${escapeHtml(labelJobError(job.last_error))}</div>` : ''}
        <dl class="detail-grid">
          ${jobItem(F.upload_id, escapeHtml(job.upload_id), true)}
          ${jobItem(F.attempts, escapeHtml(job.attempt_count ?? ''))}
          ${jobItem(F.duration, escapeHtml(formatDuration(job.ai_analysis_duration_ms) || ''))}
          ${jobItem(F.created_at, escapeHtml(formatDate(job.created_at, true) || ''))}
          ${jobItem(F.content_type, escapeHtml(job.content_type || ''))}
          ${jobItem(F.transaction, tx)}
          ${job.last_error ? jobItem(F.error_code, escapeHtml(job.last_error), true) : ''}
        </dl>
      </div>
    </div>`;
  const img = $('job-image');
  img.onerror = () => { img.hidden = true; $('job-image-missing').hidden = false; };
}

function openJob(uploadId) {
  const job = jobs.find((j) => j.upload_id === uploadId);
  if (!job) return;
  openJobId = uploadId;
  renderJobDetail(job);
  if (!$('job-dialog').open) $('job-dialog').showModal();
}

async function submitUpload(event) {
  event.preventDefault();
  const feedback = $('upload-feedback');
  const file = $('upload-file').files[0];
  feedback.classList.remove('is-error');
  if (!file) { feedback.textContent = LABELS.uploads.form.noFile; feedback.classList.add('is-error'); return; }
  if (file.size > 20 * 1024 * 1024) { feedback.textContent = LABELS.uploads.form.tooBig; feedback.classList.add('is-error'); return; }
  $('upload-submit').disabled = true;
  feedback.textContent = LABELS.uploads.form.sending;
  try {
    uploadKey = uploadKey || crypto.randomUUID();
    const result = await Api.uploadReceipt(file, uploadKey);
    event.target.reset();
    uploadKey = null;
    feedback.textContent = LABELS.uploads.form.queued(shortId(result.upload_id), result.status);
    visibleCount = PAGE_CHUNK;
    loadJobs({ quiet: true });
  } catch (e) {
    feedback.textContent = LABELS.error(LABELS.uploads.form.failed, e.message);
    feedback.classList.add('is-error');
  } finally {
    $('upload-submit').disabled = false;
  }
}

$('status-chips').addEventListener('click', (e) => {
  const chip = e.target.closest('button[data-status]');
  if (!chip) return;
  statusFilter = chip.dataset.status;
  visibleCount = PAGE_CHUNK;
  render();
});
$('table-body').addEventListener('click', (e) => {
  const txButton = e.target.closest('button[data-tx]');
  if (txButton) return openTransactionDetail(txButton.dataset.tx);
  const row = e.target.closest('tr[data-id]');
  if (row) openJob(row.dataset.id);
});
$('table-body').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('tr[data-id]')) openJob(e.target.dataset.id); });
$('table-body').addEventListener('error', (e) => { if (e.target.tagName === 'IMG') e.target.style.visibility = 'hidden'; }, true); // hide broken thumbnails
$('job-body').addEventListener('click', (e) => {
  const button = e.target.closest('button[data-open-tx]');
  if (button) openTransactionFromJob(button.dataset.openTx);
});
$('job-dialog').addEventListener('close', () => { openJobId = null; });
$('more-button').addEventListener('click', () => { visibleCount += PAGE_CHUNK; render(); });
$('reload-button').addEventListener('click', () => loadJobs());
$('open-upload').addEventListener('click', () => { $('upload-feedback').textContent = ''; $('upload-dialog').showModal(); });
$('upload-file').addEventListener('change', () => { uploadKey = null; $('upload-feedback').textContent = ''; });
$('upload-form').addEventListener('submit', submitUpload);

// Refresh every 5 s while receipts are being processed, otherwise every 30 s.
setInterval(() => {
  if (document.hidden) return;
  tick += 1;
  if (jobs.some(isActive) || tick % 6 === 0) loadJobs({ quiet: true });
}, REFRESH_MS);

loadJobs();
