/**
 * Local storage utilities for assignments page.
 * 
 * Handles reading/writing filters, view mode, and visit tracking.
 */

const FILTERS_STORAGE_KEY = "tutordex_assignments_filters_v1";
const VIEW_MODE_STORAGE_KEY = "tutordex_assignments_view_mode_v1";
const LAST_VISIT_STORAGE_KEY = "tutordex_assignments_last_visit_ms_v1";

/**
 * Read view mode from local storage.
 * @returns {"full"|"compact"} View mode
 */
export function readViewMode() {
  try {
    const raw = String(localStorage.getItem(VIEW_MODE_STORAGE_KEY) || "")
      .trim()
      .toLowerCase();
    return raw === "compact" ? "compact" : "full";
  } catch {
    return "full";
  }
}

/**
 * Write view mode to local storage.
 * @param {"full"|"compact"} mode - View mode to save
 */
export function writeViewMode(mode) {
  try {
    localStorage.setItem(VIEW_MODE_STORAGE_KEY, mode);
  } catch {
    // Ignore storage errors
  }
}

/**
 * Read last visit timestamp from local storage.
 * @returns {number} Timestamp in milliseconds, or 0 if not found
 */
export function readLastVisitMs() {
  try {
    const raw = localStorage.getItem(LAST_VISIT_STORAGE_KEY);
    if (!raw) return 0;
    const ms = Number.parseInt(raw, 10);
    return Number.isFinite(ms) && ms > 0 ? ms : 0;
  } catch {
    return 0;
  }
}

/**
 * Write last visit timestamp to local storage.
 * @param {number} ms - Timestamp in milliseconds
 */
export function writeLastVisitMs(ms) {
  try {
    if (typeof ms === "number" && Number.isFinite(ms) && ms > 0) {
      localStorage.setItem(LAST_VISIT_STORAGE_KEY, String(ms));
    }
  } catch {
    // Ignore storage errors
  }
}

/**
 * Read filters from local storage.
 * @returns {Object|null} Saved filters or null
 */
export function readFilters() {
  try {
    const raw = localStorage.getItem(FILTERS_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

/**
 * Write filters to local storage.
 * @param {Object} filters - Filters object to save
 */
export function writeFilters(filters) {
  try {
    if (filters && typeof filters === "object") {
      localStorage.setItem(FILTERS_STORAGE_KEY, JSON.stringify(filters));
    }
  } catch {
    // Ignore storage errors
  }
}

/**
 * Clear all saved data from local storage.
 */
export function clearAllSaved() {
  try {
    localStorage.removeItem(FILTERS_STORAGE_KEY);
    localStorage.removeItem(VIEW_MODE_STORAGE_KEY);
    localStorage.removeItem(LAST_VISIT_STORAGE_KEY);
  } catch {
    // Ignore storage errors
  }
}
