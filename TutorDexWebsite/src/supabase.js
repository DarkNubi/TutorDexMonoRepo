import { debugError, debugLog, redactToken } from "./debug.js";

const SUPABASE_URL = (import.meta.env?.VITE_SUPABASE_URL ?? "").trim().replace(/\/$/, "");
const SUPABASE_ANON_KEY = (import.meta.env?.VITE_SUPABASE_ANON_KEY ?? "").trim();
const ASSIGNMENTS_TABLE = (import.meta.env?.VITE_SUPABASE_ASSIGNMENTS_TABLE ?? "").trim() || "assignments";

export function isSupabaseEnabled() {
  return Boolean(SUPABASE_URL && SUPABASE_ANON_KEY && ASSIGNMENTS_TABLE);
}

export function getSupabaseConfigSummary() {
  let host = "";
  try {
    host = SUPABASE_URL ? new URL(SUPABASE_URL).host : "";
  } catch {
    host = "";
  }

  return {
    enabled: isSupabaseEnabled(),
    urlPresent: Boolean(SUPABASE_URL),
    urlHost: host || "",
    table: ASSIGNMENTS_TABLE || "",
    anonKeyPresent: Boolean(SUPABASE_ANON_KEY),
    anonKeyPreview: redactToken(SUPABASE_ANON_KEY),
    mode: import.meta.env?.MODE || "",
    baseUrl: import.meta.env?.BASE_URL || "",
  };
}

async function supabaseGet(path, { signal } = {}) {
  const url = `${SUPABASE_URL}/rest/v1/${path.replace(/^\//, "")}`;
  debugLog("Supabase GET", { url });
  const resp = await fetch(url, {
    method: "GET",
    headers: {
      apikey: SUPABASE_ANON_KEY,
      authorization: `Bearer ${SUPABASE_ANON_KEY}`,
    },
    signal,
  });
  debugLog("Supabase response", { url, status: resp.status, ok: resp.ok });

  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    debugError("Supabase GET failed", { url, status: resp.status, body: (text || "").slice(0, 400) });
    throw new Error(`Supabase GET failed (${resp.status}): ${text || resp.statusText}`);
  }

  const data = await resp.json();
  if (!Array.isArray(data)) return [];
  return data;
}

function parseRate(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string") return null;
  const m = value.match(/(\d{1,3})/);
  if (!m) return null;
  const n = Number.parseInt(m[1], 10);
  return Number.isFinite(n) ? n : null;
}

function pickFirst(value) {
  if (Array.isArray(value)) {
    for (const item of value) {
      const v = pickFirst(item);
      if (v) return v;
    }
    return "";
  }
  return typeof value === "string" ? value.trim() : "";
}

export async function listOpenAssignments({ limit = 200 } = {}) {
  if (!isSupabaseEnabled()) return [];

  const baseCols =
    "id,external_id,message_link,agency_name,learning_mode,subject,subjects,level,specific_student_level,address,postal_code,nearest_mrt,frequency,duration,hourly_rate,rate_min,rate_max,student_gender,tutor_gender,status,created_at,last_seen";
  const optionalCols = ["freshness_tier"];

  const params = new URLSearchParams();
  params.set("status", "eq.open");
  params.set("order", "created_at.desc");
  params.set("limit", String(limit));

  let rows = [];
  const missingCols = new Set();
  for (let attempt = 0; attempt < 4; attempt++) {
    const selectCols = [baseCols, ...optionalCols.filter((c) => !missingCols.has(c))].join(",");
    params.set("select", selectCols);
    try {
      rows = await supabaseGet(`${ASSIGNMENTS_TABLE}?${params.toString()}`);
      break;
    } catch (e) {
      const msg = String(e?.message || e || "").toLowerCase();
      const matched = optionalCols.find((c) => msg.includes(c.toLowerCase()));
      if (!matched) throw e;
      missingCols.add(matched);
    }
  }

  return rows.map((row) => {
    const subject = (row?.subject || "").trim() || pickFirst(row?.subjects) || "Unknown";

    const learningMode = (row?.learning_mode || "").trim();
    const hasPhysicalLocation = Boolean(
      (row?.address || "").trim() || (row?.postal_code || "").trim() || (row?.nearest_mrt || "").trim()
    );
    const lm = learningMode.toLowerCase();
    const isOnlineOnly = Boolean(learningMode) && lm.includes("online") && !lm.includes("hybrid") && !lm.includes("face");

    const location = isOnlineOnly && !hasPhysicalLocation
      ? "Online"
      : (row?.address || "").trim() || (row?.postal_code || "").trim() || (row?.nearest_mrt || "").trim() || "Unknown";

    const rate = row?.rate_min ?? parseRate(row?.hourly_rate);

    const freqBits = [];
    if (row?.frequency) freqBits.push(String(row.frequency).trim());
    if (row?.duration) freqBits.push(String(row.duration).trim());

    return {
      id: (row?.external_id || `DB-${row?.id || ""}`).trim(),
      messageLink: (row?.message_link || "").trim(),
      level: (row?.level || "").trim(),
      specificLevel: (row?.specific_student_level || "").trim(),
      subject,
      location,
      rate: typeof rate === "number" && Number.isFinite(rate) ? rate : null,
      gender: (row?.tutor_gender || row?.student_gender || "Any").trim(),
      freshnessTier: (row?.freshness_tier || "").trim() || "green",
      freq: freqBits.join(" / "),
      agencyName: (row?.agency_name || "").trim(),
      learningMode,
      updatedAt: (row?.last_seen || row?.created_at || "").trim(),
    };
  });
}
