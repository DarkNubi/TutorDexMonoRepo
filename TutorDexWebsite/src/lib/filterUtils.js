import { canonicalizeSubjectLabels } from "../taxonomy/subjectsTaxonomyV2.js";

export function matchesFilters(job, filters) {
  if (!job || !filters) return true;
  const level = String(filters.level || "").trim();
  const specificLevel = String(filters.specificStudentLevel || "").trim();
  const subjectGeneral = String(filters.subjectGeneral || "").trim();
  const subjectCanonical = String(filters.subjectCanonical || "").trim();
  const location = String(filters.location || "").trim();
  const minRate = filters.minRate ? Number.parseInt(filters.minRate, 10) : null;
  const tutorType = String(filters.tutorType || "").trim();

  if (level && !(Array.isArray(job.signalsLevels) && job.signalsLevels.includes(level))) return false;
  if (specificLevel && !(Array.isArray(job.signalsSpecificLevels) && job.signalsSpecificLevels.includes(specificLevel))) return false;
  if (subjectGeneral && !(Array.isArray(job.subjectsGeneral) && job.subjectsGeneral.includes(subjectGeneral))) return false;
  if (subjectCanonical && !(Array.isArray(job.subjectsCanonical) && job.subjectsCanonical.includes(subjectCanonical))) return false;
  if (location) {
    const needle = String(location).trim().toLowerCase();
    const norm = needle.replace(/\s+/g, "").replace(/_/g, "-");
    const isRegion =
      norm === "north" || norm === "east" || norm === "west" || norm === "central" || norm === "north-east" || norm === "northeast";
    const isOnline = norm === "online";

    if (isRegion) {
      const want = norm === "northeast" ? "north-east" : norm;
      const jobRegion = String(job.region || "")
        .trim()
        .toLowerCase()
        .replace(/\s+/g, "")
        .replace(/_/g, "-");
      if (jobRegion !== want) return false;
    } else if (isOnline) {
      const lm = String(job.learningMode || "").toLowerCase();
      const loc = String(job.location || "").toLowerCase();
      if (!(lm.includes("online") || loc.includes("online"))) return false;
    } else {
      const haystack = String(job.location || "").toLowerCase();
      if (!haystack.includes(needle)) return false;
    }
  }
  if (minRate && typeof job.rateMin === "number" && job.rateMin < minRate) return false;
  if (minRate && typeof job.rateMin !== "number") return false;
  if (tutorType) {
    // job.tutorTypes can be [{canonical, original, confidence}] or absent
    const types = Array.isArray(job.tutorTypes) ? job.tutorTypes : [];
    const has = types.some((t) => {
      if (!t) return false;
      const c = String(t.canonical || "")
        .trim()
        .toLowerCase();
      const o = String(t.original || "")
        .trim()
        .toLowerCase();
      return c === tutorType.toLowerCase() || o === tutorType.toLowerCase();
    });
    if (!has) return false;
  }
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
