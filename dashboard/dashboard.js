const PAGE_SIZE = 20;
const state = {
  jobs: [],
  transactions: [],
  accounts: [],
  jobBusy: false,
  transactionBusy: false,
  transactionRefreshPending: false,
  idempotencyKey: null,
  jobsLoaded: false,
  transactionsLoaded: false,
  jobsHasMore: false,
  transactionsHasMore: false,
};
let detailRequestVersion = 0;
let detailTrigger = null;
let activeTransaction = null;
let activeAccount = null;
let jobDetailTrigger = null;
let jobImageRequestVersion = 0;

const byId = (id) => document.getElementById(id);

async function getJson(path, options = {}) {
  const response = await fetch(path, { cache: "no-store", ...options });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    // Keep the HTTP status as the useful error when a response is not JSON.
  }
  if (!response.ok) {
    const detail = typeof payload?.detail === "string" ? payload.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return payload;
}

function cell(text, className = "") {
  const element = document.createElement("td");
  element.textContent = text == null || text === "" ? "—" : String(text);
  if (className) element.className = className;
  return element;
}

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function formatDurationMs(value) {
  if (!Number.isFinite(value) || value < 0) return "Not measured yet";
  return value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(2)} s`;
}

function formatReviewFlag(flag) {
  return ({
    abusive_language: "abusive language",
    sensitive_credentials_request: "credential request",
    urgent_payment_pressure: "urgent payment wording",
    instruction_like_content: "instruction-like text",
  })[flag] || "suspicious wording";
}

function transactionTypeCell(type) {
  const presentation = ({
    EXPENSES: { label: "Expense", className: "transaction-type-expense" },
    INCOMING: { label: "Incoming", className: "transaction-type-incoming" },
    TRANSFER: { label: "Transfer", className: "transaction-type-transfer" },
  })[type] || {
    label: type ? String(type) : "Unknown",
    className: "transaction-type-other",
  };
  const element = document.createElement("td");
  element.className = "transaction-type-cell";
  const badge = document.createElement("span");
  badge.className = `transaction-type-pill ${presentation.className}`;
  badge.textContent = presentation.label;
  element.append(badge);
  return element;
}

function formatJobError(error) {
  if (!error) return "No error details recorded";
  return ({
    not_a_receipt: "Image was not recognized as a receipt",
    TimeoutError: "OCR analysis timed out",
    ValidationError: "OCR response did not match the expected format",
  })[error] || String(error).replaceAll("_", " ");
}

function formatAmount(value) {
  if (value == null || value === "") return "—";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "—";
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 2,
  }).format(amount);
}

function showError(id, message) {
  const element = byId(id);
  element.textContent = message;
  element.hidden = false;
}

function clearError(id) {
  const element = byId(id);
  element.textContent = "";
  element.hidden = true;
}

function setConnection(isOnline) {
  const container = byId("connection-state").parentElement;
  container.classList.toggle("is-online", isOnline);
  container.classList.toggle("is-offline", !isOnline);
  byId("connection-state").textContent = isOnline ? "OCR service connected" : "OCR service unavailable";
}

function renderJobs() {
  const body = byId("jobs-body");
  body.replaceChildren();
  byId("jobs-empty").hidden = state.jobs.length > 0 || !state.jobsLoaded;
  byId("jobs-count").textContent = state.jobs.length === PAGE_SIZE
    ? `Showing the latest ${PAGE_SIZE} uploads`
    : `Showing ${state.jobs.length} recent upload${state.jobs.length === 1 ? "" : "s"}`;

  for (const job of state.jobs) {
    const row = document.createElement("tr");
    const idCell = cell(String(job.upload_id).slice(0, 8), "id-cell");
    idCell.title = job.upload_id;
    row.append(idCell);

    const statusCell = document.createElement("td");
    const status = document.createElement("span");
    const safeStatus = ["PENDING", "PROCESSING", "COMPLETED", "DUPLICATE", "FAILED"].includes(job.status)
      ? job.status.toLowerCase()
      : "pending";
    status.className = `status-pill status-${safeStatus}`;
    status.textContent = job.status || "UNKNOWN";
    statusCell.append(status);
    if (job.status === "FAILED") {
      const error = document.createElement("span");
      error.className = "job-error-summary";
      error.textContent = formatJobError(job.last_error);
      if (job.last_error) error.title = job.last_error;
      statusCell.append(error);
    }
    row.append(statusCell);

    row.append(cell(job.attempt_count));
    row.append(cell(formatDate(job.created_at)));

    const transactionCell = document.createElement("td");
    if (job.transaction_record_id != null) {
      const link = document.createElement("a");
      link.className = "transaction-link";
      link.href = "#transactions-title";
      link.textContent = `#${job.transaction_record_id}`;
      link.setAttribute("aria-label", `Go to the transaction list for record ${job.transaction_record_id}`);
      transactionCell.append(link);
    } else {
      transactionCell.textContent = "—";
      transactionCell.className = "muted-value";
    }
    row.append(transactionCell);

    const detailsCell = document.createElement("td");
    const detailsButton = document.createElement("button");
    detailsButton.type = "button";
    detailsButton.className = "transaction-open";
    detailsButton.dataset.jobId = job.upload_id;
    detailsButton.textContent = "Details";
    detailsButton.setAttribute(
      "aria-label",
      `View processing details for upload ${String(job.upload_id).slice(0, 8)}`,
    );
    detailsCell.append(detailsButton);
    row.append(detailsCell);
    body.append(row);
  }

  byId("load-more-jobs").hidden = !state.jobsHasMore;
}

function renderTransactions() {
  const body = byId("transactions-body");
  body.replaceChildren();
  byId("transactions-empty").hidden = state.transactions.length > 0 || !state.transactionsLoaded;
  byId("transactions-count").textContent = state.transactions.length === PAGE_SIZE
    ? `Showing the latest ${PAGE_SIZE} transactions`
    : `Showing ${state.transactions.length} transaction${state.transactions.length === 1 ? "" : "s"}`;

  for (const transaction of state.transactions) {
    const row = document.createElement("tr");
    row.id = `transaction-${transaction.id}`;
    row.append(cell(formatDate(transaction.transaction_date || transaction.created_at)));

    const descriptionCell = document.createElement("td");
    const description = document.createElement("span");
    description.className = "description-main";
    description.textContent = transaction.description || "Untitled transaction";
    description.title = transaction.description || "";
    descriptionCell.append(description);
    if (transaction.transaction_id) {
      const reference = document.createElement("span");
      reference.className = "description-sub";
      reference.textContent = `Ref ${transaction.transaction_id}`;
      descriptionCell.append(reference);
    }
    if (transaction.review_flags?.length) {
      const review = document.createElement("span");
      review.className = "description-sub review-warning";
      review.textContent = `Review needed: ${transaction.review_flags.map(formatReviewFlag).join(", ")}`;
      descriptionCell.append(review);
    }
    row.append(descriptionCell);

    row.append(cell(transaction.source_bank || transaction.beneficiary_bank));
    row.append(cell(transaction.category, "category-cell"));
    row.append(transactionTypeCell(transaction.transaction_type));
    row.append(cell(formatAmount(transaction.amount), "amount-cell"));

    const actionCell = document.createElement("td");
    const viewButton = document.createElement("button");
    viewButton.type = "button";
    viewButton.className = "transaction-open";
    viewButton.dataset.transactionId = String(transaction.id);
    viewButton.textContent = "View";
    viewButton.setAttribute("aria-label", `View details and receipt for transaction ${transaction.id}`);
    actionCell.append(viewButton);
    row.append(actionCell);
    body.append(row);
  }

  byId("load-more-transactions").hidden = !state.transactionsHasMore;
}

function renderAccounts() {
  const body = byId("accounts-body");
  body.replaceChildren();
  byId("accounts-empty").hidden = state.accounts.length > 0;
  state.accounts.forEach((account, index) => {
    const row = document.createElement("tr");
    row.append(cell(account.bank_name), cell(account.account_name), cell(account.account_number));
    const action = document.createElement("td");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "transaction-open";
    button.dataset.accountIndex = String(index);
    button.textContent = "Edit";
    button.setAttribute("aria-label", `Edit ${account.bank_name || "bank"} account ${account.account_number || ""}`);
    action.append(button);
    row.append(action);
    body.append(row);
  });
}

async function loadAccounts() {
  clearError("accounts-error");
  try {
    state.accounts = await getJson("/api/accounts");
    renderAccounts();
  } catch (error) {
    showError("accounts-error", `Could not load accounts: ${error.message}`);
  }
}

function setFormValue(form, name, value) {
  form.elements.namedItem(name).value = value == null ? "" : String(value);
}

function startTransactionEdit() {
  const form = byId("transaction-edit-form");
  for (const [name, value] of Object.entries(activeTransaction)) {
    if (form.elements.namedItem(name)) setFormValue(form, name, value);
  }
  byId("detail-content").hidden = true;
  byId("edit-transaction").hidden = true;
  form.hidden = false;
  clearError("transaction-edit-error");
}

async function loadJobs({ append = false, quiet = false } = {}) {
  if (state.jobBusy) return;
  state.jobBusy = true;
  const button = byId("refresh-jobs");
  if (!quiet && !append) button.disabled = true;
  clearError("jobs-error");
  try {
    const skip = append ? state.jobs.length : 0;
    const rows = await getJson(`/api/documents/uploads?skip=${skip}&limit=${PAGE_SIZE}`);
    const completedBefore = new Set(
      state.jobs.filter((job) => job.status === "COMPLETED").map((job) => job.upload_id),
    );
    const newCompletion = !append && rows.some(
      (job) => job.status === "COMPLETED" && !completedBefore.has(job.upload_id),
    );
    state.jobs = append ? state.jobs.concat(rows) : rows;
    state.jobsHasMore = rows.length === PAGE_SIZE;
    state.jobsLoaded = true;
    renderJobs();
    setConnection(true);
    if (newCompletion) void loadTransactions();
  } catch (error) {
    showError("jobs-error", `Could not load processing jobs: ${error.message}`);
    setConnection(false);
  } finally {
    state.jobBusy = false;
    button.disabled = false;
  }
}

async function loadTransactions({ append = false } = {}) {
  if (state.transactionBusy) {
    if (!append) state.transactionRefreshPending = true;
    return;
  }
  state.transactionBusy = true;
  const button = byId("refresh-transactions");
  button.disabled = true;
  clearError("transactions-error");
  try {
    const skip = append ? state.transactions.length : 0;
    const rows = await getJson(`/api/documents/?skip=${skip}&limit=${PAGE_SIZE}`);
    state.transactions = append ? state.transactions.concat(rows) : rows;
    state.transactionsHasMore = rows.length === PAGE_SIZE;
    state.transactionsLoaded = true;
    renderTransactions();
  } catch (error) {
    showError("transactions-error", `Could not load transactions: ${error.message}`);
  } finally {
    state.transactionBusy = false;
    button.disabled = false;
    if (state.transactionRefreshPending) {
      state.transactionRefreshPending = false;
      void loadTransactions();
    }
  }
}

function addDetailItem(label, value, className = "", listId = "detail-list") {
  const item = document.createElement("div");
  item.className = `detail-item${className ? ` ${className}` : ""}`;
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = value == null || value === "" ? "—" : String(value);
  item.append(term, description);
  byId(listId).append(item);
}

function openJobDetails(uploadId, trigger) {
  const job = state.jobs.find((item) => item.upload_id === uploadId);
  if (!job) return;
  const isDuplicateMatch = job.status === "DUPLICATE" && job.transaction_record_id != null;
  jobDetailTrigger = trigger;
  byId("job-dialog-title").textContent = `Upload ${String(job.upload_id).slice(0, 8)}`;
  byId("job-detail-list").replaceChildren();
  addDetailItem("Upload ID", job.upload_id, "detail-item--wide", "job-detail-list");
  addDetailItem("Status", job.status, "", "job-detail-list");
  addDetailItem("Attempts", job.attempt_count, "", "job-detail-list");
  addDetailItem("AI analysis time", formatDurationMs(job.ai_analysis_duration_ms), "", "job-detail-list");
  addDetailItem("Received", formatDate(job.created_at), "", "job-detail-list");
  addDetailItem("Image type", job.content_type, "", "job-detail-list");
  addDetailItem(
    "Linked transaction",
    job.transaction_record_id == null ? "—" : `#${job.transaction_record_id}`,
    "",
    "job-detail-list",
  );
  addDetailItem(
    "Error",
    job.status === "FAILED" ? formatJobError(job.last_error) : "—",
    "detail-item--wide detail-item--error",
    "job-detail-list",
  );
  if (job.last_error) {
    addDetailItem("Error code", job.last_error, "detail-item--wide", "job-detail-list");
  }
  byId("job-dialog").showModal();

  const imageVersion = ++jobImageRequestVersion;
  const imageUrl = `/api/documents/uploads/${encodeURIComponent(job.upload_id)}/image`;
  const image = byId("job-receipt-image");
  const openLink = byId("job-receipt-open");
  const matchNote = byId("job-receipt-match");
  matchNote.hidden = !isDuplicateMatch;
  matchNote.textContent = isDuplicateMatch
    ? `Duplicate match: transaction #${job.transaction_record_id}.`
    : "";
  image.alt = isDuplicateMatch
    ? `Matched image from transaction ${job.transaction_record_id} for duplicate upload ${String(job.upload_id).slice(0, 8)}`
    : `Uploaded receipt image for upload ${String(job.upload_id).slice(0, 8)}`;
  image.hidden = true;
  byId("job-receipt-error").textContent = isDuplicateMatch
    ? `Matched image from transaction #${job.transaction_record_id} could not be previewed.`
    : "Upload image could not be previewed.";
  byId("job-receipt-error").hidden = true;
  byId("job-receipt-placeholder").textContent = "Loading upload image…";
  byId("job-receipt-placeholder").hidden = false;
  openLink.textContent = isDuplicateMatch
    ? `Open matched image from transaction #${job.transaction_record_id}`
    : "Open uploaded image in a new tab";
  openLink.hidden = true;
  image.onload = () => {
    if (imageVersion !== jobImageRequestVersion) return;
    image.hidden = false;
    byId("job-receipt-placeholder").hidden = true;
    openLink.href = imageUrl;
    openLink.hidden = false;
  };
  image.onerror = () => {
    if (imageVersion !== jobImageRequestVersion) return;
    byId("job-receipt-placeholder").hidden = true;
    byId("job-receipt-error").hidden = false;
  };
  image.src = imageUrl;
}

function accountLabel(name, number) {
  return [name, number].filter(Boolean).join(" · ") || "—";
}

async function openTransactionDetails(transactionId, trigger) {
  const id = Number(transactionId);
  if (!Number.isSafeInteger(id) || id < 1) return;

  detailTrigger = trigger;
  const requestVersion = ++detailRequestVersion;
  const dialog = byId("transaction-dialog");
  byId("dialog-title").textContent = `Transaction #${id}`;
  byId("detail-loading").hidden = false;
  byId("detail-content").hidden = true;
  byId("transaction-edit-form").hidden = true;
  byId("edit-transaction").hidden = true;
  byId("detail-list").replaceChildren();
  clearError("detail-error");
  byId("receipt-image").hidden = true;
  byId("receipt-image").removeAttribute("src");
  byId("receipt-placeholder").textContent = "Loading receipt image…";
  byId("receipt-placeholder").hidden = false;
  byId("receipt-error").hidden = true;
  byId("receipt-open").hidden = true;
  if (!dialog.open) dialog.showModal();

  try {
    const transaction = await getJson(`/api/documents/${id}`);
    if (requestVersion !== detailRequestVersion) return;
    activeTransaction = transaction;

    byId("detail-loading").hidden = true;
    byId("detail-content").hidden = false;
    byId("edit-transaction").hidden = false;
    addDetailItem("Record", `#${transaction.id}`);
    addDetailItem("Bank reference", transaction.transaction_id);
    addDetailItem("Type", transaction.transaction_type);
    addDetailItem("Transaction date", formatDate(transaction.transaction_date));
    addDetailItem("Category", transaction.category);
    addDetailItem("Amount", formatAmount(transaction.amount), "detail-item--amount");
    addDetailItem("Description", transaction.description, "detail-item--wide");
    addDetailItem("Source bank", transaction.source_bank);
    addDetailItem(
      "Source account",
      accountLabel(transaction.source_account_name, transaction.source_account_number),
    );
    addDetailItem("Beneficiary bank", transaction.beneficiary_bank);
    addDetailItem(
      "Beneficiary account",
      accountLabel(transaction.benecifiacry_account_name, transaction.beneficiary_account_number),
    );

    const receiptUrl = `/api/documents/${id}/receipt`;
    const image = byId("receipt-image");
    const openLink = byId("receipt-open");
    image.alt = `Receipt image for transaction ${id}`;
    image.onload = () => {
      if (requestVersion !== detailRequestVersion) return;
      image.hidden = false;
      byId("receipt-placeholder").hidden = true;
      openLink.href = receiptUrl;
      openLink.hidden = false;
    };
    image.onerror = () => {
      if (requestVersion !== detailRequestVersion) return;
      byId("receipt-placeholder").hidden = true;
      byId("receipt-error").hidden = false;
      openLink.href = receiptUrl;
      openLink.hidden = false;
    };
    image.src = receiptUrl;
  } catch (error) {
    if (requestVersion !== detailRequestVersion) return;
    byId("detail-loading").hidden = true;
    showError("detail-error", `Could not load transaction details: ${error.message}`);
  }
}

byId("receipt-file").addEventListener("change", (event) => {
  const file = event.currentTarget.files?.[0];
  state.idempotencyKey = file ? crypto.randomUUID() : null;
  byId("file-name").textContent = file ? file.name : "Choose a receipt image";
  byId("upload-feedback").textContent = "";
  byId("upload-feedback").classList.remove("is-error");
});

byId("upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const file = byId("receipt-file").files?.[0];
  const button = byId("upload-button");
  const feedback = byId("upload-feedback");
  feedback.classList.remove("is-error");

  if (!file) {
    feedback.textContent = "Choose an image before queueing it.";
    feedback.classList.add("is-error");
    return;
  }
  if (file.size > 20 * 1024 * 1024) {
    feedback.textContent = "This image is over the 20 MB limit.";
    feedback.classList.add("is-error");
    return;
  }

  button.disabled = true;
  button.textContent = "Queueing…";
  feedback.textContent = "Sending image to the OCR queue…";
  try {
    const formData = new FormData(form);
    const idempotencyKey = state.idempotencyKey || (state.idempotencyKey = crypto.randomUUID());
    const result = await getJson("/api/documents/upload", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: formData,
    });
    form.reset();
    state.idempotencyKey = null;
    byId("file-name").textContent = "Choose a receipt image";
    feedback.textContent = `Queued · upload ${String(result.upload_id).slice(0, 8)} · status ${result.status}`;
    await loadJobs();
  } catch (error) {
    feedback.textContent = `Upload failed: ${error.message}`;
    feedback.classList.add("is-error");
  } finally {
    button.disabled = false;
    button.textContent = "Queue receipt";
  }
});

byId("refresh-jobs").addEventListener("click", () => loadJobs());
byId("load-more-jobs").addEventListener("click", () => loadJobs({ append: true }));
byId("jobs-body").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-job-id]");
  if (button) openJobDetails(button.dataset.jobId, button);
});
byId("close-job-dialog").addEventListener("click", () => byId("job-dialog").close());
byId("job-dialog").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) event.currentTarget.close();
});
byId("job-dialog").addEventListener("close", () => {
  jobImageRequestVersion += 1;
  const image = byId("job-receipt-image");
  image.onload = null;
  image.onerror = null;
  image.removeAttribute("src");
  const focusTarget = jobDetailTrigger?.isConnected ? jobDetailTrigger : byId("refresh-jobs");
  focusTarget.focus();
  jobDetailTrigger = null;
});
byId("refresh-transactions").addEventListener("click", () => loadTransactions());
byId("load-more-transactions").addEventListener("click", () => loadTransactions({ append: true }));
byId("transactions-body").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-transaction-id]");
  if (button) void openTransactionDetails(button.dataset.transactionId, button);
});
byId("edit-transaction").addEventListener("click", startTransactionEdit);
byId("cancel-transaction-edit").addEventListener("click", () => {
  byId("transaction-edit-form").hidden = true;
  byId("detail-content").hidden = false;
  byId("edit-transaction").hidden = false;
});
byId("transaction-edit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector('[type="submit"]');
  const nullableFields = [
    "transaction_date", "transaction_id", "source_bank", "source_account_number",
    "source_account_name", "beneficiary_bank", "beneficiary_account_number",
    "benecifiacry_account_name",
  ];
  const payload = {};
  for (const [name, rawValue] of new FormData(form).entries()) {
    let value = rawValue;
    if (nullableFields.includes(name)) value = rawValue.trim() || null;
    if (name === "amount") value = rawValue === "" ? null : rawValue;
    if (name === "description") value = rawValue.trim();
    const previous = activeTransaction[name];
    const unchanged = value === null
      ? previous == null
      : String(value) === String(previous ?? "");
    if (!unchanged) payload[name] = value;
  }
  if (Object.keys(payload).length === 0) {
    showError("transaction-edit-error", "No transaction changes to save.");
    return;
  }
  submit.disabled = true;
  clearError("transaction-edit-error");
  try {
    await getJson(`/api/documents/${activeTransaction.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    form.hidden = true;
    await loadTransactions();
    await openTransactionDetails(activeTransaction.id, detailTrigger);
  } catch (error) {
    showError("transaction-edit-error", `Could not save transaction: ${error.message}`);
  } finally {
    submit.disabled = false;
  }
});
byId("accounts-body").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-account-index]");
  if (!button) return;
  activeAccount = state.accounts[Number(button.dataset.accountIndex)];
  const form = byId("account-edit-form");
  setFormValue(form, "bank_name", activeAccount.bank_name);
  setFormValue(form, "account_name", activeAccount.account_name);
  setFormValue(form, "account_number", activeAccount.account_number);
  clearError("account-edit-error");
  byId("account-dialog").showModal();
});
byId("account-edit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const submit = form.querySelector('[type="submit"]');
  const values = new FormData(form);
  const next = Object.fromEntries(values.entries());
  for (const key of Object.keys(next)) next[key] = next[key].trim() || null;
  if (Object.values(next).some((value) => value === null)) {
    showError("account-edit-error", "Bank, account name, and account number are required.");
    return;
  }
  const payload = {
    current_account_number: activeAccount.account_number,
    current_account_name: activeAccount.account_name,
    current_bank_name: activeAccount.bank_name,
    ...next,
  };
  submit.disabled = true;
  clearError("account-edit-error");
  try {
    await getJson("/api/accounts", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    byId("account-dialog").close();
    await loadAccounts();
  } catch (error) {
    showError("account-edit-error", `Could not save account: ${error.message}`);
  } finally {
    submit.disabled = false;
  }
});
byId("refresh-accounts").addEventListener("click", loadAccounts);
byId("close-account-dialog").addEventListener("click", () => byId("account-dialog").close());
byId("cancel-account-edit").addEventListener("click", () => byId("account-dialog").close());
byId("account-dialog").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) event.currentTarget.close();
});
byId("account-dialog").addEventListener("close", () => {
  activeAccount = null;
});
byId("close-dialog").addEventListener("click", () => byId("transaction-dialog").close());
byId("transaction-dialog").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) event.currentTarget.close();
});
byId("transaction-dialog").addEventListener("close", () => {
  detailRequestVersion += 1;
  const image = byId("receipt-image");
  image.onload = null;
  image.onerror = null;
  image.removeAttribute("src");
  const focusTarget = detailTrigger?.isConnected ? detailTrigger : byId("refresh-transactions");
  focusTarget.focus();
  detailTrigger = null;
});

loadJobs();
loadTransactions();
loadAccounts();

setInterval(() => {
  if (!document.hidden) loadJobs({ quiet: true });
}, 5000);
