import { sendClickBeacon, trackEvent } from "./backend.js";
import {
  labelForCanonicalCode,
  labelForGeneralCategoryCode,
  labelsForCanonicalCodes,
  labelsForGeneralCategoryCodes,
} from "./taxonomy/subjectsTaxonomyV2.js";
import { formatDistanceKm, formatRelativeTime, formatShortDate, parseRate, pickFirst, toText, toStringList } from "./lib/assignmentFormatters.js";
import { writeViewMode } from "./lib/assignmentStorage.js";

import { E, MAX_SUBJECT_CHIPS, S } from "./page-assignments.state.js";

let _onFiltersChanged = null;
let _onRetryLoad = null;

export function setFiltersChangedHandler(fn) {
  _onFiltersChanged = typeof fn === "function" ? fn : null;
}

export function setRetryLoadHandler(fn) {
  _onRetryLoad = typeof fn === "function" ? fn : null;
}

function _subjectKey(type, code) {
  return `${String(type || "").trim()}:${String(code || "").trim()}`;
}

function _normalizeSubjectType(type) {
  const t = String(type || "")
    .trim()
    .toLowerCase();
  return t === "canonical" ? "canonical" : "general";
}

function _subjectLabel(type, code) {
  const c = String(code || "").trim();
  if (!c) return "";
  if (_normalizeSubjectType(type) === "canonical") return labelForCanonicalCode(c) || c;
  return labelForGeneralCategoryCode(c) || c;
}

function _ensureSubjectStateInitialized() {
  if (!S.selectedSubjects || typeof S.selectedSubjects !== "object") S.selectedSubjects = { general: [], canonical: [] };
  if (!Array.isArray(S.selectedSubjects.general)) S.selectedSubjects.general = [];
  if (!Array.isArray(S.selectedSubjects.canonical)) S.selectedSubjects.canonical = [];
  if (!Array.isArray(S.selectedSubjectOrder)) S.selectedSubjectOrder = [];
}

function _removeSubjectSelection(type, code, { silent = false } = {}) {
  _ensureSubjectStateInitialized();
  const t = _normalizeSubjectType(type);
  const c = String(code || "").trim();
  if (!c) return false;
  S.selectedSubjects[t] = (S.selectedSubjects[t] || []).filter((x) => String(x || "").trim() !== c);
  const k = _subjectKey(t, c);
  S.selectedSubjectOrder = (S.selectedSubjectOrder || []).filter((x) => _subjectKey(x?.type, x?.code) !== k);
  renderSubjectTray();
  if (!silent) {
    if (_onFiltersChanged) _onFiltersChanged();
  }
  return true;
}

function _addSubjectSelection(type, code, { silent = false, label = "" } = {}) {
  _ensureSubjectStateInitialized();
  const t = _normalizeSubjectType(type);
  const c = String(code || "").trim();
  if (!c) return false;

  // Toggle off if already selected.
  const existing = new Set((S.selectedSubjects[t] || []).map((x) => String(x || "").trim()));
  if (existing.has(c)) return _removeSubjectSelection(t, c, { silent });

  // Enforce max chips across both types.
  const total = (S.selectedSubjects.general || []).length + (S.selectedSubjects.canonical || []).length;
  if (total >= MAX_SUBJECT_CHIPS) {
    const oldest = S.selectedSubjectOrder && S.selectedSubjectOrder.length ? S.selectedSubjectOrder[0] : null;
    if (oldest?.type && oldest?.code) _removeSubjectSelection(oldest.type, oldest.code, { silent: true });
  }

  S.selectedSubjects[t] = [...(S.selectedSubjects[t] || []), c];
  S.selectedSubjectOrder = [...(S.selectedSubjectOrder || []), { type: t, code: c, label: String(label || "").trim() || null }];
  renderSubjectTray();

  if (!silent) {
    if (_onFiltersChanged) _onFiltersChanged();
  }
  return true;
}

function renderSubjectTray() {
  _ensureSubjectStateInitialized();
  const tray = document.getElementById("subjects-tray");
  const empty = document.getElementById("subjects-tray-empty");
  if (!tray) return;

  tray.innerHTML = "";
  const items = (S.selectedSubjectOrder || [])
    .map((x) => ({ type: _normalizeSubjectType(x?.type), code: String(x?.code || "").trim(), label: String(x?.label || "").trim() }))
    .filter((x) => x.code);

  if (!items.length) {
    if (empty) empty.classList.remove("hidden");
    return;
  }
  if (empty) empty.classList.add("hidden");

  for (const item of items) {
    const chip = document.createElement("span");
    chip.className = "badge flex items-center gap-2 max-w-full";
    chip.title = item.type === "canonical" ? "Specific syllabus" : "Broad subject";

    const text = document.createElement("span");
    text.className = "truncate";
    text.textContent = item.label || _subjectLabel(item.type, item.code) || item.code;

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "text-xs font-bold opacity-70 hover:opacity-100";
    remove.setAttribute("aria-label", `Remove ${text.textContent}`);
    remove.textContent = "×";
    remove.addEventListener("click", () => _removeSubjectSelection(item.type, item.code));

    chip.appendChild(text);
    chip.appendChild(remove);
    tray.appendChild(chip);
  }
}

function _collectSubjectCsv() {
  _ensureSubjectStateInitialized();
  const tokens = [];
  for (const code of S.selectedSubjects.general || []) tokens.push(String(code || "").trim());
  for (const code of S.selectedSubjects.canonical || []) tokens.push(String(code || "").trim());
  const uniq = [];
  const seen = new Set();
  for (const t of tokens) {
    const v = String(t || "").trim();
    if (!v || seen.has(v)) continue;
    seen.add(v);
    uniq.push(v);
  }
  return uniq.length ? uniq.join(",") : null;
}

// Pending selections preserved across async facet refreshes
const pendingFilters = { level: null, specificStudentLevel: null };

function getOrCreateStatusEl() {
  const host = document.querySelector(".max-w-6xl") || document.body;
  let el = document.getElementById("data-source-status");
  if (el) return el;
  el = document.createElement("div");
  el.id = "data-source-status";
  el.className = "text-sm font-medium text-muted-foreground mt-2 flex items-center gap-3";

  const text = document.createElement("span");
  text.id = "data-source-status-text";
  el.appendChild(text);

  const retry = document.createElement("button");
  retry.id = "data-source-status-retry";
  retry.type = "button";
  retry.className = "hidden text-xs font-bold uppercase underline";
  retry.textContent = "Retry";
  retry.addEventListener("click", () => {
    if (_onRetryLoad) _onRetryLoad();
  });
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
  if (kind === "error") el.className += " text-red-400";
  else if (kind === "success") el.className += " text-emerald-300";
  else if (kind === "warning") el.className += " text-amber-300";
  else el.className += " text-muted-foreground";
}

function updateGridLayout() {
  if (!E.grid) return;
  if (S.viewMode === "compact") {
    E.grid.className = "grid grid-cols-1 gap-3";
  } else {
    E.grid.className = "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6";
  }
}

function setViewMode(next) {
  S.viewMode = next === "compact" ? "compact" : "full";
  writeViewMode(S.viewMode);
  updateViewToggleUI();
  updateGridLayout();
  renderCards(S.allAssignments);
}

function updateViewToggleUI() {
  const fullBtn = document.getElementById("view-toggle-full");
  const compactBtn = document.getElementById("view-toggle-compact");
  const activeClasses = ["bg-gradient-to-r", "from-blue-600", "to-indigo-600", "text-white", "border-transparent"];
  if (fullBtn) activeClasses.forEach((cls) => fullBtn.classList.toggle(cls, S.viewMode === "full"));
  if (compactBtn) activeClasses.forEach((cls) => compactBtn.classList.toggle(cls, S.viewMode === "compact"));
}

function setResultsSummary(showing, total) {
  if (!E.resultsSummary) return;
  const s = Number.isFinite(showing) ? showing : 0;
  const t = Number.isFinite(total) ? total : 0;
  E.resultsSummary.textContent = `Showing ${s} of ${t}`;
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

function hasMatchForMe(job) {
  const me = S.myTutorProfile;
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
  const me = S.myTutorProfile;
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

function renderSkeleton(count = 6) {
  E.grid.innerHTML = "";
  updateGridLayout();
  E.noResults.classList.add("hidden");
  E.countLabel.innerText = "...";
  setResultsSummary(0, 0);
  if (E.loadMoreBtn) E.loadMoreBtn.classList.add("hidden");
  if (E.facetHint) E.facetHint.classList.add("hidden");

  for (let i = 0; i < count; i++) {
    const card = document.createElement("div");
    card.className = "job-card rounded-2xl p-6 relative flex flex-col justify-between h-full animate-pulse";
    card.innerHTML = `
      <div>
        <div class="flex justify-between items-start mb-4">
          <div class="h-6 w-24 bg-muted/60 rounded-full"></div>
          <div class="h-6 w-16 bg-muted/60 rounded-full"></div>
          <div class="h-6 w-14 bg-muted/60 rounded"></div>
        </div>
        <div class="h-8 w-2/3 bg-muted/60 rounded mb-3"></div>
        <div class="h-4 w-1/2 bg-muted/60 rounded mb-6"></div>
        <div class="space-y-3 mb-8">
          <div class="h-4 w-5/6 bg-muted/60 rounded"></div>
          <div class="h-4 w-4/6 bg-muted/60 rounded"></div>
          <div class="h-4 w-3/6 bg-muted/60 rounded"></div>
        </div>
      </div>
      <div class="h-12 w-full bg-muted/60 rounded-lg"></div>
    `.trim();
    E.grid.appendChild(card);
  }
}

function renderCards(data) {
  E.grid.innerHTML = "";
  updateGridLayout();

  const visible = Array.isArray(data) ? data : [];
  if (visible.length === 0) {
    E.noResults.classList.remove("hidden");
    E.countLabel.innerText = "0";
    setResultsSummary(0, S.totalAssignments);
    if (E.loadMoreBtn) E.loadMoreBtn.classList.add("hidden");
    return;
  }

  E.noResults.classList.add("hidden");
  E.countLabel.innerText = String(visible.length);
  setResultsSummary(visible.length, S.totalAssignments);

  const compact = S.viewMode === "compact";

  visible.forEach((job) => {
    const levelDisplay =
      Array.isArray(job.signalsSpecificLevels) && job.signalsSpecificLevels.length
        ? job.signalsSpecificLevels.join(" / ")
        : Array.isArray(job.signalsLevels) && job.signalsLevels.length
        ? job.signalsLevels.join(" / ")
        : "";

    if (compact) {
      const rawMessageLink = typeof job.messageLink === "string" ? job.messageLink.trim() : "";
      const messageLink = rawMessageLink.startsWith("t.me/") ? `https://${rawMessageLink}` : rawMessageLink;

      const row = document.createElement(messageLink ? "a" : "div");
      row.className = "bg-background rounded-2xl p-5 shadow-md border border-border hover:shadow-lg transition-shadow block";
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

      const header = document.createElement("div");
      header.className = "flex items-start justify-between mb-3";

      const left = document.createElement("div");
      left.className = "min-w-0";

      const title = document.createElement("h3");
      title.className = "font-semibold text-lg truncate";
      title.textContent = job.academicDisplayText || "Tuition Assignment";

      left.appendChild(title);

      if (levelDisplay) {
        const subtitle = document.createElement("p");
        subtitle.className = "text-sm text-muted-foreground truncate";
        subtitle.textContent = levelDisplay;
        left.appendChild(subtitle);
      }

      const right = document.createElement("div");
      right.className = "flex flex-wrap items-center gap-2";

      const tier = String(job?.freshnessTier || "green")
        .trim()
        .toLowerCase();
      const tierPill = document.createElement("span");
      tierPill.className = "inline-flex items-center rounded-full bg-black/5 px-3 py-1 text-xs font-semibold text-black";
      tierPill.textContent =
        tier === "green" ? "Likely open" : tier === "yellow" ? "Probably open" : tier === "orange" ? "Uncertain" : "Likely closed";
      tierPill.title = "Open-likelihood inferred from recent agency reposts/updates.";
      if (tier === "yellow") tierPill.className += " bg-yellow-100 text-yellow-700 dark:bg-yellow-950 dark:text-yellow-300";
      else if (tier === "orange") tierPill.className += " bg-orange-100 text-orange-700 dark:bg-orange-950 dark:text-orange-300";
      else if (tier === "red") tierPill.className += " bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300";
      else tierPill.className += " bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300";
      right.appendChild(tierPill);

      if (hasMatchForMe(job)) {
        const matchPill = document.createElement("span");
        matchPill.className =
          "inline-flex items-center rounded-full bg-black/5 px-3 py-1 text-xs font-semibold text-black bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300";
        matchPill.textContent = "Matches you";
        const details = matchDetails(job);
        matchPill.title =
          details && details.length ? `Matches your saved profile preferences: ${details.join(", ")}` : "Matches your saved profile preferences.";
        right.appendChild(matchPill);
      }

      header.appendChild(left);
      header.appendChild(right);

      const meta = document.createElement("div");
      meta.className = "grid grid-cols-2 gap-3 text-sm";

      function metaItem(iconClass, text, labelClass = "", wrapperClass = "") {
        const wrap = document.createElement("div");
        wrap.className = `flex items-center gap-2 ${wrapperClass}`.trim();

        const icon = document.createElement("i");
        icon.className = `${iconClass} h-4 w-4 text-muted-foreground`;

        const label = document.createElement("span");
        label.className = labelClass;
        label.textContent = text;

        wrap.appendChild(icon);
        wrap.appendChild(label);
        return wrap;
      }

      // show postal (explicit or estimated), distance, and time availability in compact mode
      const postal = job.postalCode || job.postalEstimated || job.location || "Unknown";
      meta.appendChild(metaItem("fa-solid fa-location-dot", postal));
      const rateLabel = (() => {
        if (typeof job.rateMin === "number" && Number.isFinite(job.rateMin) && typeof job.rateMax === "number" && Number.isFinite(job.rateMax)) {
          if (Math.abs(job.rateMin - job.rateMax) < 1e-9) return `$${job.rateMin}/hr`;
          return `$${job.rateMin}-$${job.rateMax}/hr`;
        }
        if (typeof job.rateMin === "number" && Number.isFinite(job.rateMin)) return `$${job.rateMin}/hr`;
        const raw = String(job.rateRawText || "").trim();
        return raw || "N/A";
      })();
      meta.appendChild(metaItem("fa-solid fa-dollar-sign", rateLabel, "font-medium text-blue-600"));

      if (typeof job.distanceKm === "number" && Number.isFinite(job.distanceKm)) {
        meta.appendChild(metaItem("fa-solid fa-ruler-combined", formatDistanceKm(job.distanceKm, job.postalCoordsEstimated)));
      }

      const timingNotes = [
        ...(Array.isArray(job.scheduleNotes) ? job.scheduleNotes.filter(Boolean) : []),
        ...(Array.isArray(job.timeNotes) ? job.timeNotes.filter(Boolean) : []),
      ];
      if (timingNotes.length) {
        meta.appendChild(metaItem("fa-solid fa-clock", timingNotes.join(" · "), "", "col-span-2"));
      }

      row.appendChild(header);
      row.appendChild(meta);
      E.grid.appendChild(row);
      return;
    }

    const card = document.createElement("div");
    card.className = "job-card rounded-2xl p-6 relative flex flex-col justify-between h-full";

    const top = document.createElement("div");

    const header = document.createElement("div");
    header.className = "flex justify-between items-start mb-4";

    const badge = document.createElement("span");
    badge.className = "badge bg-gradient-to-r from-blue-600 to-indigo-600 text-white";
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
    if (tier === "yellow") tierPill.className = "badge bg-yellow-500/20 text-yellow-200";
    else if (tier === "orange") tierPill.className = "badge bg-orange-500/20 text-orange-200";
    else if (tier === "red") tierPill.className = "badge bg-red-500/20 text-red-200";
    else tierPill.className = "badge bg-emerald-500/20 text-emerald-200";

    const chips = document.createElement("div");
    chips.className = "flex flex-wrap items-center justify-center gap-2 px-2";
    chips.appendChild(tierPill);

    if (hasMatchForMe(job)) {
      const matchPill = document.createElement("span");
      matchPill.className = "badge bg-purple-500/20 text-purple-200";
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
    subtitle.className = "text-muted-foreground font-bold uppercase text-xs tracking-wider mb-6";
    subtitle.textContent = levelDisplay;

    const details = document.createElement("div");
    details.className = compact ? "space-y-2 mb-4" : "space-y-3 mb-8";

    function addDetail(iconClass, text) {
      const row = document.createElement("div");
      row.className = "flex items-center gap-3";

      const iconWrap = document.createElement("div");
      iconWrap.className = "w-8 h-8 rounded-full bg-muted/60 text-muted-foreground flex items-center justify-center text-xs";

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

    if (!compact && job.rateBreakdown && typeof job.rateBreakdown === "object") {
      const entries = Object.entries(job.rateBreakdown)
        .slice(0, 3)
        .map(([k, v]) => {
          const currency =
            v && typeof v.currency === "string" && v.currency.trim()
              ? v.currency.trim()
              : v && typeof v.original_text === "string" && v.original_text.includes("$")
              ? "$"
              : "";
          const minVal = v && Number.isFinite(Number(v.min)) ? Number(v.min) : null;
          const maxVal = v && Number.isFinite(Number(v.max)) ? Number(v.max) : null;
          const rateText = (() => {
            if (minVal != null && maxVal != null) {
              if (Math.abs(minVal - maxVal) < 1e-9) return `${currency}${minVal}`;
              return `${currency}${minVal}-${currency}${maxVal}`;
            }
            if (minVal != null) return `${currency}${minVal}`;
            if (maxVal != null) return `${currency}${maxVal}`;
            return "";
          })();
          return `${k}${rateText ? ` ${rateText}${v && v.unit ? `/${v.unit}` : ""}` : ""}`;
        })
        .filter(Boolean);
      if (entries.length) addDetail("fa-solid fa-money-bill", `Rates: ${entries.join(" · ")}`);
    }

    const lastUpdated = job.bumpedAt || job.postedAt;
    if (lastUpdated) {
      const rel = formatRelativeTime(lastUpdated);
      const d = formatShortDate(lastUpdated);
      addDetail("fa-solid fa-rotate", rel ? `Last updated ${rel}${d ? ` (${d})` : ""}` : d ? `Last updated ${d}` : "Last updated");
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
      "flex-1 py-3 border border-border rounded-lg font-bold uppercase tracking-wide transition text-center " +
      (messageLink ? "hover:bg-muted/60" : "opacity-40 cursor-not-allowed");
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
    E.grid.appendChild(card);
  });
}

function renderLoadError(message) {
  if (E.grid) E.grid.innerHTML = "";
  if (E.noResults) E.noResults.classList.add("hidden");
  if (E.loadErrorMessage) E.loadErrorMessage.textContent = message || "We couldn’t load assignments right now. Please try again.";
  if (E.loadError) E.loadError.classList.remove("hidden");
  if (E.countLabel) E.countLabel.innerText = "0";
  setResultsSummary(0, 0);
  if (E.loadMoreBtn) E.loadMoreBtn.classList.add("hidden");
  if (E.facetHint) E.facetHint.classList.add("hidden");
}

function hideLoadError() {
  if (E.loadError) E.loadError.classList.add("hidden");
}

// --- 4. FILTER LOGIC ---

export {
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
  setViewMode,
  updateViewToggleUI,
  setResultsSummary,
  mapAssignmentRow,
};

// Backwards-compatible globals for inline handlers or legacy bundles
try {
  if (typeof window !== "undefined") {
    window.renderSubjectTray = renderSubjectTray;
    window.renderSkeleton = renderSkeleton;
  }
} catch (e) {
  // ignore
}
