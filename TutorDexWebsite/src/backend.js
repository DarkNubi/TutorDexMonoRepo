import { debugError, debugLog } from "./debug.js";

const BACKEND_URL = (import.meta.env?.VITE_BACKEND_URL ?? "").trim().replace(/\/$/, "");

async function buildAuthHeaders() {
  try {
    const mod = await import("../auth.js");
    const token = await mod.getIdToken?.();
    if (!token) return {};
    return { authorization: `Bearer ${token}` };
  } catch {
    return {};
  }
}

export function isBackendEnabled() {
  return Boolean(BACKEND_URL);
}

async function backendFetch(path, { method = "GET", body, signal } = {}) {
  const url = `${BACKEND_URL}${path.startsWith("/") ? "" : "/"}${path}`;
  debugLog("Backend request", { method, url });
  const authHeaders = await buildAuthHeaders();
  const headers = { ...authHeaders };
  if (body) headers["content-type"] = "application/json";
  const resp = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    signal,
  });
  debugLog("Backend response", { method, url, status: resp.status, ok: resp.ok });

  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    debugError("Backend request failed", { method, url, status: resp.status, body: (text || "").slice(0, 400) });
    throw new Error(`Backend ${method} ${path} failed (${resp.status}): ${text || resp.statusText}`);
  }

  const data = await resp.json().catch(() => null);
  return data;
}

export async function getTutor(tutorId) {
  if (!isBackendEnabled()) return null;
  void tutorId;
  try {
    return await backendFetch("/me/tutor");
  } catch (e) {
    if (String(e?.message || "").includes("404")) return null;
    throw e;
  }
}

export async function upsertTutor(tutorId, payload) {
  if (!isBackendEnabled()) throw new Error("Backend not configured (VITE_BACKEND_URL missing).");
  void tutorId;
  return backendFetch("/me/tutor", { method: "PUT", body: payload });
}

export async function createTelegramLinkCode(tutorId, { ttlSeconds = 600 } = {}) {
  if (!isBackendEnabled()) throw new Error("Backend not configured (VITE_BACKEND_URL missing).");
  void tutorId;
  void ttlSeconds;
  return backendFetch("/me/telegram/link-code", { method: "POST" });
}

export async function trackEvent({ eventType, assignmentExternalId, agencyName, meta } = {}) {
  if (!isBackendEnabled()) return { ok: false, skipped: true, reason: "backend_disabled" };
  return backendFetch("/analytics/event", {
    method: "POST",
    body: {
      event_type: eventType,
      assignment_external_id: assignmentExternalId || null,
      agency_name: agencyName || null,
      meta: meta || null,
    },
  });
}
