import { debugError, debugLog } from "./debug.js";

const BACKEND_URL = (import.meta.env?.VITE_BACKEND_URL ?? "").trim().replace(/\/$/, "");

async function buildAuthHeaders({ forceRefresh = false } = {}) {
  try {
    const mod = await import("../auth.js");
    const token = await mod.getIdToken?.(forceRefresh);
    if (!token) return {};
    return { Authorization: `Bearer ${token}` };
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

  async function doFetch({ forceRefresh = false } = {}) {
    const authHeaders = await buildAuthHeaders({ forceRefresh });
    const headers = { ...authHeaders };
    if (body) headers["content-type"] = "application/json";
    return fetch(url, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    });
  }

  let resp = await doFetch();
  if (resp.status === 401) {
    // Token can be stale; retry once with a refreshed Firebase ID token.
    resp = await doFetch({ forceRefresh: true });
  }
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

export async function getRecentMatchCounts({ levels, subjects, subjectsCanonical, subjectsGeneral, specificStudentLevels } = {}) {
  if (!isBackendEnabled()) throw new Error("Backend not configured (VITE_BACKEND_URL missing).");
  return backendFetch("/me/assignments/match-counts", {
    method: "POST",
    body: {
      levels: Array.isArray(levels) ? levels : null,
      specific_student_levels: Array.isArray(specificStudentLevels) ? specificStudentLevels : null,
      subjects: Array.isArray(subjects) ? subjects : null,
      subjects_canonical: Array.isArray(subjectsCanonical) ? subjectsCanonical : null,
      subjects_general: Array.isArray(subjectsGeneral) ? subjectsGeneral : null,
    },
  });
}

export async function fetchAssignmentDuplicates(assignmentId) {
  if (!isBackendEnabled()) throw new Error("Backend not configured (VITE_BACKEND_URL missing).");
  return backendFetch(`/assignments/${assignmentId}/duplicates`);
}

export async function fetchDuplicateGroup(groupId) {
  if (!isBackendEnabled()) throw new Error("Backend not configured (VITE_BACKEND_URL missing).");
  return backendFetch(`/duplicate-groups/${groupId}`);
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

export function sendClickBeacon({
  eventType = "click",
  assignmentExternalId = null,
  destinationType = null,
  destinationUrl = null,
  meta = null,
} = {}) {
  if (!isBackendEnabled()) return false;

  const payload = {
    event_type: eventType,
    assignment_external_id: assignmentExternalId,
    destination_type: destinationType,
    destination_url: destinationUrl,
    timestamp_ms: Date.now(),
    meta,
  };

  const url = `${BACKEND_URL}/track`;
  const body = JSON.stringify(payload);

  try {
    if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
      const blob = new Blob([body], { type: "application/json" });
      return navigator.sendBeacon(url, blob);
    }
  } catch (e) {
    debugError("sendBeacon failed", e);
  }

  try {
    void fetch(url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body,
      keepalive: true,
    });
    return true;
  } catch (e) {
    debugError("click beacon fetch failed", e);
    return false;
  }
}

export async function listOpenAssignmentsPaged({
  limit = 50,
  cursorLastSeen = null,
  cursorId = null,
  cursorDistanceKm = null,
  sort = null,
  level = null,
  specificStudentLevel = null,
  subject = null,
  subjectGeneral = null,
  subjectCanonical = null,
  agencyName = null,
  learningMode = null,
  location = null,
  minRate = null,
  tutorType = null,
  showDuplicates = true,
} = {}) {
  if (!isBackendEnabled()) throw new Error("Backend not configured (VITE_BACKEND_URL missing).");

  const params = new URLSearchParams();
  params.set("limit", String(limit));
  if (sort) params.set("sort", String(sort));
  if (cursorLastSeen) params.set("cursor_last_seen", String(cursorLastSeen));
  if (cursorId !== null && cursorId !== undefined) params.set("cursor_id", String(cursorId));
  if (cursorDistanceKm !== null && cursorDistanceKm !== undefined) params.set("cursor_distance_km", String(cursorDistanceKm));
  if (level) params.set("level", String(level));
  if (specificStudentLevel) params.set("specific_student_level", String(specificStudentLevel));
  if (subject) params.set("subject", String(subject));
  if (subjectGeneral) params.set("subject_general", String(subjectGeneral));
  if (subjectCanonical) params.set("subject_canonical", String(subjectCanonical));
  if (agencyName) params.set("agency_name", String(agencyName));
  if (learningMode) params.set("learning_mode", String(learningMode));
  if (location) params.set("location", String(location));
  if (minRate !== null && minRate !== undefined && String(minRate).trim() !== "") params.set("min_rate", String(minRate));
  params.set("show_duplicates", showDuplicates ? "true" : "false");
  if (tutorType) params.set("tutor_type", String(tutorType));

  return backendFetch(`/assignments?${params.toString()}`);
}

export async function getOpenAssignmentFacets({
  level = null,
  specificStudentLevel = null,
  subject = null,
  subjectGeneral = null,
  subjectCanonical = null,
  agencyName = null,
  learningMode = null,
  location = null,
  minRate = null,
  tutorType = null,
} = {}) {
  if (!isBackendEnabled()) throw new Error("Backend not configured (VITE_BACKEND_URL missing).");

  const params = new URLSearchParams();
  if (level) params.set("level", String(level));
  if (specificStudentLevel) params.set("specific_student_level", String(specificStudentLevel));
  if (subject) params.set("subject", String(subject));
  if (subjectGeneral) params.set("subject_general", String(subjectGeneral));
  if (subjectCanonical) params.set("subject_canonical", String(subjectCanonical));
  if (agencyName) params.set("agency_name", String(agencyName));
  if (learningMode) params.set("learning_mode", String(learningMode));
  if (location) params.set("location", String(location));
  if (minRate !== null && minRate !== undefined && String(minRate).trim() !== "") params.set("min_rate", String(minRate));
  if (tutorType) params.set("tutor_type", String(tutorType));

  return backendFetch(`/assignments/facets?${params.toString()}`);
}
