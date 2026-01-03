import taxonomy from "../generated/subjects_taxonomy_v2.json";

function uniq(list) {
  const out = [];
  const seen = new Set();
  for (const item of list || []) {
    const s = String(item || "").trim();
    if (!s || seen.has(s)) continue;
    seen.add(s);
    out.push(s);
  }
  return out;
}

const GENERAL_BY_CODE = new Map();
for (const c of taxonomy.general_categories || []) {
  const code = String(c?.code || "").trim();
  const label = String(c?.label || "").trim();
  if (code) GENERAL_BY_CODE.set(code, label || code);
}

const CANON_BY_CODE = new Map();
const CANON_META_BY_CODE = new Map();
for (const s of taxonomy.canonical_subjects || []) {
  const code = String(s?.code || "").trim();
  const label = String(s?.label || "").trim();
  const cat = String(s?.general_category_code || "").trim();
  if (!code) continue;
  CANON_BY_CODE.set(code, label || code);
  CANON_META_BY_CODE.set(code, { code, label: label || code, generalCategoryCode: cat });
}

function normalizeSubjectLabel(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) return "";
  return raw
    .replace(/[–—]/g, "-")
    .replace(/[\\/_&.,()[\\]{}:;|]+/g, " ")
    .replace(/[^a-z0-9+#\\s-]+/g, " ")
    .replace(/-/g, " ")
    .replace(/\\s+/g, " ")
    .trim();
}

const LEVEL_ALIAS = new Map();
for (const [raw, resolved] of Object.entries(taxonomy.level_aliases || {})) {
  const k = normalizeSubjectLabel(raw);
  const v = String(resolved || "").trim();
  if (k && v) LEVEL_ALIAS.set(k, v);
}

const SUBJECT_ALIAS = new Map();
for (const [raw, key] of Object.entries(taxonomy.subject_aliases || {})) {
  const k = normalizeSubjectLabel(raw);
  const v = String(key || "").trim();
  if (k && v) SUBJECT_ALIAS.set(k, v);
}

function resolveLevel(level) {
  const raw = String(level || "").trim();
  if (!raw) return null;
  const n = normalizeSubjectLabel(raw);
  const aliased = LEVEL_ALIAS.get(n);
  if (aliased) return aliased;
  return (taxonomy.levels || []).includes(raw) ? raw : null;
}

export function taxonomyVersion() {
  return Number(taxonomy?.version || 2);
}

export function generalCategoryOptions() {
  return (taxonomy.general_categories || [])
    .map((c) => ({ code: String(c?.code || "").trim(), label: String(c?.label || "").trim() }))
    .filter((c) => c.code && c.label);
}

export function canonicalSubjectOptions() {
  return (taxonomy.canonical_subjects || [])
    .map((s) => ({
      code: String(s?.code || "").trim(),
      label: String(s?.label || "").trim(),
      generalCategoryCode: String(s?.general_category_code || "").trim(),
    }))
    .filter((s) => s.code && s.label);
}

export function labelForGeneralCategoryCode(code) {
  const c = String(code || "").trim();
  return c ? GENERAL_BY_CODE.get(c) || c : "";
}

export function labelForCanonicalCode(code) {
  const c = String(code || "").trim();
  return c ? CANON_BY_CODE.get(c) || c : "";
}

export function labelsForCanonicalCodes(codes) {
  return uniq((codes || []).map((c) => labelForCanonicalCode(c)).filter(Boolean));
}

export function labelsForGeneralCategoryCodes(codes) {
  return uniq((codes || []).map((c) => labelForGeneralCategoryCode(c)).filter(Boolean));
}

export function canonicalSubjectsForLevel(levelCode, { includeAny = false } = {}) {
  const level = String(levelCode || "").trim();
  const byLevel = taxonomy?.mappings?.by_level_subject_key || {};
  const lvlMap = level && byLevel[level] ? byLevel[level] : null;
  const anyMap = includeAny ? byLevel?.ANY || {} : {};

  const codes = [];
  if (lvlMap) {
    Object.values(lvlMap).forEach((arr) => {
      (arr || []).forEach((c) => codes.push(String(c || "").trim()));
    });
  }
  Object.values(anyMap).forEach((arr) => {
    (arr || []).forEach((c) => codes.push(String(c || "").trim()));
  });

  const uniqCodes = uniq(codes).filter((c) => CANON_META_BY_CODE.has(c));
  return uniqCodes.map((c) => CANON_META_BY_CODE.get(c));
}

export function canonicalizeSubjectLabels({ level, subjects } = {}) {
  const levelCode = resolveLevel(level);
  const byLevel = taxonomy?.mappings?.by_level_subject_key || {};
  const lvlMap = levelCode && byLevel[levelCode] ? byLevel[levelCode] : null;
  const anyMap = byLevel?.ANY || {};

  const input = Array.isArray(subjects) ? subjects : subjects ? [subjects] : [];
  const codes = [];
  const general = [];
  const unmapped = [];

  for (const raw of input) {
    const norm = normalizeSubjectLabel(raw);
    if (!norm) continue;
    const key = SUBJECT_ALIAS.get(norm);
    if (!key) {
      unmapped.push(String(raw || ""));
      continue;
    }
    const mapped = (lvlMap && lvlMap[key]) || anyMap[key] || null;
    if (!mapped || !Array.isArray(mapped) || mapped.length === 0) {
      unmapped.push(String(raw || ""));
      continue;
    }
    mapped.forEach((c) => codes.push(String(c || "").trim()));
  }

  const uniqCodes = uniq(codes);
  uniqCodes.forEach((c) => {
    const cat = CANON_META_BY_CODE.get(c)?.generalCategoryCode;
    if (cat) general.push(cat);
  });

  return {
    ok: true,
    subjectsCanonical: uniqCodes,
    subjectsGeneral: uniq(general),
    version: taxonomyVersion(),
    debug: { levelIn: level || null, levelCode, unmapped: unmapped.slice(0, 50) },
  };
}
