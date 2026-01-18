import { getCurrentUid, waitForAuth } from "../auth.js";
import { getOpenAssignmentFacets, getTutor, isBackendEnabled, listOpenAssignmentsPaged, sendClickBeacon, trackEvent } from "./backend.js";
import { debugLog, isDebugEnabled } from "./debug.js";
import { reportError, addBreadcrumb, setUserContext } from "./errorReporter.js";
import { SPECIFIC_LEVELS } from "./academicEnums.js";
import {
  canonicalSubjectsForLevel,
  generalCategoriesForLevel,
  generalCategoryOptions,
  labelForCanonicalCode,
  labelForGeneralCategoryCode,
  labelsForCanonicalCodes,
  labelsForGeneralCategoryCodes,
  searchSubjects,
} from "./taxonomy/subjectsTaxonomyV2.js";
import { matchesFilters } from "./lib/filterUtils.js";
import { formatDistanceKm, formatRelativeTime, formatShortDate, parseRate, pickFirst, toText, toStringList } from "./lib/assignmentFormatters.js";
import {
  readFilters as readStoredFilters,
  readLastVisitMs,
  readViewMode,
  writeFilters as writeStoredFilters,
  writeLastVisitMs,
  writeViewMode,
} from "./lib/assignmentStorage.js";
import { $id } from "./lib/domUtils.js";

import { BUILD_TIME, E, MAX_SUBJECT_CHIPS, S } from "./page-assignments.state.js";
import {
  renderCards,
  renderSkeleton,
  renderSubjectTray,
  _ensureSubjectStateInitialized,
  _addSubjectSelection,
  _removeSubjectSelection,
  _collectSubjectCsv,
  renderLoadError,
  hideLoadError,
  setStatus,
  updateGridLayout,
  updateViewToggleUI,
  setViewMode,
  setResultsSummary,
  mapAssignmentRow,
  setFiltersChangedHandler,
  setRetryLoadHandler,
} from "./page-assignments.render.js";

function snapshotFiltersForStorage() {
  const filters = collectFiltersFromUI();
  return {
    v: 2,
    level: filters.level || "",
    specificStudentLevel: filters.specificStudentLevel || "",
    subjects: filters.subject || "",
    subjectsGeneral: Array.isArray(S.selectedSubjects?.general) ? S.selectedSubjects.general : [],
    subjectsCanonical: Array.isArray(S.selectedSubjects?.canonical) ? S.selectedSubjects.canonical : [],
    subjectsOrder: Array.isArray(S.selectedSubjectOrder) ? S.selectedSubjectOrder : [],
    sort: filters.sort || "newest",
    minRate: filters.minRate || "",
    savedAtMs: Date.now(),
  };
}

// Track whether we've written last-visit timestamp this session to avoid repeated writes
let didWriteLastVisitThisSession = false;

function restoreFiltersIntoUI(stored) {
  if (!stored || typeof stored !== "object") return false;
  const levelEl = document.getElementById("filter-level");
  const specificEl = document.getElementById("filter-specific-level");
  const sortEl = document.getElementById("filter-sort");
  const rateEl = document.getElementById("filter-rate");
  if (!levelEl || !specificEl || !sortEl || !rateEl) return false;
  // Handle versioning of stored snapshot
  const v = Number.isFinite(Number(stored.v)) ? Number(stored.v) : 1;

  levelEl.value = String(stored.level || "");
  sortEl.value = String(stored.sort || "newest");
  rateEl.value = String(stored.minRate || "");

  // Options may not exist yet; set pending targets so updateFilter* can re-select after rebuild.
  pendingFilters.specificStudentLevel = String(stored.specificStudentLevel || "").trim() || null;
  pendingFilters.level = String(stored.level || "").trim() || null;

  _ensureSubjectStateInitialized();
  S.selectedSubjects = { general: [], canonical: [] };
  S.selectedSubjectOrder = [];

  if (v === 2) {
    const order = Array.isArray(stored.subjectsOrder) ? stored.subjectsOrder : [];
    for (const item of order) {
      const type = _normalizeSubjectType(item?.type);
      const code = String(item?.code || "").trim();
      const label = String(item?.label || "").trim();
      if (!code) continue;
      _addSubjectSelection(type, code, { silent: true, label });
    }
    // Backfill from arrays if present (for older v2 snapshots).
    const gen = Array.isArray(stored.subjectsGeneral) ? stored.subjectsGeneral : [];
    const canon = Array.isArray(stored.subjectsCanonical) ? stored.subjectsCanonical : [];
    for (const c of gen) _addSubjectSelection("general", c, { silent: true });
    for (const c of canon) _addSubjectSelection("canonical", c, { silent: true });
  } else if (v === 1) {
    const g = String(stored.subjectGeneral || "").trim();
    const c = String(stored.subjectCanonical || "").trim();
    if (g) _addSubjectSelection("general", g, { silent: true });
    if (c) _addSubjectSelection("canonical", c, { silent: true });
  }

  renderSubjectTray();

  // Trigger UI rebuilds which will pick up pendingFilters when facets arrive
  updateFilterSpecificLevels();
  updateFilterSubjects();
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
      btn.className = "w-full text-left px-4 py-3 hover:bg-muted/60 transition flex items-center justify-between gap-3";
      btn.setAttribute("role", "option");
      btn.tabIndex = 0;

      const left = document.createElement("span");
      left.className = "text-sm font-semibold text-foreground";
      left.textContent = String(item.label || item.code || "").trim();

      const right = document.createElement("span");
      right.className = "text-xs font-mono text-muted-foreground";
      const t = String(item.type || "").trim();
      right.textContent = t === "general" ? `BROAD · ${String(item.code || "").trim()}` : `SPEC · ${String(item.code || "").trim()}`;

      btn.appendChild(left);
      btn.appendChild(right);
      btn.addEventListener("click", () => {
        const code = String(item.code || "").trim();
        if (!code) return;
        if (String(item.type || "").trim() === "general") {
          _addSubjectSelection("general", code, { label: item.label });
        } else {
          _addSubjectSelection("canonical", code, { label: item.label });
        }
        input.value = "";
        hideResults();
        input.blur();
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
  const facetOptions = Array.isArray(S.lastFacets?.specific_levels) ? S.lastFacets.specific_levels : null;
  const allowed = new Set((options || []).map((v) => String(v || "").trim()).filter(Boolean));
  const items = (() => {
    if (facetOptions && facetOptions.length) {
      return facetOptions.filter((it) => allowed.has(String(it?.value || "").trim()));
    }
    return (options || []).map((value) => ({ value, count: null }));
  })();

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

  // Preserve previous selection only if it is valid for the selected level.
  const cur = String(currentSelected || "").trim();
  if (cur && allowed.has(cur) && Array.from(specificSelect.options || []).some((o) => String(o.value || "").trim() === cur)) {
    specificSelect.value = cur;
  } else {
    specificSelect.value = "";
  }
  specificSelect.disabled = false;

  // Re-apply any pending selection restored earlier if facets arrived late
  if (pendingFilters.specificStudentLevel) {
    const v = String(pendingFilters.specificStudentLevel || "").trim();
    if (v && allowed.has(v) && Array.from(specificSelect.options || []).some((o) => String(o.value || "").trim() === v)) specificSelect.value = v;
    pendingFilters.specificStudentLevel = null;
  }
}

function updateFilterSubjects() {
  const level = String($id("filter-level")?.value || "").trim();
  if (!level) {
    renderSubjectTray();
    return;
  }

  const allowedGeneral = new Set(
    generalCategoriesForLevel(level, { includeAny: false })
      .map((c) => String(c?.code || "").trim())
      .filter(Boolean)
  );
  const allowedCanonical = new Set(
    canonicalSubjectsForLevel(level, { includeAny: false })
      .map((s) => String(s?.code || "").trim())
      .filter(Boolean)
  );

  _ensureSubjectStateInitialized();
  const before = _collectSubjectCsv();
  S.selectedSubjects.general = (S.selectedSubjects.general || []).filter((c) => allowedGeneral.has(String(c || "").trim()));
  S.selectedSubjects.canonical = (S.selectedSubjects.canonical || []).filter((c) => allowedCanonical.has(String(c || "").trim()));
  const allowedKeys = new Set([
    ...(S.selectedSubjects.general || []).map((c) => _subjectKey("general", c)),
    ...(S.selectedSubjects.canonical || []).map((c) => _subjectKey("canonical", c)),
  ]);
  S.selectedSubjectOrder = (S.selectedSubjectOrder || []).filter((x) => allowedKeys.has(_subjectKey(x?.type, x?.code)));
  renderSubjectTray();

  const after = _collectSubjectCsv();
  if (before !== after) writeStoredFilters(snapshotFiltersForStorage());
}

function collectFiltersFromUI() {
  return {
    level: (document.getElementById("filter-level")?.value || "").trim() || null,
    specificStudentLevel: (document.getElementById("filter-specific-level")?.value || "").trim() || null,
    subject: _collectSubjectCsv(),
    sort: (document.getElementById("filter-sort")?.value || "").trim() || "newest",
    minRate: (document.getElementById("filter-rate")?.value || "").trim() || null,
  };
}

// Centralized helper to check if a job matches a filters object.
// `matchesFilters` is implemented in `src/lib/filterUtils.js` and imported above.

async function applyFilters() {
  writeStoredFilters(snapshotFiltersForStorage());
  if (!isBackendEnabled()) {
    // Legacy fallback: filter only the currently loaded in-memory list.
    const filters = collectFiltersFromUI();
    const filtered = S.allAssignments.filter((job) => matchesFilters(job, filters));
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
  S.selectedSubjects = { general: [], canonical: [] };
  S.selectedSubjectOrder = [];
  renderSubjectTray();
  const subjectSearch = document.getElementById("subject-search");
  if (subjectSearch) subjectSearch.value = "";
  const subjectSearchResults = document.getElementById("subject-search-results");
  if (subjectSearchResults) {
    subjectSearchResults.classList.add("hidden");
    subjectSearchResults.innerHTML = "";
  }
  const sortEl = document.getElementById("filter-sort");
  if (sortEl) sortEl.value = "newest";
  document.getElementById("filter-rate").value = "";
  writeStoredFilters(snapshotFiltersForStorage());
  if (!isBackendEnabled()) {
    renderCards(S.allAssignments);
    return;
  }
  void loadAssignments({ reset: true });
}

window.updateFilterSpecificLevels = updateFilterSpecificLevels;
window.updateFilterSubjects = updateFilterSubjects;
window.applyFilters = applyFilters;
window.clearFilters = clearFilters;

function setLoadMoreVisible(canLoadMore) {
  if (!E.loadMoreBtn) return;
  E.loadMoreBtn.classList.toggle("hidden", !canLoadMore);
}

function setFacetHintVisible(show) {
  if (!E.facetHint) return;
  E.facetHint.classList.toggle("hidden", !show);
}

function applySortAvailability() {
  const select = document.getElementById("filter-sort");
  if (!select) return;
  const option = Array.from(select.options).find((o) => o.value === "distance");
  const canSortByDistance = S.hasPostalCoords === true;
  if (option) option.disabled = !canSortByDistance;
  select.title = canSortByDistance ? "" : "Sign in and set your postal code in Profile to enable Nearest sorting.";
  if (!canSortByDistance && select.value === "distance") {
    select.value = "newest";
  }

  const cta = document.getElementById("postal-cta");
  if (cta) {
    cta.classList.toggle("hidden", canSortByDistance);
    cta.setAttribute("href", S.currentUid ? "profile.html" : "index.html?next=profile.html");
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
  const loadToken = ++S.activeLoadToken;
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
    S.allAssignments = [];
    S.totalAssignments = 0;
    S.nextCursorLastSeen = null;
    S.nextCursorId = null;
    renderLoadError("Assignments are temporarily unavailable. Please try again.");
    return;
  }

  if (reset) {
    S.allAssignments = [];
    S.totalAssignments = 0;
    S.nextCursorLastSeen = null;
    S.nextCursorId = null;
    S.nextCursorDistanceKm = null;
  }

  const isInitial = !append && S.allAssignments.length === 0;
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
          minRate: Number.isFinite(minRate) ? minRate : null,
        });
        if (loadToken === S.activeLoadToken) {
          S.lastFacets = facetsResp?.facets || null;
          // Rebuild dropdown options based on new facets.
          updateFilterSpecificLevels();
          updateFilterSubjects();
          setFacetHintVisible(Boolean(S.lastFacets));
        }
      } catch (e) {
        if (loadToken === S.activeLoadToken) {
          S.lastFacets = null;
          setFacetHintVisible(false);
        }
      }
    }

    const page = await listOpenAssignmentsPaged({
      limit: 50,
      sort,
      cursorLastSeen: append ? S.nextCursorLastSeen : null,
      cursorId: append ? S.nextCursorId : null,
      cursorDistanceKm: append && sort === "distance" ? S.nextCursorDistanceKm : null,
      level: filters.level,
      specificStudentLevel: filters.specificStudentLevel,
      subject: filters.subject,
      minRate: Number.isFinite(minRate) ? minRate : null,
    });

    if (loadToken !== S.activeLoadToken) return;

    const rows = Array.isArray(page?.items) ? page.items : [];
    const mapped = rows.map(mapAssignmentRow);
    S.allAssignments = append ? [...S.allAssignments, ...mapped] : mapped;
    S.totalAssignments = Number.isFinite(page?.total) ? page.total : S.allAssignments.length;
    S.nextCursorLastSeen = page?.next_cursor_last_seen || null;
    S.nextCursorId = page?.next_cursor_id ?? null;
    S.nextCursorDistanceKm = page?.next_cursor_distance_km ?? null;
    const canLoadMore =
      sort === "distance"
        ? Boolean(
            S.nextCursorLastSeen &&
              S.nextCursorId !== null &&
              S.nextCursorId !== undefined &&
              S.nextCursorDistanceKm !== null &&
              S.nextCursorDistanceKm !== undefined
          )
        : Boolean(S.nextCursorLastSeen && S.nextCursorId !== null && S.nextCursorId !== undefined);
    setLoadMoreVisible(canLoadMore);

    hideLoadError();
    renderCards(S.allAssignments);
    try {
      await trackEvent({ eventType: "assignments_view" });
    } catch {}

    if (!didWriteLastVisitThisSession) {
      didWriteLastVisitThisSession = true;
      writeLastVisitMs(Date.now());
    }
    setStatus(`Loaded ${S.allAssignments.length} of ${S.totalAssignments} assignments.`, "success");
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

    // Report error to Sentry/console
    reportError(err, {
      context: "loadAssignments",
      filters: collectFiltersFromUI(),
      isInitial,
      append,
      reset,
    });

    console.error("Failed to load assignments from backend.", err);
    const friendly = formatAssignmentsLoadError(err);
    setStatus(friendly, "error", { showRetry: true });
    S.allAssignments = [];
    S.totalAssignments = 0;
    S.nextCursorLastSeen = null;
    S.nextCursorId = null;
    S.nextCursorDistanceKm = null;
    renderLoadError(friendly);
  }
}

async function loadProfileContext() {
  if (!isBackendEnabled()) return;

  try {
    await waitForAuth();
    const uid = await getCurrentUid();
    if (!uid) return;
    S.currentUid = uid;

    // Set user context for error reporting
    setUserContext(uid);
    addBreadcrumb("User authenticated", { uid }, "auth");

    const profile = await getTutor(uid);
    if (!profile) return;
    S.myTutorProfile = profile;

    const lat = profile?.postal_lat;
    const lon = profile?.postal_lon;
    S.hasPostalCoords = typeof lat === "number" && Number.isFinite(lat) && typeof lon === "number" && Number.isFinite(lon);
    applySortAvailability();
  } catch (err) {
    console.error("Failed to load profile context.", err);
    reportError(err, { context: "loadProfileContext" });
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
    <details class="border border-border rounded-2xl p-4 bg-background">
      <summary class="cursor-pointer font-bold uppercase text-xs tracking-wide text-muted-foreground">Debug</summary>
      <div class="mt-3 text-sm text-muted-foreground space-y-2">
        <div><span class="font-semibold">Build time:</span> <span class="font-mono">${BUILD_TIME || "(unknown)"}</span></div>
        <div><span class="font-semibold">Backend enabled:</span> <span class="font-mono">${String(isBackendEnabled())}</span></div>
      </div>
    </details>
	  `.trim();

  host.appendChild(wrap);
}

export function initAssignmentsPage() {
  S.viewMode = readViewMode();
  S.lastVisitCutoffMs = readLastVisitMs();

  setFiltersChangedHandler(() => {
    writeStoredFilters(snapshotFiltersForStorage());
    void loadAssignments({ reset: true });
  });
  setRetryLoadHandler(() => {
    void loadAssignments({ reset: true });
  });

  const fullBtn = document.getElementById("view-toggle-full");
  const compactBtn = document.getElementById("view-toggle-compact");
  if (fullBtn) fullBtn.addEventListener("click", () => setViewMode("full"));
  if (compactBtn) compactBtn.addEventListener("click", () => setViewMode("compact"));

  updateViewToggleUI();
  updateGridLayout();
  mountSubjectSearch();
  // Tutor type filter is dropdown-only (no free-text search).

  if (E.retryLoadBtn) E.retryLoadBtn.addEventListener("click", () => loadAssignments({ reset: true }));
  if (E.loadMoreBtn) E.loadMoreBtn.addEventListener("click", () => loadAssignments({ append: true }));
  const sortEl = document.getElementById("filter-sort");
  if (sortEl) {
    sortEl.addEventListener("change", () => {
      writeStoredFilters(snapshotFiltersForStorage());
      loadAssignments({ reset: true });
    });
  }

  try {
    const stored = readStoredFilters();
    S.didRestoreFiltersFromStorage = restoreFiltersIntoUI(stored);
  } catch {
    S.didRestoreFiltersFromStorage = false;
  }
  mountDebugPanel();
  loadAssignments({ reset: true }).then(() => {
    // Load profile for "Matches you" + Nearest availability, but do not auto-apply preferences as filters.
    void loadProfileContext();
  });
}
