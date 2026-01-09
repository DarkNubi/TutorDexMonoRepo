import { getCurrentUid, waitForAuth } from "../auth.js";
import { getOpenAssignmentFacets, getTutor, isBackendEnabled, listOpenAssignmentsPaged, sendClickBeacon, trackEvent } from "./backend.js";
import { debugLog, isDebugEnabled } from "./debug.js";
import { SPECIFIC_LEVELS } from "./academicEnums.js";
import {
  canonicalSubjectsForLevel,
  generalCategoryOptions,
  labelForCanonicalCode,
  labelForGeneralCategoryCode,
  labelsForCanonicalCodes,
  labelsForGeneralCategoryCodes,
  searchSubjects,
} from "./taxonomy/subjectsTaxonomyV2.js";
import { matchesFilters } from "./lib/filterUtils.js";

const BUILD_TIME = typeof __BUILD_TIME__ !== "undefined" ? __BUILD_TIME__ : "";

const specificLevelsData = SPECIFIC_LEVELS || {};
const FILTERS_STORAGE_KEY = "tutordex_assignments_filters_v1";
const VIEW_MODE_STORAGE_KEY = "tutordex_assignments_view_mode_v1";
const LAST_VISIT_STORAGE_KEY = "tutordex_assignments_last_visit_ms_v1";

// --- 3. RENDER FUNCTIONS ---
const grid = document.getElementById("assignments-grid");
const noResults = document.getElementById("no-results");
const countLabel = document.getElementById("job-count");
const resultsSummary = document.getElementById("results-summary");
const loadError = document.getElementById("load-error");
const loadErrorMessage = document.getElementById("load-error-message");
const retryLoadBtn = document.getElementById("retry-load-assignments");
const loadMoreBtn = document.getElementById("load-more");
const facetHint = document.getElementById("facet-hint");
let allAssignments = [];
let totalAssignments = 0;
let nextCursorLastSeen = null;
let nextCursorId = null;
let nextCursorDistanceKm = null;
let lastFacets = null;
let activeLoadToken = 0;
let hasPostalCoords = null;
let didRestoreFiltersFromStorage = false;
let viewMode = "full";
let lastVisitCutoffMs = 0;
let myTutorProfile = null;
let didWriteLastVisitThisSession = false;
let currentUid = null;

// Lightweight DOM cache helper to reduce repeated queries and guard existence.
const _elCache = new Map();
function $id(id) {
  if (!_elCache.has(id)) _elCache.set(id, document.getElementById(id));
  return _elCache.get(id);
}

// Pending selections preserved across async facet refreshes
const pendingFilters = { level: null, specificStudentLevel: null, subjectGeneral: null, subjectCanonical: null };

function getOrCreateStatusEl() {
  const host = document.querySelector(".max-w-6xl") || document.body;
  let el = document.getElementById("data-source-status");
  if (el) return el;
  el = document.createElement("div");
  el.id = "data-source-status";
  el.className = "text-sm font-medium text-gray-500 mt-2 flex items-center gap-3";

  const text = document.createElement("span");
  text.id = "data-source-status-text";
  el.appendChild(text);

  const retry = document.createElement("button");
  retry.id = "data-source-status-retry";
  retry.type = "button";
  retry.className = "hidden text-xs font-bold uppercase underline";
  retry.textContent = "Retry";
  retry.addEventListener("click", () => loadAssignments());
  el.appendChild(retry);

  host.prepend(el);
  return el;
}

function setStatus(message, kind = "info", { showRetry = false } = {}) {
  const el = getOrCreateStatusEl();
  const text = el.querySelector("#data-source-status-text");
  const retry = el.querySelector("#data-source-status-retry");
  if (text) text.textContent = message || "";
  if (retry) retry.classList.toggle("hidden", !showRetry);

  el.className = "text-sm font-medium mt-2 flex items-center gap-3";
  if (kind === "error") el.className += " text-red-600";
  else if (kind === "success") el.className += " text-green-600";
  else if (kind === "warning") el.className += " text-yellow-700";
  else el.className += " text-gray-500";
}

function updateGridLayout() {
  if (!grid) return;
  if (viewMode === "compact") {
    grid.className = "grid grid-cols-1 gap-3";
  } else {
    grid.className = "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6";
  }
}

function setViewMode(next) {
  viewMode = next === "compact" ? "compact" : "full";
  writeViewMode(viewMode);
  updateViewToggleUI();
  updateGridLayout();
  renderCards(allAssignments);
}

function updateViewToggleUI() {
  const fullBtn = document.getElementById("view-toggle-full");
  const compactBtn = document.getElementById("view-toggle-compact");
  if (fullBtn) fullBtn.classList.toggle("bg-black", viewMode === "full");
  if (fullBtn) fullBtn.classList.toggle("text-white", viewMode === "full");
  if (compactBtn) compactBtn.classList.toggle("bg-black", viewMode === "compact");
  if (compactBtn) compactBtn.classList.toggle("text-white", viewMode === "compact");
}

function setResultsSummary(showing, total) {
  if (!resultsSummary) return;
  const s = Number.isFinite(showing) ? showing : 0;
  const t = Number.isFinite(total) ? total : 0;
  resultsSummary.textContent = `Showing ${s} of ${t}`;
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

function toText(value) {
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

function toStringList(value) {
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

function readViewMode() {
  try {
    const raw = String(localStorage.getItem(VIEW_MODE_STORAGE_KEY) || "")
      .trim()
      .toLowerCase();
    return raw === "compact" ? "compact" : "full";
  } catch {
    return "full";
  }
}

function writeViewMode(mode) {
  try {
    localStorage.setItem(VIEW_MODE_STORAGE_KEY, mode === "compact" ? "compact" : "full");
  } catch {}
}

function readLastVisitMs() {
  try {
    const raw = localStorage.getItem(LAST_VISIT_STORAGE_KEY);
    const n = raw ? Number.parseInt(raw, 10) : 0;
    return Number.isFinite(n) ? n : 0;
  } catch {
    return 0;
  }
}

function writeLastVisitMs(ms) {
  try {
    localStorage.setItem(LAST_VISIT_STORAGE_KEY, String(Math.max(0, Number(ms) || 0)));
  } catch {}
}

function mapAssignmentRow(row) {
  const learningMode = toText(row?.learning_mode);
  const address = pickFirst(row?.address);
  const postal = pickFirst(row?.postal_code);
  const postalEstimated = pickFirst(row?.postal_code_estimated);
  const mrt = pickFirst(row?.nearest_mrt);
  const hasPhysicalLocation = Boolean(address || postal || mrt);
  const lm = learningMode.toLowerCase();
  const isOnlineOnly = Boolean(learningMode) && lm.includes("online") && !lm.includes("hybrid") && !lm.includes("face");

  const location = (() => {
    if (isOnlineOnly && !hasPhysicalLocation) return "Online";
    if (address || postal || mrt) return address || postal || mrt || "Unknown";
    if (postalEstimated) return `Estimated postal: ${postalEstimated} (estimated)`;
    return "Unknown";
  })();

  const rateMin = typeof row?.rate_min === "number" ? row.rate_min : parseRate(row?.rate_raw_text);
  const rateMax = typeof row?.rate_max === "number" ? row.rate_max : null;

  let distanceKm = null;
  const dk = row?.distance_km;
  if (typeof dk === "number" && Number.isFinite(dk)) distanceKm = dk;
  else if (typeof dk === "string") {
    const parsed = Number.parseFloat(dk.trim());
    if (Number.isFinite(parsed)) distanceKm = parsed;
  }

  const timeNotes = toStringList(row?.time_availability_note);
  const scheduleNotes = toStringList(row?.lesson_schedule);

  const externalId = toText(row?.external_id);
  const internalId = row?.id != null ? String(row.id).trim() : "";
  const subjectsCanonical = toStringList(row?.subjects_canonical);
  const subjectsGeneral = toStringList(row?.subjects_general);
  let tutorTypes = [];
  try {
    if (Array.isArray(row?.tutor_types)) tutorTypes = row.tutor_types;
    else if (typeof row?.tutor_types === "string") {
      tutorTypes = JSON.parse(row.tutor_types || "[]") || [];
    }
  } catch (e) {
    tutorTypes = [];
  }
  let rateBreakdown = {};
  try {
    if (typeof row?.rate_breakdown === "object" && row?.rate_breakdown) rateBreakdown = row.rate_breakdown;
    else if (typeof row?.rate_breakdown === "string") {
      rateBreakdown = JSON.parse(row.rate_breakdown || "{}") || {};
    }
  } catch (e) {
    rateBreakdown = {};
  }

  return {
    id: externalId || (internalId ? `DB-${internalId}` : ""),
    messageLink: toText(row?.message_link),
    assignmentCode: toText(row?.assignment_code),
    academicDisplayText: toText(row?.academic_display_text) || "Tuition Assignment",
    signalsSubjects: toStringList(row?.signals_subjects),
    signalsLevels: toStringList(row?.signals_levels),
    signalsSpecificLevels: toStringList(row?.signals_specific_student_levels),
    subjectsCanonical,
    subjectsGeneral,
    subjectsCanonicalLabels: labelsForCanonicalCodes(subjectsCanonical),
    subjectsGeneralLabels: labelsForGeneralCategoryCodes(subjectsGeneral),
    location,
    region: toText(row?.region),
    nearestMrt: toText(row?.nearest_mrt_computed),
    nearestMrtLine: toText(row?.nearest_mrt_computed_line),
    nearestMrtDistanceM: (() => {
      const v = row?.nearest_mrt_computed_distance_m;
      if (typeof v === "number" && Number.isFinite(v)) return v;
      const s = String(v || "").trim();
      if (!s) return null;
      const n = Number.parseInt(s, 10);
      return Number.isFinite(n) ? n : null;
    })(),
    distanceKm,
    postalCoordsEstimated: row?.postal_coords_estimated === true,
    rateMin: typeof rateMin === "number" && Number.isFinite(rateMin) ? rateMin : null,
    rateMax: typeof rateMax === "number" && Number.isFinite(rateMax) ? rateMax : null,
    rateRawText: toText(row?.rate_raw_text),
    freshnessTier: toText(row?.freshness_tier) || "green",
    timeNotes,
    scheduleNotes,
    startDate: toText(row?.start_date),
    agencyName: toText(row?.agency_name),
    learningMode,
    postedAt: toText(row?.published_at || row?.created_at || row?.last_seen),
    bumpedAt: toText(row?.source_last_seen || row?.published_at || row?.last_seen),
    processedAt: toText(row?.last_seen),
    postalCode: postal,
    postalEstimated,
    tutorTypes,
    rateBreakdown,
  };
}

function formatRelativeTime(isoString) {
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

function formatShortDate(isoString) {
  const t = Date.parse(String(isoString || ""));
  if (!Number.isFinite(t)) return "";
  try {
    const d = new Date(t);
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return "";
  }
}

function hasMatchForMe(job) {
  const me = myTutorProfile;
  if (!me) return false;
  const mySubjects = new Set(toStringList(me.subjects));
  const myLevels = new Set(toStringList(me.levels));
  const mySpecific = new Set(toStringList(me.specific_student_levels || me.specificStudentLevels || []));

  const subjHit = Array.isArray(job.subjectsCanonical) && job.subjectsCanonical.some((c) => mySubjects.has(String(c || "").trim()));
  const lvlHit = Array.isArray(job.signalsLevels) && job.signalsLevels.some((l) => myLevels.has(String(l || "").trim()));
  const specHit = Array.isArray(job.signalsSpecificLevels) && job.signalsSpecificLevels.some((l) => mySpecific.has(String(l || "").trim()));

  return Boolean(subjHit || specHit || lvlHit);
}

function matchDetails(job) {
  const me = myTutorProfile;
  if (!me) return [];
  const mySubjects = new Set(toStringList(me.subjects));
  const myLevels = new Set(toStringList(me.levels));
  const mySpecific = new Set(toStringList(me.specific_student_levels || me.specificStudentLevels || []));
  const out = [];
  if (Array.isArray(job.subjectsCanonical) && job.subjectsCanonical.some((c) => mySubjects.has(String(c || "").trim()))) out.push("Subject");
  if (Array.isArray(job.signalsSpecificLevels) && job.signalsSpecificLevels.some((l) => mySpecific.has(String(l || "").trim())))
    out.push("Specific level");
  if (Array.isArray(job.signalsLevels) && job.signalsLevels.some((l) => myLevels.has(String(l || "").trim()))) out.push("Level");
  return out;
}

function formatDistanceKm(km, isEstimated = false) {
  const n = typeof km === "number" ? km : Number.parseFloat(String(km || ""));
  if (!Number.isFinite(n)) return "";
  const distStr = n < 10 ? `~${n.toFixed(1)} km` : `~${Math.round(n)} km`;
  return isEstimated ? `${distStr} (estimated)` : distStr;
}

function renderSkeleton(count = 6) {
  grid.innerHTML = "";
  updateGridLayout();
  noResults.classList.add("hidden");
  countLabel.innerText = "...";
  setResultsSummary(0, 0);
  if (loadMoreBtn) loadMoreBtn.classList.add("hidden");
  if (facetHint) facetHint.classList.add("hidden");

  for (let i = 0; i < count; i++) {
    const card = document.createElement("div");
    card.className = "job-card bg-white dark:bg-gray-800 rounded-xl p-6 relative flex flex-col justify-between h-full animate-pulse";
    card.innerHTML = `
      <div>
        <div class="flex justify-between items-start mb-4">
          <div class="h-6 w-24 bg-gray-100 dark:bg-gray-700 rounded-full"></div>
          <div class="h-6 w-16 bg-gray-100 dark:bg-gray-700 rounded-full"></div>
          <div class="h-6 w-14 bg-gray-100 dark:bg-gray-700 rounded"></div>
        </div>
        <div class="h-8 w-2/3 bg-gray-100 dark:bg-gray-700 rounded mb-3"></div>
        <div class="h-4 w-1/2 bg-gray-100 dark:bg-gray-700 rounded mb-6"></div>
        <div class="space-y-3 mb-8">
          <div class="h-4 w-5/6 bg-gray-100 dark:bg-gray-700 rounded"></div>
          <div class="h-4 w-4/6 bg-gray-100 dark:bg-gray-700 rounded"></div>
          <div class="h-4 w-3/6 bg-gray-100 dark:bg-gray-700 rounded"></div>
        </div>
      </div>
      <div class="h-12 w-full bg-gray-100 dark:bg-gray-700 rounded-lg"></div>
    `.trim();
    grid.appendChild(card);
  }
}

function renderCards(data) {
  grid.innerHTML = "";
  updateGridLayout();

  const visible = Array.isArray(data) ? data : [];
  if (visible.length === 0) {
    noResults.classList.remove("hidden");
    countLabel.innerText = "0";
    setResultsSummary(0, totalAssignments);
    if (loadMoreBtn) loadMoreBtn.classList.add("hidden");
    return;
  }

  noResults.classList.add("hidden");
  countLabel.innerText = String(visible.length);
  setResultsSummary(visible.length, totalAssignments);

  const compact = viewMode === "compact";

  visible.forEach((job) => {
    if (compact) {
      const rawMessageLink = typeof job.messageLink === "string" ? job.messageLink.trim() : "";
      const messageLink = rawMessageLink.startsWith("t.me/") ? `https://${rawMessageLink}` : rawMessageLink;

      const row = document.createElement(messageLink ? "a" : "div");
      row.className =
        "job-card bg-white dark:bg-gray-800 rounded-xl px-4 py-4 sm:px-5 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4 border border-gray-100 dark:border-gray-700";
      if (messageLink) {
        row.href = messageLink;
        row.target = "_blank";
        row.rel = "noopener noreferrer";
        row.addEventListener("click", () => {
          try {
            sendClickBeacon({
              eventType: "apply_click",
              assignmentExternalId: job.id,
              destinationType: "telegram_message",
              destinationUrl: messageLink,
              meta: { hasMessageLink: true, viewMode: "compact" },
            });
          } catch {}
        });
      } else {
        row.className += " opacity-70";
      }

      const top = document.createElement("div");
      top.className = "flex-1 min-w-0";

      const header = document.createElement("div");
      header.className = "flex items-start justify-between gap-3";

      const left = document.createElement("div");
      left.className = "min-w-0";

      const title = document.createElement("div");
      title.className = "text-lg font-bold leading-tight truncate";
      title.textContent = job.academicDisplayText || "Tuition Assignment";

      // compact view: do not show level/subject here (academicDisplayText includes it)

      left.prepend(title);

      const right = document.createElement("div");
      right.className = "flex flex-col items-end gap-2 shrink-0";

      const rate = document.createElement("div");
      rate.className = "font-bold text-base";
      const rateLabel = (() => {
        if (typeof job.rateMin === "number" && Number.isFinite(job.rateMin) && typeof job.rateMax === "number" && Number.isFinite(job.rateMax)) {
          if (Math.abs(job.rateMin - job.rateMax) < 1e-9) return `$${job.rateMin}/hr`;
          return `$${job.rateMin}-$${job.rateMax}/hr`;
        }
        if (typeof job.rateMin === "number" && Number.isFinite(job.rateMin)) return `$${job.rateMin}/hr`;
        const raw = String(job.rateRawText || "").trim();
        return raw || "N/A";
      })();
      rate.textContent = rateLabel;

      const chips = document.createElement("div");
      chips.className = "flex flex-wrap items-center justify-end gap-2";

      const tier = String(job?.freshnessTier || "green")
        .trim()
        .toLowerCase();
      const tierPill = document.createElement("span");
      tierPill.className = "badge";
      tierPill.textContent =
        tier === "green" ? "Likely open" : tier === "yellow" ? "Probably open" : tier === "orange" ? "Uncertain" : "Likely closed";
      tierPill.title = "Open-likelihood inferred from recent agency reposts/updates.";
      if (tier === "yellow") tierPill.className = "badge bg-yellow-100 text-yellow-800";
      else if (tier === "orange") tierPill.className = "badge bg-orange-100 text-orange-800";
      else if (tier === "red") tierPill.className = "badge bg-red-100 text-red-800";
      else tierPill.className = "badge bg-green-100 text-green-800";
      chips.appendChild(tierPill);

      const postedMs = Date.parse(String(job.postedAt || ""));
      const isNew = Number.isFinite(postedMs) && lastVisitCutoffMs > 0 && postedMs > lastVisitCutoffMs;
      if (isNew) {
        const newPill = document.createElement("span");
        newPill.className = "badge bg-blue-100 text-blue-800";
        newPill.textContent = "New";
        newPill.title = "Posted since your last visit.";
        chips.appendChild(newPill);
      }

      if (hasMatchForMe(job)) {
        const matchPill = document.createElement("span");
        matchPill.className = "badge bg-purple-100 text-purple-800";
        matchPill.textContent = "Matches you";
        const details = matchDetails(job);
        matchPill.title =
          details && details.length ? `Matches your saved profile preferences: ${details.join(", ")}` : "Matches your saved profile preferences.";
        chips.appendChild(matchPill);
      }

      right.appendChild(rate);
      right.appendChild(chips);

      header.appendChild(left);
      header.appendChild(right);
      top.appendChild(header);

      const meta = document.createElement("div");
      meta.className = "mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-gray-700";

      function metaItem(iconClass, text) {
        const wrap = document.createElement("span");
        wrap.className = "inline-flex items-center gap-2 min-w-0";

        const iconWrap = document.createElement("span");
        iconWrap.className = "w-7 h-7 rounded-full bg-gray-50 dark:bg-gray-700 flex items-center justify-center text-xs shrink-0";
        const icon = document.createElement("i");
        icon.className = iconClass;
        iconWrap.appendChild(icon);

        const label = document.createElement("span");
        label.className = "font-medium truncate";
        label.textContent = text;

        wrap.appendChild(iconWrap);
        wrap.appendChild(label);
        return wrap;
      }

      // show postal (explicit or estimated), distance, and time availability in compact mode
      const postal = job.postalCode || job.postalEstimated || job.location || "Unknown";
      meta.appendChild(metaItem("fa-solid fa-location-dot", postal));
      // compact: show tutor type summary if available
      if (Array.isArray(job.tutorTypes) && job.tutorTypes.length) {
        const t = job.tutorTypes[0];
        const label = t && (t.original || t.canonical) ? t.original || t.canonical : null;
        if (label) meta.appendChild(metaItem("fa-solid fa-user-tie", label));
      }
      if (typeof job.distanceKm === "number" && Number.isFinite(job.distanceKm)) {
        meta.appendChild(metaItem("fa-solid fa-ruler-combined", formatDistanceKm(job.distanceKm, job.postalCoordsEstimated)));
      }
      if (Array.isArray(job.timeNotes) && job.timeNotes.length) {
        meta.appendChild(metaItem("fa-solid fa-clock", job.timeNotes.join(" · ")));
      }

      top.appendChild(meta);
      row.appendChild(top);
      grid.appendChild(row);
      return;
    }

    const levelDisplay =
      Array.isArray(job.signalsSpecificLevels) && job.signalsSpecificLevels.length
        ? job.signalsSpecificLevels.join(" / ")
        : Array.isArray(job.signalsLevels) && job.signalsLevels.length
        ? job.signalsLevels.join(" / ")
        : "";

    const card = document.createElement("div");
    card.className = "job-card bg-white dark:bg-gray-800 rounded-xl p-6 relative flex flex-col justify-between h-full";

    const top = document.createElement("div");

    const header = document.createElement("div");
    header.className = "flex justify-between items-start mb-4";

    const badge = document.createElement("span");
    badge.className = "badge bg-black text-white";
    const displayId = String(job.assignmentCode || "").trim() || String(job.id || "").trim();
    badge.textContent = displayId || "ID";
    if (displayId && String(job.id || "").trim() && String(job.id || "").trim() !== displayId) {
      badge.title = `Internal id: ${String(job.id || "").trim()}`;
    }

    const tier = String(job?.freshnessTier || "green")
      .trim()
      .toLowerCase();
    const tierPill = document.createElement("span");
    tierPill.className = "badge";
    tierPill.textContent = tier === "green" ? "Likely open" : tier === "yellow" ? "Probably open" : tier === "orange" ? "Uncertain" : "Likely closed";
    tierPill.title = "Open-likelihood inferred from recent agency reposts/updates.";
    if (tier === "yellow") tierPill.className = "badge bg-yellow-100 text-yellow-800";
    else if (tier === "orange") tierPill.className = "badge bg-orange-100 text-orange-800";
    else if (tier === "red") tierPill.className = "badge bg-red-100 text-red-800";
    else tierPill.className = "badge bg-green-100 text-green-800";

    const chips = document.createElement("div");
    chips.className = "flex flex-wrap items-center justify-center gap-2 px-2";
    chips.appendChild(tierPill);

    const postedMs = Date.parse(String(job.postedAt || ""));
    const isNew = Number.isFinite(postedMs) && lastVisitCutoffMs > 0 && postedMs > lastVisitCutoffMs;
    if (isNew) {
      const newPill = document.createElement("span");
      newPill.className = "badge bg-blue-100 text-blue-800";
      newPill.textContent = "New";
      newPill.title = "Posted since your last visit.";
      chips.appendChild(newPill);
    }

    if (hasMatchForMe(job)) {
      const matchPill = document.createElement("span");
      matchPill.className = "badge bg-purple-100 text-purple-800";
      matchPill.textContent = "Matches you";
      matchPill.title = "Matches your saved profile preferences.";
      chips.appendChild(matchPill);
    }

    const rate = document.createElement("span");
    rate.className = "font-bold text-lg";
    const rateLabel = (() => {
      if (typeof job.rateMin === "number" && Number.isFinite(job.rateMin) && typeof job.rateMax === "number" && Number.isFinite(job.rateMax)) {
        if (Math.abs(job.rateMin - job.rateMax) < 1e-9) return `$${job.rateMin}/hr`;
        return `$${job.rateMin}-$${job.rateMax}/hr`;
      }
      if (typeof job.rateMin === "number" && Number.isFinite(job.rateMin)) return `$${job.rateMin}/hr`;
      const raw = String(job.rateRawText || "").trim();
      return raw || "N/A";
    })();
    rate.textContent = rateLabel;

    header.appendChild(badge);
    header.appendChild(chips);
    header.appendChild(rate);

    const title = document.createElement("h3");
    title.className = compact ? "text-2xl brand-font leading-none mb-1" : "text-3xl brand-font leading-none mb-1";
    title.textContent = job.academicDisplayText || "Tuition Assignment";

    const subtitle = document.createElement("p");
    subtitle.className = "text-gray-500 font-bold uppercase text-xs tracking-wider mb-6";
    subtitle.textContent = levelDisplay;

    const details = document.createElement("div");
    details.className = compact ? "space-y-2 mb-4" : "space-y-3 mb-8";

    function addDetail(iconClass, text) {
      const row = document.createElement("div");
      row.className = "flex items-center gap-3";

      const iconWrap = document.createElement("div");
      iconWrap.className = "w-8 h-8 rounded-full bg-gray-50 dark:bg-gray-700 flex items-center justify-center text-xs";

      const icon = document.createElement("i");
      icon.className = iconClass;
      iconWrap.appendChild(icon);

      const value = document.createElement("span");
      value.className = "font-medium text-sm";
      value.textContent = text;

      row.appendChild(iconWrap);
      row.appendChild(value);
      details.appendChild(row);
    }

    const subjectBits =
      Array.isArray(job.subjectsCanonicalLabels) && job.subjectsCanonicalLabels.length
        ? job.subjectsCanonicalLabels
        : Array.isArray(job.signalsSubjects) && job.signalsSubjects.length
        ? job.signalsSubjects
        : [];
    if (subjectBits.length) {
      addDetail("fa-solid fa-book", subjectBits.slice(0, 5).join(" / "));
    }

    addDetail("fa-solid fa-location-dot", job.location);
    if (!compact && job.region) addDetail("fa-solid fa-map", job.region);
    if (!compact && job.nearestMrt) {
      const line = String(job.nearestMrtLine || "").trim();
      const dist = typeof job.nearestMrtDistanceM === "number" && Number.isFinite(job.nearestMrtDistanceM) ? job.nearestMrtDistanceM : null;
      const suffix = `${line ? ` (${line})` : ""}${dist != null ? ` ~${dist}m` : ""}`;
      addDetail("fa-solid fa-train-subway", `${job.nearestMrt}${suffix}`);
    }
    if (!compact && typeof job.distanceKm === "number" && Number.isFinite(job.distanceKm))
      addDetail("fa-solid fa-ruler-combined", formatDistanceKm(job.distanceKm, job.postalCoordsEstimated));
    if (!compact && Array.isArray(job.scheduleNotes) && job.scheduleNotes.length)
      job.scheduleNotes.forEach((line) => addDetail("fa-solid fa-calendar-days", line));
    if (!compact && job.startDate) addDetail("fa-solid fa-calendar-check", job.startDate);
    if (!compact && Array.isArray(job.timeNotes) && job.timeNotes.length) job.timeNotes.forEach((line) => addDetail("fa-solid fa-clock", line));
    if (!compact && job.learningMode) addDetail("fa-solid fa-wifi", job.learningMode);
    if (!compact && job.agencyName) addDetail("fa-solid fa-building", job.agencyName);

    // show tutor types and rate breakdown in full view
    if (!compact && Array.isArray(job.tutorTypes) && job.tutorTypes.length) {
      const typesText = job.tutorTypes
        .map((t) => (t && (t.original || t.canonical) ? t.original || t.canonical : null))
        .filter(Boolean)
        .join(" · ");
      if (typesText) addDetail("fa-solid fa-user-tie", `Tutor types: ${typesText}`);
    }
    if (!compact && job.rateBreakdown && typeof job.rateBreakdown === "object") {
      const entries = Object.entries(job.rateBreakdown)
        .slice(0, 3)
        .map(([k, v]) => {
          const min = v && v.min ? `$${v.min}` : "";
          const max = v && v.max ? (v.max === v.min ? `$${v.max}` : `$${v.min}-$${v.max}`) : "";
          return `${k}${min || max ? ` ${min || max}${v && v.unit ? `/${v.unit}` : ""}` : ""}`;
        })
        .filter(Boolean);
      if (entries.length) addDetail("fa-solid fa-money-bill", `Rates: ${entries.join(" · ")}`);
    }

    if (job.postedAt) {
      const rel = formatRelativeTime(job.postedAt);
      const d = formatShortDate(job.postedAt);
      addDetail("fa-solid fa-calendar-day", rel ? `Posted ${rel}${d ? ` (${d})` : ""}` : d ? `Posted ${d}` : "Posted");
    }
    if (job.bumpedAt) {
      const rel = formatRelativeTime(job.bumpedAt);
      const d = formatShortDate(job.bumpedAt);
      addDetail("fa-solid fa-rotate", rel ? `Bumped/Updated ${rel}${d ? ` (${d})` : ""}` : d ? `Bumped/Updated ${d}` : "Bumped/Updated");
    }

    top.appendChild(header);
    top.appendChild(title);
    top.appendChild(subtitle);
    top.appendChild(details);

    const rawMessageLink = typeof job.messageLink === "string" ? job.messageLink.trim() : "";
    const messageLink = rawMessageLink.startsWith("t.me/") ? `https://${rawMessageLink}` : rawMessageLink;

    card.appendChild(top);

    const actions = document.createElement("div");
    actions.className = "mt-3";

    const primaryRow = document.createElement("div");
    primaryRow.className = "flex";

    const openBtn = document.createElement(messageLink ? "a" : "button");
    openBtn.className =
      "flex-1 py-3 border-2 border-black rounded-lg font-bold uppercase tracking-wide transition text-center " +
      (messageLink ? "hover:bg-black hover:text-white" : "opacity-40 cursor-not-allowed");
    openBtn.textContent = messageLink ? "Open original post" : "Link unavailable";
    if (messageLink) {
      openBtn.href = messageLink;
      openBtn.target = "_blank";
      openBtn.rel = "noopener noreferrer";
      openBtn.addEventListener("click", () => {
        try {
          sendClickBeacon({
            eventType: "apply_click",
            assignmentExternalId: job.id,
            destinationType: "telegram_message",
            destinationUrl: messageLink,
            meta: { hasMessageLink: true },
          });
        } catch {}
      });
    } else {
      openBtn.type = "button";
      openBtn.disabled = true;
    }

    primaryRow.appendChild(openBtn);
    actions.appendChild(primaryRow);

    card.appendChild(actions);
    grid.appendChild(card);
  });
}

function renderLoadError(message) {
  grid.innerHTML = "";
  noResults.classList.add("hidden");
  if (loadErrorMessage) loadErrorMessage.textContent = message || "We couldn’t load assignments right now. Please try again.";
  if (loadError) loadError.classList.remove("hidden");
  countLabel.innerText = "0";
  setResultsSummary(0, 0);
  if (loadMoreBtn) loadMoreBtn.classList.add("hidden");
  if (facetHint) facetHint.classList.add("hidden");
}

function hideLoadError() {
  if (loadError) loadError.classList.add("hidden");
}

// --- 4. FILTER LOGIC ---
function readStoredFilters() {
  try {
    const raw = localStorage.getItem(FILTERS_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function writeStoredFilters(filters) {
  try {
    localStorage.setItem(FILTERS_STORAGE_KEY, JSON.stringify(filters || {}));
  } catch {}
}

function snapshotFiltersForStorage() {
  const filters = collectFiltersFromUI();
  return {
    v: 1,
    level: filters.level || "",
    specificStudentLevel: filters.specificStudentLevel || "",
    subjectGeneral: filters.subjectGeneral || "",
    subjectCanonical: filters.subjectCanonical || "",
    location: filters.location || "",
    sort: filters.sort || "newest",
    minRate: filters.minRate || "",
    tutorType: filters.tutorType || "",
    savedAtMs: Date.now(),
  };
}

function restoreFiltersIntoUI(stored) {
  if (!stored || typeof stored !== "object") return false;
  const levelEl = document.getElementById("filter-level");
  const specificEl = document.getElementById("filter-specific-level");
  const genEl = document.getElementById("filter-subject-general");
  const canonEl = document.getElementById("filter-subject-canonical");
  const locEl = document.getElementById("filter-location");
  const sortEl = document.getElementById("filter-sort");
  const rateEl = document.getElementById("filter-rate");
  const tutorTypeEl = document.getElementById("filter-tutor-type");
  if (!levelEl || !specificEl || !locEl || !sortEl || !rateEl) return false;
  // Handle versioning of stored snapshot
  const v = Number.isFinite(Number(stored.v)) ? Number(stored.v) : 1;
  if (v !== 1) {
    // Unknown format - ignore for safety
    return false;
  }

  levelEl.value = String(stored.level || "");
  locEl.value = String(stored.location || "");
  sortEl.value = String(stored.sort || "newest");
  rateEl.value = String(stored.minRate || "");
  if (tutorTypeEl) tutorTypeEl.value = String(stored.tutorType || "");

  // Options may not exist yet; set pending targets so updateFilter* can re-select after rebuild.
  if (genEl) pendingFilters.subjectGeneral = String(stored.subjectGeneral || "").trim() || null;
  if (canonEl) pendingFilters.subjectCanonical = String(stored.subjectCanonical || "").trim() || null;
  pendingFilters.specificStudentLevel = String(stored.specificStudentLevel || "").trim() || null;
  pendingFilters.level = String(stored.level || "").trim() || null;

  // Trigger UI rebuilds which will pick up pendingFilters when facets arrive
  updateFilterSpecificLevels();
  updateFilterSubjects();
  return true;
}

function ensureCanonicalOption(code, label) {
  const select = $id("filter-subject-canonical");
  if (!select) return false;
  const c = String(code || "").trim();
  if (!c) return false;
  const exists = Array.from(select.options || []).some((o) => String(o.value || "").trim() === c);
  if (!exists) {
    const opt = document.createElement("option");
    opt.value = c;
    opt.text = String(label || c).trim() || c;
    select.appendChild(opt);
  }
  select.value = c;
  return true;
}

function mountSubjectSearch() {
  const input = document.getElementById("subject-search");
  const resultsEl = document.getElementById("subject-search-results");
  if (!input || !resultsEl) return;

  function hideResults() {
    resultsEl.classList.add("hidden");
    resultsEl.innerHTML = "";
  }

  function showResults(items, { query } = {}) {
    resultsEl.innerHTML = "";
    if (!items || !items.length) {
      hideResults();
      return;
    }
    items.forEach((item) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "w-full text-left px-4 py-3 hover:bg-gray-50 transition flex items-center justify-between gap-3";
      btn.setAttribute("role", "option");
      btn.tabIndex = 0;

      const left = document.createElement("span");
      left.className = "text-sm font-semibold text-gray-900";
      left.textContent = String(item.label || item.code || "").trim();

      const right = document.createElement("span");
      right.className = "text-xs font-mono text-gray-500";
      const t = String(item.type || "").trim();
      right.textContent = t === "general" ? `BROAD · ${String(item.code || "").trim()}` : `SPEC · ${String(item.code || "").trim()}`;

      btn.appendChild(left);
      btn.appendChild(right);
      btn.addEventListener("click", () => {
        const code = String(item.code || "").trim();
        if (!code) return;
        input.value = String(item.label || code).trim();
        const generalSelect = document.getElementById("filter-subject-general");
        const canonicalSelect = document.getElementById("filter-subject-canonical");
        if (String(item.type || "").trim() === "general") {
          if (generalSelect) generalSelect.value = code;
          if (canonicalSelect) canonicalSelect.value = "";
        } else {
          ensureCanonicalOption(code, item.label);
          if (generalSelect) generalSelect.value = "";
        }
        writeStoredFilters(snapshotFiltersForStorage());
        hideResults();
        input.blur();
        void loadAssignments({ reset: true });
      });
      resultsEl.appendChild(btn);
    });
    resultsEl.classList.remove("hidden");

    // Accessibility: expose as listbox + basic keyboard navigation
    resultsEl.setAttribute("role", "listbox");
    resultsEl.querySelectorAll("button[role=option]").forEach((b) => {
      b.addEventListener("keydown", (e) => {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          const nxt = b.nextElementSibling;
          if (nxt && nxt.focus) nxt.focus();
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          const prev = b.previousElementSibling;
          if (prev && prev.focus) prev.focus();
        }
      });
    });

    if (query) {
      resultsEl.setAttribute("data-query", String(query));
    }
  }

  let lastQuery = "";
  let searchTimer = null;

  function doSearch() {
    const q = String(input.value || "").trim();
    if (!q) {
      lastQuery = "";
      hideResults();
      return;
    }
    if (q === lastQuery) return;
    lastQuery = q;

    const level = (document.getElementById("filter-level")?.value || "").trim() || null;
    const items = searchSubjects(q, { level, limit: 10 });
    showResults(items, { query: q });
  }

  input.addEventListener("input", () => {
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(doSearch, 80);
  });

  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      hideResults();
      return;
    }
    if (e.key === "Enter") {
      const first = resultsEl.querySelector("button");
      if (first) {
        e.preventDefault();
        first.click();
      }
    }
  });

  input.addEventListener("blur", () => {
    setTimeout(() => hideResults(), 150);
  });
}

function updateFilterSpecificLevels() {
  const specificSelect = $id("filter-specific-level");
  const levelEl = $id("filter-level");
  if (!specificSelect || !levelEl) return;
  const currentSelected = specificSelect.value || "";
  const level = String(levelEl.value || "").trim();
  const options = specificLevelsData[level] || [];

  specificSelect.innerHTML = '<option value="">All Specific Levels</option>';

  if (!level) {
    specificSelect.disabled = true;
    return;
  }

  // Prefer server facets when available (accurate), fallback to static list.
  const facetOptions = Array.isArray(lastFacets?.specific_levels) ? lastFacets.specific_levels : null;
  const items = facetOptions && facetOptions.length ? facetOptions : options.map((value) => ({ value, count: null }));

  if (!items.length) {
    specificSelect.disabled = true;
    return;
  }

  items.forEach((item) => {
    const name = String(item?.value || "").trim();
    if (!name) return;
    const option = document.createElement("option");
    option.value = name;
    option.text = item?.count ? `${name} (${item.count})` : name;
    specificSelect.appendChild(option);
  });

  // Preserve the previously selected specific level even if not in current facets
  if (currentSelected) {
    if (!Array.from(specificSelect.options || []).some((o) => String(o.value || "").trim() === String(currentSelected).trim())) {
      const val = String(currentSelected).trim();
      if (val) {
        const opt = document.createElement("option");
        opt.value = val;
        opt.text = val;
        specificSelect.appendChild(opt);
      }
    }
    specificSelect.value = currentSelected;
  }
  specificSelect.disabled = false;

  // Re-apply any pending selection restored earlier if facets arrived late
  if (pendingFilters.specificStudentLevel) {
    const v = String(pendingFilters.specificStudentLevel || "").trim();
    if (v) {
      let appended = false;
      if (!Array.from(specificSelect.options || []).some((o) => String(o.value || "").trim() === v)) {
        const opt = document.createElement("option");
        opt.value = v;
        opt.text = v;
        specificSelect.appendChild(opt);
        appended = true;
      }
      specificSelect.value = v;
      if (appended) {
        try {
          trackEvent({ eventType: "facets_mismatch", facet: "specific_levels", value: v, note: "restored_from_storage_not_in_facets" });
        } catch {}
      }
    }
    pendingFilters.specificStudentLevel = null;
  }
}

function updateFilterSubjects() {
  const level = String($id("filter-level")?.value || "").trim();
  const generalSelect = $id("filter-subject-general");
  const canonicalSelect = $id("filter-subject-canonical");
  const prevGeneral = generalSelect?.value || "";
  const prevCanonical = canonicalSelect?.value || "";

  if (generalSelect) generalSelect.innerHTML = '<option value="">All Subjects (Broad)</option>';
  if (canonicalSelect) canonicalSelect.innerHTML = '<option value="">Any Specific Syllabus</option>';

  // Prefer server facets when available (accurate), fallback to static list.
  const facetGeneral = Array.isArray(lastFacets?.subjects_general) ? lastFacets.subjects_general : null;
  const facetCanonical = Array.isArray(lastFacets?.subjects_canonical) ? lastFacets.subjects_canonical : null;

  if (generalSelect) {
    const items = facetGeneral && facetGeneral.length ? facetGeneral : generalCategoryOptions().map((c) => ({ value: c.code, count: null }));
    items.forEach((item) => {
      const code = String(item?.value || "").trim();
      if (!code) return;
      const label = labelForGeneralCategoryCode(code) || code;
      const option = document.createElement("option");
      option.value = code;
      option.text = item?.count ? `${label} (${item.count})` : label;
      generalSelect.appendChild(option);
    });
  }

  if (canonicalSelect) {
    const lvl = String(level || "").trim();
    const fallback = lvl ? canonicalSubjectsForLevel(lvl) : [];
    const items = facetCanonical && facetCanonical.length ? facetCanonical : fallback.map((s) => ({ value: s.code, count: null }));
    items.forEach((item) => {
      const code = String(item?.value || "").trim();
      if (!code) return;
      const label = labelForCanonicalCode(code) || code;
      const option = document.createElement("option");
      option.value = code;
      option.text = item?.count ? `${label} (${item.count})` : label;
      canonicalSelect.appendChild(option);
    });
  }

  if (generalSelect && prevGeneral) {
    if (!Array.from(generalSelect.options || []).some((o) => String(o.value || "").trim() === String(prevGeneral).trim())) {
      const code = String(prevGeneral).trim();
      if (code) {
        const opt = document.createElement("option");
        opt.value = code;
        opt.text = labelForGeneralCategoryCode(code) || code;
        generalSelect.appendChild(opt);
      }
    }
    generalSelect.value = prevGeneral;
  }

  if (canonicalSelect && prevCanonical) {
    if (!Array.from(canonicalSelect.options || []).some((o) => String(o.value || "").trim() === String(prevCanonical).trim())) {
      const code = String(prevCanonical).trim();
      if (code) {
        const opt = document.createElement("option");
        opt.value = code;
        opt.text = labelForCanonicalCode(code) || code;
        canonicalSelect.appendChild(opt);
      }
    }
    canonicalSelect.value = prevCanonical;
  }

  // Reapply any pending selections that were stored while facets were loading
  if (pendingFilters.subjectGeneral && generalSelect) {
    const v = String(pendingFilters.subjectGeneral || "").trim();
    if (v) {
      let appended = false;
      if (!Array.from(generalSelect.options || []).some((o) => String(o.value || "").trim() === v)) {
        const opt = document.createElement("option");
        opt.value = v;
        opt.text = labelForGeneralCategoryCode(v) || v;
        generalSelect.appendChild(opt);
        appended = true;
      }
      generalSelect.value = v;
      if (appended) {
        try {
          trackEvent({ eventType: "facets_mismatch", facet: "subjects_general", value: v, note: "restored_from_storage_not_in_facets" });
        } catch {}
      }
    }
    pendingFilters.subjectGeneral = null;
  }

  if (pendingFilters.subjectCanonical && canonicalSelect) {
    const v = String(pendingFilters.subjectCanonical || "").trim();
    if (v) {
      // If the option is not present, we'll track that we had to append it.
      const exists = Array.from(canonicalSelect.options || []).some((o) => String(o.value || "").trim() === v);
      ensureCanonicalOption(v, labelForCanonicalCode(v));
      canonicalSelect.value = v;
      if (!exists) {
        try {
          trackEvent({ eventType: "facets_mismatch", facet: "subjects_canonical", value: v, note: "restored_from_storage_not_in_facets" });
        } catch {}
      }
    }
    pendingFilters.subjectCanonical = null;
  }
  // Tutor types facet population
  try {
    updateFilterTutorTypes();
  } catch (e) {}
}

function updateFilterTutorTypes() {
  const select = $id("filter-tutor-type");
  if (!select) return;
  const prev = select.value || "";
  select.innerHTML = '<option value="">All Tutor Types</option>';
  const facetOptions = Array.isArray(lastFacets?.tutor_types) ? lastFacets.tutor_types : null;
  if (facetOptions && facetOptions.length) {
    facetOptions.forEach((it) => {
      const code = String(it?.value || "").trim();
      if (!code) return;
      const opt = document.createElement("option");
      opt.value = code;
      opt.text = it.count ? `${code} (${it.count})` : code;
      select.appendChild(opt);
    });
  } else {
    // Keep existing static options (do nothing)
  }
  if (prev) {
    if (!Array.from(select.options || []).some((o) => String(o.value || "").trim() === String(prev).trim())) {
      const opt = document.createElement("option");
      opt.value = prev;
      opt.text = prev;
      select.appendChild(opt);
    }
    select.value = prev;
  }
}

function mountTutorTypeSearch() {
  const input = document.getElementById("tutor-type-search");
  const resultsEl = document.getElementById("tutor-type-search-results");
  if (!input || !resultsEl) return;

  function hide() {
    resultsEl.classList.add("hidden");
    resultsEl.innerHTML = "";
  }

  function show(items) {
    resultsEl.innerHTML = "";
    if (!items || !items.length) {
      hide();
      return;
    }
    items.forEach((item) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "w-full text-left px-4 py-2 hover:bg-gray-50 transition flex items-center justify-between gap-3";
      btn.textContent = `${item.label || item.value}`;
      btn.addEventListener("click", () => {
        const select = document.getElementById("filter-tutor-type");
        if (select) {
          ensureOptionAndSelect(select, item.value, item.label || item.value);
        }
        hide();
        input.value = "";
      });
      resultsEl.appendChild(btn);
    });
    resultsEl.classList.remove("hidden");
  }

  function ensureOptionAndSelect(select, value, label) {
    const exists = Array.from(select.options || []).some((o) => String(o.value || "") === String(value || ""));
    if (!exists) {
      const opt = document.createElement("option");
      opt.value = value;
      opt.text = label || value;
      select.appendChild(opt);
    }
    select.value = value;
  }

  let timer = null;
  input.addEventListener("input", () => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      const q = String(input.value || "")
        .trim()
        .toLowerCase();
      if (!q) return hide();
      const facetOptions = Array.isArray(lastFacets?.tutor_types) ? lastFacets.tutor_types : null;
      const candidates = (
        facetOptions && facetOptions.length
          ? facetOptions
          : Array.from(document.getElementById("filter-tutor-type").options || []).map((o) => ({ value: o.value }))
      ).map((o) => ({ value: String(o.value || "").trim(), label: String(o.value || "").trim() }));
      const matched = candidates
        .filter(
          (c) =>
            String(c.value || "")
              .toLowerCase()
              .includes(q) ||
            String(c.label || "")
              .toLowerCase()
              .includes(q)
        )
        .slice(0, 10);
      show(matched);
    }, 120);
  });
  input.addEventListener("blur", () => setTimeout(hide, 150));
}

function collectFiltersFromUI() {
  return {
    level: (document.getElementById("filter-level")?.value || "").trim() || null,
    specificStudentLevel: (document.getElementById("filter-specific-level")?.value || "").trim() || null,
    subjectGeneral: (document.getElementById("filter-subject-general")?.value || "").trim() || null,
    subjectCanonical: (document.getElementById("filter-subject-canonical")?.value || "").trim() || null,
    location: (document.getElementById("filter-location")?.value || "").trim() || null,
    sort: (document.getElementById("filter-sort")?.value || "").trim() || "newest",
    minRate: (document.getElementById("filter-rate")?.value || "").trim() || null,
    tutorType: (document.getElementById("filter-tutor-type")?.value || "").trim() || null,
  };
}

// Centralized helper to check if a job matches a filters object.
// `matchesFilters` is implemented in `src/lib/filterUtils.js` and imported above.

async function applyFilters() {
  writeStoredFilters(snapshotFiltersForStorage());
  if (!isBackendEnabled()) {
    // Legacy fallback: filter only the currently loaded in-memory list.
    const level = document.getElementById("filter-level").value;
    const specificLevel = document.getElementById("filter-specific-level").value;
    const subjectGeneral = document.getElementById("filter-subject-general").value;
    const subjectCanonical = document.getElementById("filter-subject-canonical").value;
    const location = document.getElementById("filter-location").value;
    const minRate = document.getElementById("filter-rate").value;
    const filters = collectFiltersFromUI();
    const filtered = allAssignments.filter((job) => matchesFilters(job, filters));
    renderCards(filtered);
    return;
  }

  await loadAssignments({ reset: true });
}

function clearFilters() {
  document.getElementById("filter-level").value = "";
  document.getElementById("filter-specific-level").value = "";
  document.getElementById("filter-specific-level").innerHTML = '<option value="">All Specific Levels</option>';
  document.getElementById("filter-specific-level").disabled = true;
  const g = document.getElementById("filter-subject-general");
  if (g) g.innerHTML = '<option value="">All Subjects (Broad)</option>';
  const c = document.getElementById("filter-subject-canonical");
  if (c) c.innerHTML = '<option value="">Any Specific Syllabus</option>';
  document.getElementById("filter-location").value = "";
  const sortEl = document.getElementById("filter-sort");
  if (sortEl) sortEl.value = "newest";
  document.getElementById("filter-rate").value = "";
  writeStoredFilters(snapshotFiltersForStorage());
  if (!isBackendEnabled()) {
    renderCards(allAssignments);
    return;
  }
  void loadAssignments({ reset: true });
}

window.updateFilterSpecificLevels = updateFilterSpecificLevels;
window.updateFilterSubjects = updateFilterSubjects;
window.applyFilters = applyFilters;
window.clearFilters = clearFilters;

function setLoadMoreVisible(canLoadMore) {
  if (!loadMoreBtn) return;
  loadMoreBtn.classList.toggle("hidden", !canLoadMore);
}

function setFacetHintVisible(show) {
  if (!facetHint) return;
  facetHint.classList.toggle("hidden", !show);
}

function applySortAvailability() {
  const select = document.getElementById("filter-sort");
  if (!select) return;
  const option = Array.from(select.options).find((o) => o.value === "distance");
  const canSortByDistance = hasPostalCoords === true;
  if (option) option.disabled = !canSortByDistance;
  select.title = canSortByDistance ? "" : "Sign in and set your postal code in Profile to enable Nearest sorting.";
  if (!canSortByDistance && select.value === "distance") {
    select.value = "newest";
  }

  const cta = document.getElementById("postal-cta");
  if (cta) {
    cta.classList.toggle("hidden", canSortByDistance);
    cta.setAttribute("href", currentUid ? "profile.html" : "index.html?next=profile.html");
  }
}

function formatAssignmentsLoadError(err) {
  const msg = String(err?.message || err || "").trim();
  if (!msg) return "Assignments are temporarily unavailable. Please try again.";

  if (msg.includes("VITE_BACKEND_URL missing")) {
    return "Assignments unavailable: website backend is not configured (VITE_BACKEND_URL missing at build time).";
  }

  // Common when the reverse proxy points at the wrong service, or backend container wasn't rebuilt.
  if (msg.includes("Backend GET /assignments") && msg.includes("(404)") && msg.includes("Not Found")) {
    return "Assignments unavailable: backend route not found (404). If you updated the backend, rebuild/redeploy it and verify your reverse proxy points to the TutorDex backend.";
  }

  // Backend exists but can't serve because DB functions weren't applied.
  if (msg.includes("list_assignments_failed") || msg.includes("facets_failed")) {
    return "Assignments unavailable: backend is up, but the Supabase RPC functions for pagination/facets are missing or failing. Apply `TutorDexAggregator/supabase sqls/2025-12-25_assignments_facets_pagination.sql`, `TutorDexAggregator/supabase sqls/2025-12-29_assignments_distance_sort.sql`, and (for v2 subjects) `TutorDexAggregator/supabase sqls/2026-01-03_subjects_taxonomy_v2.sql`.";
  }

  if (msg.includes("supabase_disabled")) {
    return "Assignments unavailable: backend Supabase integration is disabled/misconfigured (check SUPABASE_ENABLED, SUPABASE_URL_HOST/SUPABASE_URL_DOCKER/SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY).";
  }

  if (msg.includes("postal_required_for_distance")) {
    return "Nearest sort requires your postal code. Set it in Profile, then try again.";
  }

  return `Assignments unavailable (${msg}).`;
}

async function loadAssignments({ reset = false, append = false } = {}) {
  const loadToken = ++activeLoadToken;
  if (isDebugEnabled()) {
    debugLog("Assignments page boot", {
      buildTime: BUILD_TIME,
      pathname: window.location.pathname,
    });
  }

  if (!isBackendEnabled()) {
    setStatus("Assignments unavailable: website backend is not configured (VITE_BACKEND_URL missing at build time).", "error", {
      showRetry: true,
    });
    allAssignments = [];
    totalAssignments = 0;
    nextCursorLastSeen = null;
    nextCursorId = null;
    renderLoadError("Assignments are temporarily unavailable. Please try again.");
    return;
  }

  if (reset) {
    allAssignments = [];
    totalAssignments = 0;
    nextCursorLastSeen = null;
    nextCursorId = null;
    nextCursorDistanceKm = null;
  }

  const isInitial = !append && allAssignments.length === 0;
  if (isInitial) {
    setStatus("Loading assignments from backend...", "info");
    renderSkeleton(6);
  }
  try {
    const filters = collectFiltersFromUI();
    const minRate = filters.minRate ? Number.parseInt(filters.minRate, 10) : null;
    const sort = (filters.sort || "newest").trim().toLowerCase();

    if (!append) {
      try {
        // Fetch facets without self-filtering subject/specific level, so dropdowns remain useful.
        const facetsResp = await getOpenAssignmentFacets({
          level: filters.level,
          location: filters.location,
          minRate: Number.isFinite(minRate) ? minRate : null,
          tutorType: filters.tutorType || null,
        });
        if (loadToken === activeLoadToken) {
          lastFacets = facetsResp?.facets || null;
          // Rebuild dropdown options based on new facets.
          updateFilterSpecificLevels();
          updateFilterSubjects();
          updateFilterTutorTypes();
          setFacetHintVisible(Boolean(lastFacets));
        }
      } catch (e) {
        if (loadToken === activeLoadToken) {
          lastFacets = null;
          setFacetHintVisible(false);
        }
      }
    }

    const page = await listOpenAssignmentsPaged({
      limit: 50,
      sort,
      cursorLastSeen: append ? nextCursorLastSeen : null,
      cursorId: append ? nextCursorId : null,
      cursorDistanceKm: append && sort === "distance" ? nextCursorDistanceKm : null,
      level: filters.level,
      specificStudentLevel: filters.specificStudentLevel,
      subjectGeneral: filters.subjectGeneral,
      subjectCanonical: filters.subjectCanonical,
      location: filters.location,
      minRate: Number.isFinite(minRate) ? minRate : null,
      tutorType: filters.tutorType || null,
    });

    if (loadToken !== activeLoadToken) return;

    const rows = Array.isArray(page?.items) ? page.items : [];
    const mapped = rows.map(mapAssignmentRow);
    allAssignments = append ? [...allAssignments, ...mapped] : mapped;
    totalAssignments = Number.isFinite(page?.total) ? page.total : allAssignments.length;
    nextCursorLastSeen = page?.next_cursor_last_seen || null;
    nextCursorId = page?.next_cursor_id ?? null;
    nextCursorDistanceKm = page?.next_cursor_distance_km ?? null;
    const canLoadMore =
      sort === "distance"
        ? Boolean(
            nextCursorLastSeen &&
              nextCursorId !== null &&
              nextCursorId !== undefined &&
              nextCursorDistanceKm !== null &&
              nextCursorDistanceKm !== undefined
          )
        : Boolean(nextCursorLastSeen && nextCursorId !== null && nextCursorId !== undefined);
    setLoadMoreVisible(canLoadMore);

    hideLoadError();
    renderCards(allAssignments);
    try {
      await trackEvent({ eventType: "assignments_view" });
    } catch {}

    if (!didWriteLastVisitThisSession) {
      didWriteLastVisitThisSession = true;
      writeLastVisitMs(Date.now());
    }
    setStatus(`Loaded ${allAssignments.length} of ${totalAssignments} assignments.`, "success");
  } catch (err) {
    const msg = String(err?.message || err || "");
    if (msg.includes("postal_required_for_distance")) {
      const select = document.getElementById("filter-sort");
      if (select) select.value = "newest";
      setStatus("Nearest sort needs your postal code. Switched back to Newest.", "warning");
      applySortAvailability();
      void loadAssignments({ reset: true });
      return;
    }

    console.error("Failed to load assignments from backend.", err);
    const friendly = formatAssignmentsLoadError(err);
    setStatus(friendly, "error", { showRetry: true });
    allAssignments = [];
    totalAssignments = 0;
    nextCursorLastSeen = null;
    nextCursorId = null;
    nextCursorDistanceKm = null;
    renderLoadError(friendly);
  }
}

async function loadProfileContext() {
  if (!isBackendEnabled()) return;

  try {
    await waitForAuth();
    const uid = await getCurrentUid();
    if (!uid) return;
    currentUid = uid;

    const profile = await getTutor(uid);
    if (!profile) return;
    myTutorProfile = profile;

    const lat = profile?.postal_lat;
    const lon = profile?.postal_lon;
    hasPostalCoords = typeof lat === "number" && Number.isFinite(lat) && typeof lon === "number" && Number.isFinite(lon);
    applySortAvailability();
  } catch (err) {
    console.error("Failed to load profile context.", err);
  }
}

function mountDebugPanel() {
  if (!isDebugEnabled()) return;

  const host = document.querySelector(".max-w-6xl") || document.body;
  if (!host || document.getElementById("debug-panel")) return;

  const wrap = document.createElement("div");
  wrap.id = "debug-panel";
  wrap.className = "mt-6";

  wrap.innerHTML = `
	    <details class="border border-gray-200 rounded-xl p-4 bg-white">
	      <summary class="cursor-pointer font-bold uppercase text-xs tracking-wide text-gray-600">Debug</summary>
	      <div class="mt-3 text-sm text-gray-700 space-y-2">
	        <div><span class="font-semibold">Build time:</span> <span class="font-mono">${BUILD_TIME || "(unknown)"}</span></div>
	        <div><span class="font-semibold">Backend enabled:</span> <span class="font-mono">${String(isBackendEnabled())}</span></div>
	      </div>
	    </details>
	  `.trim();

  host.appendChild(wrap);
}

window.addEventListener("load", () => {
  viewMode = readViewMode();
  lastVisitCutoffMs = readLastVisitMs();

  const fullBtn = document.getElementById("view-toggle-full");
  const compactBtn = document.getElementById("view-toggle-compact");
  if (fullBtn) fullBtn.addEventListener("click", () => setViewMode("full"));
  if (compactBtn) compactBtn.addEventListener("click", () => setViewMode("compact"));

  updateViewToggleUI();
  updateGridLayout();
  mountSubjectSearch();
  mountTutorTypeSearch();

  const generalSelect = document.getElementById("filter-subject-general");
  const canonicalSelect = document.getElementById("filter-subject-canonical");
  if (generalSelect) {
    generalSelect.addEventListener("change", () => {
      if (canonicalSelect) canonicalSelect.value = "";
    });
  }
  if (canonicalSelect) {
    canonicalSelect.addEventListener("change", () => {
      if (generalSelect) generalSelect.value = "";
    });
  }

  if (retryLoadBtn) retryLoadBtn.addEventListener("click", () => loadAssignments({ reset: true }));
  if (loadMoreBtn) loadMoreBtn.addEventListener("click", () => loadAssignments({ append: true }));
  const sortEl = document.getElementById("filter-sort");
  if (sortEl) {
    sortEl.addEventListener("change", () => {
      writeStoredFilters(snapshotFiltersForStorage());
      loadAssignments({ reset: true });
    });
  }

  try {
    const stored = readStoredFilters();
    didRestoreFiltersFromStorage = restoreFiltersIntoUI(stored);
  } catch {
    didRestoreFiltersFromStorage = false;
  }
  mountDebugPanel();
  loadAssignments({ reset: true }).then(() => {
    // Load profile for "Matches you" + Nearest availability, but do not auto-apply preferences as filters.
    void loadProfileContext();
  });

  // Advanced subjects toggle: toggle the specific syllabus details panel
  try {
    const advBtn = document.getElementById("toggle-advanced-subjects");
    const details = document.getElementById("specific-syllabus-details");
    const canonicalSelect = $id("filter-subject-canonical");
    if (advBtn && details) {
      advBtn.addEventListener("click", () => {
        const open = details.hasAttribute("open");
        if (open) details.removeAttribute("open");
        else {
          details.setAttribute("open", "");
          // focus the select for keyboard users
          setTimeout(() => {
            try {
              if (canonicalSelect && canonicalSelect.focus) canonicalSelect.focus();
            } catch {}
          }, 50);
        }
      });
    }
  } catch (e) {}
});
