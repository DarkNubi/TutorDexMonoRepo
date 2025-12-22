import "../subjectsData.js";
import { isSupabaseEnabled, listOpenAssignments } from "./supabase.js";
import { getCurrentUid, waitForAuth } from "../auth.js";
import { getTutor, isBackendEnabled, trackEvent } from "./backend.js";
import { debugLog, isDebugEnabled } from "./debug.js";
import { getSupabaseConfigSummary } from "./supabase.js";

const BUILD_TIME = typeof __BUILD_TIME__ !== "undefined" ? __BUILD_TIME__ : "";

const subjectsData = window.tutorDexSubjects || window.subjectsData || {};
const specificLevelsData = window.tutorDexSpecificLevels || {};

function getSubjectsKey(level) {
  if (level === "IGCSE" || level === "International Baccalaureate") return "IB/IGCSE";
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
let allAssignments = [];

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

function renderSkeleton(count = 6) {
  grid.innerHTML = "";
  noResults.classList.add("hidden");
  countLabel.innerText = "...";
  setResultsSummary(0, 0);

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
    setResultsSummary(0, allAssignments.length);
    return;
  }

  noResults.classList.add("hidden");
  countLabel.innerText = String(data.length);
  setResultsSummary(data.length, allAssignments.length);

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

    const tier = String(job?.freshnessTier || "green").trim().toLowerCase();
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
    applyBtn.className =
      "w-full py-4 border-2 border-black rounded-lg font-bold uppercase tracking-wide transition text-center";
    applyBtn.textContent = messageLink ? "Apply Now" : "Link Unavailable";
    if (messageLink) {
      applyBtn.href = messageLink;
      applyBtn.target = "_blank";
      applyBtn.rel = "noopener noreferrer";
      applyBtn.className += " hover:bg-black hover:text-white";
      applyBtn.addEventListener("click", async () => {
        try {
          await trackEvent({ eventType: "apply_click", assignmentExternalId: job.id, hasMessageLink: true });
        } catch {}
      });
    } else {
      applyBtn.type = "button";
      applyBtn.disabled = true;
      applyBtn.className += " opacity-40 cursor-not-allowed";
      applyBtn.addEventListener("click", async () => {
        try {
          await trackEvent({ eventType: "apply_click", assignmentExternalId: job.id, hasMessageLink: false });
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

  if (!level || options.length === 0) {
    specificSelect.disabled = true;
    return;
  }

  options.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.text = name;
    specificSelect.appendChild(option);
  });

  specificSelect.disabled = false;
}

function updateFilterSubjects() {
  const level = document.getElementById("filter-level").value;
  const subjectSelect = document.getElementById("filter-subject");
  const subjectsKey = getSubjectsKey(level);

  subjectSelect.innerHTML = '<option value="">All Subjects</option>';

  if (subjectsData[subjectsKey]) {
    subjectsData[subjectsKey].forEach((sub) => {
      const option = document.createElement("option");
      option.value = sub;
      option.text = sub;
      subjectSelect.appendChild(option);
    });
  }
}

function applyFilters() {
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
}

function clearFilters() {
  document.getElementById("filter-level").value = "";
  document.getElementById("filter-specific-level").value = "";
  document.getElementById("filter-specific-level").innerHTML = '<option value="">All Specific Levels</option>';
  document.getElementById("filter-specific-level").disabled = true;
  document.getElementById("filter-subject").innerHTML = '<option value="">All Subjects</option>';
  document.getElementById("filter-location").value = "";
  document.getElementById("filter-rate").value = "";
  renderCards(allAssignments);
}

window.updateFilterSpecificLevels = updateFilterSpecificLevels;
window.updateFilterSubjects = updateFilterSubjects;
window.applyFilters = applyFilters;
window.clearFilters = clearFilters;

async function loadAssignments() {
  if (isDebugEnabled()) {
    debugLog("Assignments page boot", {
      buildTime: BUILD_TIME,
      pathname: window.location.pathname,
      supabase: getSupabaseConfigSummary(),
    });
  }

  if (!isSupabaseEnabled()) {
    const cfg = getSupabaseConfigSummary();
    if (isDebugEnabled()) debugLog("Supabase disabled (config)", cfg);

    const missing = [];
    if (!cfg.urlPresent) missing.push("VITE_SUPABASE_URL");
    if (!cfg.anonKeyPresent) missing.push("VITE_SUPABASE_ANON_KEY");

    setStatus(
      missing.length
        ? `Assignments unavailable (missing ${missing.join(", ")}).`
        : "Assignments unavailable (Supabase not configured).",
      "error",
      { showRetry: true }
    );
    allAssignments = [];
    renderLoadError("Assignments are temporarily unavailable. Please try again.");
    return;
  }

  setStatus("Loading assignments from Supabase...", "info");
  renderSkeleton(6);
  try {
    const items = await listOpenAssignments({ limit: 200 });
    allAssignments = items.length ? items : [];
    hideLoadError();
    renderCards(allAssignments);
    try {
      await trackEvent({ eventType: "assignments_view" });
    } catch {}
    setStatus(`Loaded ${allAssignments.length} assignments from Supabase.`, "success");
  } catch (err) {
    console.error("Failed to load assignments from Supabase.", err);
    setStatus(`Assignments unavailable (${err?.message || err}).`, "error", { showRetry: true });
    allAssignments = [];
    renderLoadError("We couldn’t load assignments right now. Please try again.");
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
  if (retryLoadBtn) retryLoadBtn.addEventListener("click", () => loadAssignments());
  mountDebugPanel();
  loadAssignments().then(() => prepopulateFiltersFromProfile());
});
