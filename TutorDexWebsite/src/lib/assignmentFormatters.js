/**
 * Data formatting utilities for assignments page.
 * 
 * Handles conversion and formatting of assignment data fields.
 */

/**
 * Parse rate value to number.
 * @param {*} value - Rate value (string or number)
 * @returns {number|null} Parsed rate or null
 */
export function parseRate(value) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value !== "string") return null;
  const m = value.match(/(\d{1,3})/);
  if (!m) return null;
  const n = Number.parseInt(m[1], 10);
  return Number.isFinite(n) ? n : null;
}

/**
 * Pick first non-empty value from array or return value.
 * @param {*} value - Value or array
 * @returns {string} First non-empty value
 */
export function pickFirst(value) {
  if (Array.isArray(value)) {
    for (const item of value) {
      const v = pickFirst(item);
      if (v) return v;
    }
    return "";
  }
  return typeof value === "string" ? value.trim() : "";
}

/**
 * Convert value to text string.
 * @param {*} value - Value to convert
 * @returns {string} Text representation
 */
export function toText(value) {
  if (value == null) return "";
  if (Array.isArray(value)) return pickFirst(value);
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  try {
    return String(value).trim();
  } catch {
    return "";
  }
}

/**
 * Convert value to string list.
 * Handles JSON arrays, newline-separated strings, and single values.
 * @param {*} value - Value to convert
 * @returns {string[]} Array of strings
 */
export function toStringList(value) {
  if (value == null) return [];
  if (Array.isArray(value)) {
    return value
      .flatMap((v) => toStringList(v))
      .map((v) => String(v).trim())
      .filter(Boolean);
  }
  const s = String(value).trim();
  if (!s) return [];

  // If the API/DB stores a JSON-encoded list in a string, prefer that.
  if (s.startsWith("[") && s.endsWith("]")) {
    try {
      const parsed = JSON.parse(s);
      if (Array.isArray(parsed)) {
        return parsed.map((x) => String(x || "").trim()).filter(Boolean);
      }
    } catch {}
  }

  // If the backend stores multi-line notes in a single string, treat each line as an item.
  if (s.includes("\n"))
    return s
      .split("\n")
      .map((x) => x.trim())
      .filter(Boolean);
  return [s];
}

/**
 * Format relative time from ISO string.
 * @param {string} isoString - ISO date string
 * @returns {string} Formatted relative time (e.g., "2h ago")
 */
export function formatRelativeTime(isoString) {
  const t = Date.parse(String(isoString || ""));
  if (!Number.isFinite(t)) return "";
  const deltaMs = Date.now() - t;
  if (!Number.isFinite(deltaMs)) return "";
  const mins = Math.floor(deltaMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/**
 * Format short date from ISO string.
 * @param {string} isoString - ISO date string
 * @returns {string} Formatted date
 */
export function formatShortDate(isoString) {
  const t = Date.parse(String(isoString || ""));
  if (!Number.isFinite(t)) return "";
  try {
    const d = new Date(t);
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

/**
 * Format distance in kilometers.
 * @param {number} km - Distance in kilometers
 * @param {boolean} isEstimated - Whether distance is estimated
 * @returns {string} Formatted distance string
 */
export function formatDistanceKm(km, isEstimated = false) {
  const n = typeof km === "number" ? km : Number.parseFloat(String(km || ""));
  if (!Number.isFinite(n)) return "";
  const distStr = n < 10 ? `~${n.toFixed(1)} km` : `~${Math.round(n)} km`;
  return isEstimated ? `${distStr} (estimated)` : distStr;
}
