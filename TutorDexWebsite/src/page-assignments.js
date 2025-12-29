import "../subjectsData.js";
import { isSupabaseEnabled, listOpenAssignments } from "./supabase.js";
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
import { getSupabaseConfigSummary } from "./supabase.js";

const BUILD_TIME = typeof __BUILD_TIME__ !== "undefined" ? __BUILD_TIME__ : "";

const subjectsData = window.tutorDexSubjects || window.subjectsData || {};
const specificLevelsData = window.tutorDexSpecificLevels || {};

function getSubjectsKey(level) {
  if (level === "IGCSE" || level === "IB") return "IB/IGCSE";
  return level;
}

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

function mapAssignmentRow(row) {
  const subject = (row?.subject || "").trim() || pickFirst(row?.subjects) || "Unknown";

  const learningMode = (row?.learning_mode || "").trim();
  const hasPhysicalLocation = Boolean((row?.address || "").trim() || (row?.postal_code || "").trim() || (row?.nearest_mrt || "").trim());
  const lm = learningMode.toLowerCase();
  const isOnlineOnly = Boolean(learningMode) && lm.includes("online") && !lm.includes("hybrid") && !lm.includes("face");

  const location =
    isOnlineOnly && !hasPhysicalLocation
      ? "Online"
      : (row?.address || "").trim() || (row?.postal_code || "").trim() || (row?.nearest_mrt || "").trim() || "Unknown";

  const rate = row?.rate_min ?? parseRate(row?.hourly_rate);

  let distanceKm = null;
  const dk = row?.distance_km;
  if (typeof dk === "number" && Number.isFinite(dk)) distanceKm = dk;
  else if (typeof dk === "string") {
    const parsed = Number.parseFloat(dk.trim());
    if (Number.isFinite(parsed)) distanceKm = parsed;
  }

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
    distanceKm,
    rate: typeof rate === "number" && Number.isFinite(rate) ? rate : null,
    gender: (row?.tutor_gender || row?.student_gender || "Any").trim(),
    freshnessTier: (row?.freshness_tier || "").trim() || "green",
    freq: freqBits.join(" / "),
    agencyName: (row?.agency_name || "").trim(),
    learningMode,
    updatedAt: (row?.last_seen || row?.created_at || "").trim(),
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
    const levelDisplay = job.specificLevel ? `${job.level} > ${job.specificLevel}` : job.level;

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
    rate.textContent = typeof job.rate === "number" ? `$${job.rate}/hr` : "N/A";

    header.appendChild(badge);
    header.appendChild(tierPill);
    header.appendChild(rate);

    const title = document.createElement("h3");
    title.className = "text-3xl brand-font leading-none mb-1";
    title.textContent = job.subject;

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

    addDetail("fa-solid fa-location-dot", job.location);
    if (typeof job.distanceKm === "number" && Number.isFinite(job.distanceKm)) {
      addDetail("fa-solid fa-ruler-combined", formatDistanceKm(job.distanceKm));
    }
    addDetail("fa-solid fa-clock", job.freq);
    addDetail("fa-solid fa-user", `Pref: ${job.gender}`);
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
  const subjectSelect = document.getElementById("filter-subject");
  const subjectsKey = getSubjectsKey(level);

  subjectSelect.innerHTML = '<option value="">All Subjects</option>';

  // Prefer server facets when available (accurate), fallback to static list.
  const facetOptions = Array.isArray(lastFacets?.subjects) ? lastFacets.subjects : null;
  if (facetOptions && facetOptions.length) {
    facetOptions.forEach((item) => {
      const name = String(item?.value || "").trim();
      if (!name) return;
      const option = document.createElement("option");
      option.value = name;
      option.text = item?.count ? `${name} (${item.count})` : name;
      subjectSelect.appendChild(option);
    });
    return;
  }

  if (subjectsData[subjectsKey]) {
    subjectsData[subjectsKey].forEach((sub) => {
      const option = document.createElement("option");
      option.value = sub;
      option.text = sub;
      subjectSelect.appendChild(option);
    });
  }
}

function collectFiltersFromUI() {
  return {
    level: (document.getElementById("filter-level")?.value || "").trim() || null,
    specificStudentLevel: (document.getElementById("filter-specific-level")?.value || "").trim() || null,
    subject: (document.getElementById("filter-subject")?.value || "").trim() || null,
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
    const subject = document.getElementById("filter-subject").value;
    const location = document.getElementById("filter-location").value;
    const minRate = document.getElementById("filter-rate").value;

    const filtered = allAssignments.filter((job) => {
      if (level && job.level !== level) return false;
      if (specificLevel && job.specificLevel !== specificLevel) return false;
      if (subject && job.subject !== subject) return false;
      if (location) {
        const haystack = String(job.location || "").toLowerCase();
        const needle = String(location).toLowerCase();
        if (!haystack.includes(needle)) return false;
      }
      if (minRate && typeof job.rate === "number" && job.rate < parseInt(minRate, 10)) return false;
      if (minRate && typeof job.rate !== "number") return false;
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
  document.getElementById("filter-subject").innerHTML = '<option value="">All Subjects</option>';
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
    return "Assignments unavailable: backend is up, but the Supabase RPC functions for pagination/facets are missing or failing. Apply the SQL in `TutorDexAggregator/supabase sqls/2025-12-25_assignments_facets_pagination.sql` and try again.";
  }

  if (msg.includes("supabase_disabled")) {
    return "Assignments unavailable: backend Supabase integration is disabled/misconfigured (check SUPABASE_ENABLED, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY).";
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
      supabase: getSupabaseConfigSummary(),
    });
  }

  if (!isBackendEnabled() && !isSupabaseEnabled()) {
    const cfg = getSupabaseConfigSummary();
    if (isDebugEnabled()) debugLog("Supabase disabled (config)", cfg);

    const missing = [];
    if (!cfg.urlPresent) missing.push("VITE_SUPABASE_URL");
    if (!cfg.anonKeyPresent) missing.push("VITE_SUPABASE_ANON_KEY");

    setStatus(
      missing.length ? `Assignments unavailable (missing ${missing.join(", ")}).` : "Assignments unavailable (Supabase not configured).",
      "error",
      { showRetry: true }
    );
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
    setStatus(isBackendEnabled() ? "Loading assignments from backend..." : "Loading assignments from Supabase...", "info");
    renderSkeleton(6);
  }
  try {
    if (isBackendEnabled()) {
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
        subject: filters.subject,
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
    } else {
      const items = await listOpenAssignments({ limit: 200 });
      allAssignments = items.length ? items : [];
      totalAssignments = allAssignments.length;
      setLoadMoreVisible(false);
      setFacetHintVisible(false);
    }

    hideLoadError();
    renderCards(allAssignments);
    try {
      await trackEvent({ eventType: "assignments_view" });
    } catch {}
    setStatus(
      isBackendEnabled()
        ? `Loaded ${allAssignments.length} of ${totalAssignments} assignments.`
        : `Loaded ${allAssignments.length} assignments from Supabase.`,
      "success"
    );
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

    console.error("Failed to load assignments from Supabase.", err);
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
    const subject = Array.isArray(profile.subjects) ? profile.subjects[0] : "";
    const lat = profile?.postal_lat;
    const lon = profile?.postal_lon;
    hasPostalCoords = typeof lat === "number" && Number.isFinite(lat) && typeof lon === "number" && Number.isFinite(lon);
    applySortAvailability();

    if (level) {
      document.getElementById("filter-level").value = level;
      updateFilterSpecificLevels();
      updateFilterSubjects();
    }

    if (subject) {
      document.getElementById("filter-subject").value = subject;
    }

    if (level || subject) applyFilters();
  } catch (err) {
    console.error("Failed to prepopulate filters from profile.", err);
  }
}

function mountDebugPanel() {
  if (!isDebugEnabled()) return;

  const host = document.querySelector(".max-w-6xl") || document.body;
  if (!host || document.getElementById("debug-panel")) return;

  const cfg = getSupabaseConfigSummary();

  const wrap = document.createElement("div");
  wrap.id = "debug-panel";
  wrap.className = "mt-6";

  wrap.innerHTML = `
    <details class="border border-gray-200 rounded-xl p-4 bg-white">
      <summary class="cursor-pointer font-bold uppercase text-xs tracking-wide text-gray-600">Debug</summary>
      <div class="mt-3 text-sm text-gray-700 space-y-2">
        <div><span class="font-semibold">Build time:</span> <span class="font-mono">${BUILD_TIME || "(unknown)"}</span></div>
        <div><span class="font-semibold">Mode:</span> <span class="font-mono">${cfg.mode || "(unknown)"}</span></div>
        <div><span class="font-semibold">Supabase enabled:</span> <span class="font-mono">${String(cfg.enabled)}</span></div>
        <div><span class="font-semibold">Supabase host:</span> <span class="font-mono">${cfg.urlHost || "(missing)"}</span></div>
        <div><span class="font-semibold">Assignments table:</span> <span class="font-mono">${cfg.table || "(missing)"}</span></div>
        <div><span class="font-semibold">Anon key:</span> <span class="font-mono">${cfg.anonKeyPreview || "(missing)"}</span></div>
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
