import { canonicalizeSubjectLabels } from "../taxonomy/subjectsTaxonomyV2.js";

function _parseList(value) {
  if (value == null) return [];
  if (Array.isArray(value)) return value.map((v) => String(v || "").trim()).filter(Boolean);
  const s = String(value || "").trim();
  if (!s) return [];
  if (s.includes(",")) return s.split(",").map((x) => x.trim()).filter(Boolean);
  return [s];
}

function _matchesAny(haystack, needles) {
  const hs = Array.isArray(haystack) ? haystack.map((x) => String(x || "").trim()).filter(Boolean) : [];
  const ns = _parseList(needles);
  if (!ns.length) return true;
  if (!hs.length) return false;
  const set = new Set(hs);
  return ns.some((n) => set.has(String(n || "").trim()));
}

export function matchesFilters(job, filters) {
  if (!job || !filters) return true;
  const level = String(filters.level || "").trim();
  const specificLevel = String(filters.specificStudentLevel || "").trim();
  const subject = filters.subject;
  const subjectGeneral = filters.subjectGeneral;
  const subjectCanonical = filters.subjectCanonical;
  const location = String(filters.location || "").trim();
  const minRate = filters.minRate ? Number.parseInt(filters.minRate, 10) : null;
  const tutorType = String(filters.tutorType || "").trim();

  if (level && !(Array.isArray(job.signalsLevels) && job.signalsLevels.includes(level))) return false;
  if (specificLevel && !(Array.isArray(job.signalsSpecificLevels) && job.signalsSpecificLevels.includes(specificLevel))) return false;

  // Unified subject filter: OR across tokens matched against general/canonical/signals.
  const tokens = _parseList(subject);
  if (tokens.length) {
    const ok =
      _matchesAny(job.subjectsGeneral, tokens) || _matchesAny(job.subjectsCanonical, tokens) || _matchesAny(job.signalsSubjects, tokens);
    if (!ok) return false;
  } else {
    // Back-compat: separate single-value filters.
    if (!_matchesAny(job.subjectsGeneral, subjectGeneral)) return false;
    if (!_matchesAny(job.subjectsCanonical, subjectCanonical)) return false;
  }

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
      if (jobRegion) {
        if (jobRegion !== want) return false;
      } else {
        // Back-compat: older rows may not have `region`; allow matching against `location` text.
        const jobLocNorm = String(job.location || "")
          .trim()
          .toLowerCase()
          .replace(/\s+/g, "")
          .replace(/_/g, "-");
        if (!(jobLocNorm === want || jobLocNorm.includes(want))) return false;
      }
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
