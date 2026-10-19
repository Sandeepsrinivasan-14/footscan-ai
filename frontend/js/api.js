/* REST client for the FootScan API. Contract: see /api/docs.
   The optional API key lives in sessionStorage (this tab only) and is sent as X-API-Key. */

const KEY_STORAGE = "footscan.apiKey";

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export function getApiKey() {
  try {
    return sessionStorage.getItem(KEY_STORAGE) || "";
  } catch {
    return "";
  }
}

export function setApiKey(value) {
  try {
    if (value) sessionStorage.setItem(KEY_STORAGE, value);
    else sessionStorage.removeItem(KEY_STORAGE);
  } catch {
    /* storage unavailable (private mode or blocked): the key just does not persist across reloads */
  }
}

function authHeaders(headers = {}) {
  const key = getApiKey();
  return key ? { ...headers, "X-API-Key": key } : headers;
}

function errorMessage(status, body) {
  const detail = body && body.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d) => `${(d.loc || []).slice(1).join(".") || "input"}: ${d.msg}`).join("; ");
  }
  if (status === 429) return "Too many requests. Please wait a moment and try again.";
  if (status === 503) return "The segmentation model is not available on the server.";
  return `Request failed (${status})`;
}

function failure(status, body) {
  if (status === 401) window.dispatchEvent(new CustomEvent("footscan:auth-required"));
  return new ApiError(status, errorMessage(status, body));
}

async function request(path, options = {}) {
  let resp;
  try {
    resp = await fetch(path, { ...options, headers: authHeaders(options.headers) });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your connection and try again.");
  }
  const isJson = (resp.headers.get("content-type") || "").includes("application/json");
  const body = isJson ? await resp.json().catch(() => null) : null;
  if (!resp.ok) throw failure(resp.status, body);
  return body;
}

/** multipart POST via XHR so we can report real upload progress (fetch cannot). */
function postForm(path, formData, onUploadProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", path);
    for (const [k, v] of Object.entries(authHeaders())) xhr.setRequestHeader(k, v);
    xhr.responseType = "json";
    if (onUploadProgress) {
      xhr.upload.onprogress = (e) => e.lengthComputable && onUploadProgress(e.loaded / e.total);
      xhr.upload.onload = () => onUploadProgress(1);
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response);
      else reject(failure(xhr.status, xhr.response));
    };
    xhr.onerror = () => reject(new ApiError(0, "Cannot reach the server. Check your connection and try again."));
    xhr.ontimeout = () => reject(new ApiError(0, "The request timed out."));
    xhr.timeout = 120_000;
    xhr.send(formData);
  });
}

export const api = {
  health: () => request("/health"),
  analyze: (formData, onProgress) => postForm("/api/analyze", formData, onProgress),
  compare: (formData, onProgress) => postForm("/api/compare", formData, onProgress),
  listPatients: () => request("/api/patients?limit=1000"),
  createPatient: (name) =>
    request("/api/patients", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  patientScans: (id) => request(`/api/patients/${encodeURIComponent(id)}/scans`),
};

/* Authenticated binary fetches. <img src> and <a href> cannot send X-API-Key, so we fetch the
   bytes and hand the browser a blob: URL instead. */

const blobCache = new Map();

async function fetchBlob(path) {
  let resp;
  try {
    resp = await fetch(path, { headers: authHeaders() });
  } catch {
    throw new ApiError(0, "Cannot reach the server.");
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw failure(resp.status, body);
  }
  return resp.blob();
}

export function scanImageUrl(scanId, kind = "overlay") {
  const path = `/api/scans/${encodeURIComponent(scanId)}/image/${kind}`;
  if (!blobCache.has(path)) {
    const pending = fetchBlob(path).then((b) => URL.createObjectURL(b));
    pending.catch(() => blobCache.delete(path));
    blobCache.set(path, pending);
  }
  return blobCache.get(path);
}

export async function downloadReport(scanId, patientName) {
  const q = patientName ? `?patient_name=${encodeURIComponent(patientName)}` : "";
  const blob = await fetchBlob(`/api/scans/${encodeURIComponent(scanId)}/report${q}`);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `footscan_report_${scanId}.pdf`;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
