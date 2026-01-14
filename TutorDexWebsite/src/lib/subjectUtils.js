/**
 * Subject utilities for assignments page.
 * 
 * Handles subject key generation, normalization, and labeling.
 */

import { labelForCanonicalCode, labelForGeneralCategoryCode } from "../taxonomy/index.js";

/**
 * Generate unique key for subject.
 * @param {string} type - Subject type ("general" or "canonical")
 * @param {string} code - Subject code
 * @returns {string} Unique key
 */
export function subjectKey(type, code) {
  return `${String(type || "").trim()}:${String(code || "").trim()}`;
}

/**
 * Normalize subject type to "general" or "canonical".
 * @param {string} type - Subject type
 * @returns {"general"|"canonical"} Normalized type
 */
export function normalizeSubjectType(type) {
  const t = String(type || "").trim().toLowerCase();
  return t === "canonical" ? "canonical" : "general";
}

/**
 * Get display label for subject.
 * @param {string} type - Subject type
 * @param {string} code - Subject code
 * @returns {string} Display label
 */
export function subjectLabel(type, code) {
  const c = String(code || "").trim();
  if (!c) return "";
  
  if (normalizeSubjectType(type) === "canonical") {
    return labelForCanonicalCode(c) || c;
  }
  
  return labelForGeneralCategoryCode(c) || c;
}

/**
 * Ensure subject state object is properly initialized.
 * @param {Object} subjects - Subject state object
 * @returns {Object} Initialized subject state
 */
export function ensureSubjectStateInitialized(subjects) {
  if (!subjects || typeof subjects !== "object") {
    subjects = { general: [], canonical: [] };
  }
  if (!Array.isArray(subjects.general)) subjects.general = [];
  if (!Array.isArray(subjects.canonical)) subjects.canonical = [];
  return subjects;
}

/**
 * Parse subject order array.
 * @param {Array} order - Subject order array
 * @returns {Array} Parsed and validated order array
 */
export function parseSubjectOrder(order) {
  if (!Array.isArray(order)) return [];
  
  return order
    .filter((x) => x && typeof x === "object")
    .map((x) => ({
      type: normalizeSubjectType(x?.type),
      code: String(x?.code || "").trim(),
      label: String(x?.label || "").trim(),
    }))
    .filter((x) => x.code);
}

/**
 * Add subject to selection.
 * @param {Object} subjects - Current subject selection
 * @param {Array} order - Current subject order
 * @param {string} type - Subject type
 * @param {string} code - Subject code
 * @param {string} label - Subject label (optional)
 * @param {number} maxChips - Maximum number of chips allowed
 * @returns {Object} Updated state {subjects, order, removed}
 */
export function addSubjectSelection(subjects, order, type, code, label = "", maxChips = 3) {
  subjects = ensureSubjectStateInitialized(subjects);
  order = parseSubjectOrder(order);
  
  const t = normalizeSubjectType(type);
  const c = String(code || "").trim();
  if (!c) return { subjects, order, removed: null };
  
  // Check if already selected (toggle off)
  const existing = new Set((subjects[t] || []).map((x) => String(x || "").trim()));
  if (existing.has(c)) {
    return removeSubjectSelection(subjects, order, type, code);
  }
  
  // Enforce max chips
  let removed = null;
  const total = (subjects.general || []).length + (subjects.canonical || []).length;
  if (total >= maxChips && order.length > 0) {
    const oldest = order[0];
    if (oldest?.type && oldest?.code) {
      const result = removeSubjectSelection(subjects, order, oldest.type, oldest.code);
      subjects = result.subjects;
      order = result.order;
      removed = oldest;
    }
  }
  
  // Add new selection
  subjects[t] = [...(subjects[t] || []), c];
  order = [...order, { type: t, code: c, label: String(label || "").trim() || null }];
  
  return { subjects, order, removed };
}

/**
 * Remove subject from selection.
 * @param {Object} subjects - Current subject selection
 * @param {Array} order - Current subject order
 * @param {string} type - Subject type
 * @param {string} code - Subject code
 * @returns {Object} Updated state {subjects, order}
 */
export function removeSubjectSelection(subjects, order, type, code) {
  subjects = ensureSubjectStateInitialized(subjects);
  order = parseSubjectOrder(order);
  
  const t = normalizeSubjectType(type);
  const c = String(code || "").trim();
  if (!c) return { subjects, order };
  
  // Remove from subjects
  subjects[t] = (subjects[t] || []).filter((x) => String(x || "").trim() !== c);
  
  // Remove from order
  const k = subjectKey(t, c);
  order = order.filter((x) => subjectKey(x?.type, x?.code) !== k);
  
  return { subjects, order };
}

/**
 * Collect subjects as CSV string for API calls.
 * @param {Object} subjects - Subject selection
 * @returns {string} CSV string
 */
export function collectSubjectCsv(subjects) {
  subjects = ensureSubjectStateInitialized(subjects);
  
  const general = (subjects.general || [])
    .map((c) => String(c || "").trim())
    .filter(Boolean);
  
  const canonical = (subjects.canonical || [])
    .map((c) => String(c || "").trim())
    .filter(Boolean);
  
  return [...general, ...canonical].join(",");
}
