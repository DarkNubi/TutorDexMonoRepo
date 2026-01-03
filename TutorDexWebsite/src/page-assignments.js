import { getCurrentUid, waitForAuth } from "../auth.js";
import {
  getOpenAssignmentFacets,
  getTutor,
  isBackendEnabled,
  listOpenAssignmentsPaged,
  sendClickBeacon,
  trackEvent,
} from "./backend.js";
import { debugLog, isDebugEnabled } from "./debug.js";
import { SPECIFIC_LEVELS } from "./academicEnums.js";
import {
  canonicalSubjectsForLevel,
  generalCategoryOptions,
  labelForCanonicalCode,
  labelForGeneralCategoryCode,
  labelsForCanonicalCodes,
  labelsForGeneralCategoryCodes,
} from "./taxonomy/subjectsTaxonomyV2.js";

const BUILD_TIME = typeof __BUILD_TIME__ !== "undefined" ? __BUILD_TIME__ : "";

const specificLevelsData = SPECIFIC_LEVELS || {};

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
  if (s.includes("\n")) return s.split("\n").map((x) => x.trim()).filter(Boolean);
  return [s];
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
    rateMin: typeof rateMin === "number" && Number.isFinite(rateMin) ? rateMin : null,
    rateMax: typeof rateMax === "number" && Number.isFinite(rateMax) ? rateMax : null,
    rateRawText: toText(row?.rate_raw_text),
    freshnessTier: toText(row?.freshness_tier) || "green",
    timeNotes,
    scheduleNotes,
    startDate: toText(row?.start_date),
    agencyName: toText(row?.agency_name),
    learningMode,
    updatedAt: toText(row?.last_seen || row?.created_at),
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

function formatDistanceKm(km) {
  const n = typeof km === "number" ? km : Number.parseFloat(String(km || ""));
  if (!Number.isFinite(n)) return "";
  if (n < 10) return `~${n.toFixed(1)} km`;
  return `~${Math.round(n)} km`;
}

function renderSkeleton(count = 6) {
  grid.innerHTML = "";
  noResults.classList.add("hidden");
  countLabel.innerText = "...";
  setResultsSummary(0, 0);
  if (loadMoreBtn) loadMoreBtn.classList.add("hidden");
  if (facetHint) facetHint.classList.add("hidden");

  for (let i = 0; i < count; i++) {
    const card = document.createElement("div");
    card.className = "job-card bg-white rounded-xl p-6 relative flex flex-col justify-between h-full animate-pulse";
    card.innerHTML = `
      <div>
        <div class="flex justify-between items-start mb-4">
          <div class="h-6 w-24 bg-gray-100 rounded-full"></div>
          <div class="h-6 w-16 bg-gray-100 rounded-full"></div>
          <div class="h-6 w-14 bg-gray-100 rounded"></div>
        </div>
        <div class="h-8 w-2/3 bg-gray-100 rounded mb-3"></div>
        <div class="h-4 w-1/2 bg-gray-100 rounded mb-6"></div>
        <div class="space-y-3 mb-8">
          <div class="h-4 w-5/6 bg-gray-100 rounded"></div>
          <div class="h-4 w-4/6 bg-gray-100 rounded"></div>
          <div class="h-4 w-3/6 bg-gray-100 rounded"></div>
        </div>
      </div>
      <div class="h-12 w-full bg-gray-100 rounded-lg"></div>
    `.trim();
    grid.appendChild(card);
  }
}

function renderCards(data) {
  grid.innerHTML = "";

  if (data.length === 0) {
    noResults.classList.remove("hidden");
    countLabel.innerText = "0";
    setResultsSummary(0, totalAssignments);
    if (loadMoreBtn) loadMoreBtn.classList.add("hidden");
    return;
  }

  noResults.classList.add("hidden");
  countLabel.innerText = String(data.length);
  setResultsSummary(data.length, totalAssignments);

  data.forEach((job) => {
    const levelDisplay = Array.isArray(job.signalsSpecificLevels) && job.signalsSpecificLevels.length
      ? job.signalsSpecificLevels.join(" / ")
      : Array.isArray(job.signalsLevels) && job.signalsLevels.length
        ? job.signalsLevels.join(" / ")
        : "";

    const card = document.createElement("div");
    card.className = "job-card bg-white rounded-xl p-6 relative flex flex-col justify-between h-full";

    const top = document.createElement("div");

    const header = document.createElement("div");
    header.className = "flex justify-between items-start mb-4";

    const badge = document.createElement("span");
    badge.className = "badge bg-black text-white";
    badge.textContent = job.id;

    const tier = String(job?.freshnessTier || "green")
      .trim()
      .toLowerCase();
    const tierPill = document.createElement("span");
    tierPill.className = "badge";
    tierPill.textContent = tier === "yellow" ? "Yellow" : tier === "orange" ? "Orange" : tier === "red" ? "Red" : "Green";
    tierPill.title = "Freshness tier based on recent reposts/updates.";
    if (tier === "yellow") tierPill.className = "badge bg-yellow-100 text-yellow-800";
    else if (tier === "orange") tierPill.className = "badge bg-orange-100 text-orange-800";
    else if (tier === "red") tierPill.className = "badge bg-red-100 text-red-800";
    else tierPill.className = "badge bg-green-100 text-green-800";

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
    header.appendChild(tierPill);
    header.appendChild(rate);

    const title = document.createElement("h3");
    title.className = "text-3xl brand-font leading-none mb-1";
    title.textContent = job.academicDisplayText || "Tuition Assignment";

    const subtitle = document.createElement("p");
    subtitle.className = "text-gray-500 font-bold uppercase text-xs tracking-wider mb-6";
    subtitle.textContent = levelDisplay;

    const details = document.createElement("div");
    details.className = "space-y-3 mb-8";

    function addDetail(iconClass, text) {
      const row = document.createElement("div");
      row.className = "flex items-center gap-3";

      const iconWrap = document.createElement("div");
      iconWrap.className = "w-8 h-8 rounded-full bg-gray-50 flex items-center justify-center text-xs";

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
    if (job.region) {
      addDetail("fa-solid fa-map", job.region);
    }
    if (job.nearestMrt) {
      const line = String(job.nearestMrtLine || "").trim();
      const dist = typeof job.nearestMrtDistanceM === "number" && Number.isFinite(job.nearestMrtDistanceM) ? job.nearestMrtDistanceM : null;
      const suffix = `${line ? ` (${line})` : ""}${dist != null ? ` ~${dist}m` : ""}`;
      addDetail("fa-solid fa-train-subway", `${job.nearestMrt}${suffix}`);
    }
    if (typeof job.distanceKm === "number" && Number.isFinite(job.distanceKm)) {
      addDetail("fa-solid fa-ruler-combined", formatDistanceKm(job.distanceKm));
    }
    if (Array.isArray(job.scheduleNotes) && job.scheduleNotes.length) {
      job.scheduleNotes.forEach((line) => addDetail("fa-solid fa-calendar-days", line));
    }
    if (job.startDate) addDetail("fa-solid fa-calendar-check", job.startDate);
    if (Array.isArray(job.timeNotes) && job.timeNotes.length) {
      job.timeNotes.forEach((line) => addDetail("fa-solid fa-clock", line));
    }
    if (job.learningMode) addDetail("fa-solid fa-wifi", job.learningMode);
    if (job.agencyName) addDetail("fa-solid fa-building", job.agencyName);
    if (job.updatedAt) {
      const rel = formatRelativeTime(job.updatedAt);
      addDetail("fa-solid fa-rotate", rel ? `Updated ${rel}` : "Updated recently");
    }

    top.appendChild(header);
    top.appendChild(title);
    top.appendChild(subtitle);
    top.appendChild(details);

    const rawMessageLink = typeof job.messageLink === "string" ? job.messageLink.trim() : "";
    const messageLink = rawMessageLink.startsWith("t.me/") ? `https://${rawMessageLink}` : rawMessageLink;

    const applyBtn = document.createElement(messageLink ? "a" : "button");
    applyBtn.className = "w-full py-4 border-2 border-black rounded-lg font-bold uppercase tracking-wide transition text-center";
    applyBtn.textContent = messageLink ? "Apply Now" : "Link Unavailable";
    if (messageLink) {
      applyBtn.href = messageLink;
      applyBtn.target = "_blank";
      applyBtn.rel = "noopener noreferrer";
      applyBtn.className += " hover:bg-black hover:text-white";
      applyBtn.addEventListener("click", () => {
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
      applyBtn.type = "button";
      applyBtn.disabled = true;
      applyBtn.className += " opacity-40 cursor-not-allowed";
      applyBtn.addEventListener("click", () => {
        try {
          sendClickBeacon({
            eventType: "apply_click",
            assignmentExternalId: job.id,
            destinationType: "telegram_message",
            destinationUrl: "",
            meta: { hasMessageLink: false },
          });
        } catch {}
      });
    }

    card.appendChild(top);
    card.appendChild(applyBtn);
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
function updateFilterSpecificLevels() {
  const level = document.getElementById("filter-level").value;
  const specificSelect = document.getElementById("filter-specific-level");
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

  specificSelect.disabled = false;
}

function updateFilterSubjects() {
  const level = document.getElementById("filter-level").value;
  const generalSelect = document.getElementById("filter-subject-general");
  const canonicalSelect = document.getElementById("filter-subject-canonical");

  if (generalSelect) generalSelect.innerHTML = '<option value="">All General Subjects</option>';
  if (canonicalSelect) canonicalSelect.innerHTML = '<option value="">All Advanced Subjects</option>';

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
  };
}

async function applyFilters() {
  if (!isBackendEnabled()) {
    // Legacy fallback: filter only the currently loaded in-memory list.
    const level = document.getElementById("filter-level").value;
    const specificLevel = document.getElementById("filter-specific-level").value;
    const subjectGeneral = document.getElementById("filter-subject-general").value;
    const subjectCanonical = document.getElementById("filter-subject-canonical").value;
    const location = document.getElementById("filter-location").value;
    const minRate = document.getElementById("filter-rate").value;

    const filtered = allAssignments.filter((job) => {
      if (level && !(Array.isArray(job.signalsLevels) && job.signalsLevels.includes(level))) return false;
      if (specificLevel && !(Array.isArray(job.signalsSpecificLevels) && job.signalsSpecificLevels.includes(specificLevel))) return false;
      if (subjectGeneral && !(Array.isArray(job.subjectsGeneral) && job.subjectsGeneral.includes(subjectGeneral))) return false;
      if (subjectCanonical && !(Array.isArray(job.subjectsCanonical) && job.subjectsCanonical.includes(subjectCanonical))) return false;
      if (location) {
        const haystack = String(job.location || "").toLowerCase();
        const needle = String(location).toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      if (minRate && typeof job.rateMin === "number" && job.rateMin < parseInt(minRate, 10)) return false;
      if (minRate && typeof job.rateMin !== "number") return false;
      return true;
    });

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
  if (g) g.innerHTML = '<option value="">All General Subjects</option>';
  const c = document.getElementById("filter-subject-canonical");
  if (c) c.innerHTML = '<option value="">All Advanced Subjects</option>';
  document.getElementById("filter-location").value = "";
  const sortEl = document.getElementById("filter-sort");
  if (sortEl) sortEl.value = "newest";
  document.getElementById("filter-rate").value = "";
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
  select.title = canSortByDistance ? "" : "Set your postal code in Profile to enable Nearest sorting.";
  if (!canSortByDistance && select.value === "distance") {
    select.value = "newest";
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
        });
        if (loadToken === activeLoadToken) {
          lastFacets = facetsResp?.facets || null;
          // Rebuild dropdown options based on new facets.
          updateFilterSpecificLevels();
          updateFilterSubjects();
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
        ? Boolean(nextCursorLastSeen && nextCursorId !== null && nextCursorId !== undefined && nextCursorDistanceKm !== null && nextCursorDistanceKm !== undefined)
        : Boolean(nextCursorLastSeen && nextCursorId !== null && nextCursorId !== undefined);
    setLoadMoreVisible(canLoadMore);

    hideLoadError();
    renderCards(allAssignments);
    try {
      await trackEvent({ eventType: "assignments_view" });
    } catch {}
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

async function prepopulateFiltersFromProfile() {
  if (!isBackendEnabled()) return;

  try {
    await waitForAuth();
    const uid = await getCurrentUid();
    if (!uid) return;

    const profile = await getTutor(uid);
    if (!profile) return;

    const level = Array.isArray(profile.levels) ? profile.levels[0] : "";
    const subjectCanonical = Array.isArray(profile.subjects) ? profile.subjects[0] : "";
    const lat = profile?.postal_lat;
    const lon = profile?.postal_lon;
    hasPostalCoords = typeof lat === "number" && Number.isFinite(lat) && typeof lon === "number" && Number.isFinite(lon);
    applySortAvailability();

    if (level) {
      document.getElementById("filter-level").value = level;
      updateFilterSpecificLevels();
      updateFilterSubjects();
    }

    if (subjectCanonical) {
      const el = document.getElementById("filter-subject-canonical");
      if (el) el.value = subjectCanonical;
    }

    if (level || subjectCanonical) applyFilters();
  } catch (err) {
    console.error("Failed to prepopulate filters from profile.", err);
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
  if (retryLoadBtn) retryLoadBtn.addEventListener("click", () => loadAssignments({ reset: true }));
  if (loadMoreBtn) loadMoreBtn.addEventListener("click", () => loadAssignments({ append: true }));
  const sortEl = document.getElementById("filter-sort");
  if (sortEl) sortEl.addEventListener("change", () => loadAssignments({ reset: true }));
  mountDebugPanel();
  loadAssignments({ reset: true }).then(() => prepopulateFiltersFromProfile());
});
