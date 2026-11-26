// Thin wrapper around the backend. Same origin as the dashboard (FastAPI mounts /dashboard), so no CORS.
async function apiRequest(path, options = {}) {
  const headers = { Accept: 'application/json', ...(options.headers || {}) };
  if (typeof options.body === 'string') headers['Content-Type'] = 'application/json';
  const response = await fetch(path, { cache: 'no-store', ...options, headers });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const data = await response.json();
      message = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data);
    } catch { /* body was not JSON */ }
    throw new Error(`${response.status}: ${message}`);
  }
  return response.status === 204 ? null : response.json();
}

// Backend limit is 50 per request. Dedupe by key because list order has no tiebreaker.
async function fetchAll(path, { pageSize = 50, maxPages = 40, key = 'id' } = {}) {
  const seen = new Map();
  for (let page = 0; page < maxPages; page++) {
    const joiner = path.includes('?') ? '&' : '?';
    const result = await apiRequest(`${path}${joiner}skip=${page * pageSize}&limit=${pageSize}`);
    const rows = Array.isArray(result) ? result : (result.items || []);
    rows.forEach((row) => seen.set(row[key], row));
    if (rows.length < pageSize) break;
  }
  return [...seen.values()];
}

const json = (method, payload) => ({ method, body: JSON.stringify(payload) });

const Api = {
  health: () => fetch('/health', { cache: 'no-store' }).then((r) => r.ok).catch(() => false),
  listTransactions: () => fetchAll('/api/documents/'),
  getTransaction: (id) => apiRequest(`/api/documents/${encodeURIComponent(id)}`),
  updateTransaction: (id, payload) => apiRequest(`/api/documents/${encodeURIComponent(id)}`, json('PATCH', payload)),
  receiptUrl: (id) => `/api/documents/${encodeURIComponent(id)}/receipt`,
  listUploads: () => fetchAll('/api/documents/uploads', { key: 'upload_id' }),
  getUpload: (id) => apiRequest(`/api/documents/uploads/${encodeURIComponent(id)}`),
  uploadImageUrl: (id) => `/api/documents/uploads/${encodeURIComponent(id)}/image`,
  uploadReceipt(file, key = crypto.randomUUID()) {
    const form = new FormData();
    form.append('file', file);
    return apiRequest('/api/documents/upload', { method: 'POST', body: form, headers: { 'Idempotency-Key': key } });
  },
  listAccounts: () => apiRequest('/api/accounts'),
  updateAccount: (payload) => apiRequest('/api/accounts', json('PATCH', payload)),
};
