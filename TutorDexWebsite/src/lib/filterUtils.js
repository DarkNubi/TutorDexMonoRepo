import { canonicalizeSubjectLabels } from "../taxonomy/subjectsTaxonomyV2.js";

export function matchesFilters(job, filters) {
  if (!job || !filters) return true;
  const level = String(filters.level || "").trim();
  const specificLevel = String(filters.specificStudentLevel || "").trim();
  const subjectGeneral = String(filters.subjectGeneral || "").trim();
  const subjectCanonical = String(filters.subjectCanonical || "").trim();
  const location = String(filters.location || "").trim();
  const minRate = filters.minRate ? Number.parseInt(filters.minRate, 10) : null;

  if (level && !(Array.isArray(job.signalsLevels) && job.signalsLevels.includes(level))) return false;
  if (specificLevel && !(Array.isArray(job.signalsSpecificLevels) && job.signalsSpecificLevels.includes(specificLevel))) return false;
  if (subjectGeneral && !(Array.isArray(job.subjectsGeneral) && job.subjectsGeneral.includes(subjectGeneral))) return false;
  if (subjectCanonical && !(Array.isArray(job.subjectsCanonical) && job.subjectsCanonical.includes(subjectCanonical))) return false;
  if (location) {
    const haystack = String(job.location || "").toLowerCase();
    const needle = String(location).toLowerCase();
    if (!haystack.includes(needle)) return false;
  }
  if (minRate && typeof job.rateMin === "number" && job.rateMin < minRate) return false;
  if (minRate && typeof job.rateMin !== "number") return false;
  return true;
}

export function canonicalizePair(level, subject) {
  const subj = String(subject || "").trim();
  if (!subj) return subj;
  const looksLikeCode = subj.includes(".") && subj === subj.toUpperCase();
  if (looksLikeCode) return subj;
  try {
    const res = canonicalizeSubjectLabels({ level: level || null, subjects: [subj] });
    const first = Array.isArray(res?.subjectsCanonical) ? res.subjectsCanonical[0] : null;
    return first || subj;
  } catch {
    return subj;
  }
}
