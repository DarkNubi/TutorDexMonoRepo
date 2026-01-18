import { getCurrentUid, getCurrentUser, waitForAuth } from "../auth.js";
import { createTelegramLinkCode, getRecentMatchCounts, getTutor, isBackendEnabled, trackEvent, upsertTutor } from "./backend.js";
import { reportError, setUserContext, clearUserContext, addBreadcrumb } from "./errorReporter.js";
import { SPECIFIC_LEVELS } from "./academicEnums.js";
import { canonicalSubjectsForLevel, labelForCanonicalCode } from "./taxonomy/subjectsTaxonomyV2.js";
import { canonicalizePair } from "./lib/filterUtils.js";

const specificLevelsData = SPECIFIC_LEVELS || {};
const DM_BOT_HANDLE = String(import.meta.env?.VITE_DM_BOT_HANDLE ?? "@TutorDexSniperBot").trim() || "@TutorDexSniperBot";

// DOM cache helper
const _elCache_pf = new Map();
function $idpf(id) {
  if (!_elCache_pf.has(id)) _elCache_pf.set(id, document.getElementById(id));
  return _elCache_pf.get(id);
}

function _dmBotUsername() {
  const h = String(DM_BOT_HANDLE || "").trim();
  if (!h) return "TutorDexSniperBot";
  return h.startsWith("@") ? h.slice(1) : h;
}

function _dmBotLinkUrl({ code } = {}) {
  const user = _dmBotUsername();
  if (!user) return "";
  const c = String(code || "").trim();
  if (!c) return `https://t.me/${encodeURIComponent(user)}`;
  // Deep link uses /start payload; backend bot treats it like /link <code>.
  return `https://t.me/${encodeURIComponent(user)}?start=${encodeURIComponent(`link_${c}`)}`;
}

function _setDmBotLinks({ code } = {}) {
  const handle = DM_BOT_HANDLE.startsWith("@") ? DM_BOT_HANDLE : `@${DM_BOT_HANDLE}`;
  const href = _dmBotLinkUrl({ code });
  const a1 = document.getElementById("dm-bot-link");
  const a2 = document.getElementById("dm-bot-link-2");
  const open = document.getElementById("open-dm-bot");
  for (const a of [a1, a2]) {
    if (!a) continue;
    a.textContent = handle;
    a.href = _dmBotLinkUrl();
  }
  if (open) {
    open.textContent = `Open ${handle}`;
    open.href = href || _dmBotLinkUrl();
    open.style.pointerEvents = href ? "auto" : "none";
    open.style.opacity = href ? "1" : "0.6";
  }
}

function selectSingle(btn, inputId) {
  const container = btn.parentElement;
  const buttons = container.getElementsByClassName("select-btn");
  for (const b of buttons) {
    b.classList.remove("active");
  }
  btn.classList.add("active");
  document.getElementById(`input-${inputId}`).value = btn.querySelector(".brand-font").innerText;
}

function toggleBtn(btn) {
  btn.classList.toggle("active");
}

function updateSpecificLevels() {
  const level = document.getElementById("level-select").value;
  const specificSelect = document.getElementById("specific-level-select");
  const options = specificLevelsData[level] || [];

  specificSelect.innerHTML = '<option value="" selected>Select Specific Level (Optional)</option>';

  if (options.length === 0) {
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

function updateSubjects() {
  const level = document.getElementById("level-select").value;
  const specificLevel = String(document.getElementById("specific-level-select")?.value || "").trim();
  const root = document.getElementById("subject-buttons");
  const searchEl = document.getElementById("subject-search");

  if (!root) return;

  function hasChip(lvl, spec, subjectCode) {
    const tray = document.getElementById("subjects-tray");
    if (!tray) return false;
    return Array.from(tray.querySelectorAll(".tray-item")).some((el) => {
      const elLvl = String(el.dataset.level || "").trim();
      const elSpec = String(el.dataset.specificLevel || "").trim();
      const elCode = String(el.dataset.subjectCode || "").trim();
      return elLvl === lvl && elSpec === spec && elCode === subjectCode;
    });
  }

  function removeChip(lvl, spec, subjectCode) {
    const tray = document.getElementById("subjects-tray");
    if (!tray) return false;
    const chips = Array.from(tray.querySelectorAll(".tray-item"));
    let removed = false;
    for (const el of chips) {
      const elLvl = String(el.dataset.level || "").trim();
      const elSpec = String(el.dataset.specificLevel || "").trim();
      const elCode = String(el.dataset.subjectCode || "").trim();
      if (elLvl === lvl && elSpec === spec && elCode === subjectCode) {
        el.remove();
        removed = true;
      }
    }
    if (removed) _updateEmptyTrayState();
    return removed;
  }

  const q = String(searchEl?.value || "")
    .trim()
    .toLowerCase();

  const all = level ? canonicalSubjectsForLevel(level) || [] : [];
  const filtered = q
    ? all.filter((s) =>
        String(s?.label || "")
          .toLowerCase()
          .includes(q)
      )
    : all;

  root.innerHTML = "";

  if (!level) {
    const msg = document.createElement("span");
    msg.className = "text-muted-foreground text-sm italic w-full text-center";
    msg.textContent = "Pick a level to see subjects…";
    root.appendChild(msg);
    return;
  }

  if (!filtered.length) {
    const msg = document.createElement("span");
    msg.className = "text-muted-foreground text-sm italic w-full text-center";
    msg.textContent = q ? "No matching subjects." : "No subjects available for this level.";
    root.appendChild(msg);
    return;
  }

  for (const sub of filtered) {
    const code = String(sub?.code || "").trim();
    const label = String(sub?.label || "").trim();
    if (!code || !label) continue;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "select-btn rounded-full px-4 py-2 font-bold uppercase text-xs tracking-wide";
    btn.setAttribute("role", "option");
    btn.tabIndex = 0;
    btn.textContent = label;

    const isSelected = hasChip(level, specificLevel, code);
    btn.classList.toggle("active", isSelected);

    btn.addEventListener("click", () => {
      const lvl = String(document.getElementById("level-select")?.value || "").trim();
      if (!lvl) return;
      const spec = String(document.getElementById("specific-level-select")?.value || "").trim();
      const already = hasChip(lvl, spec, code);
      if (already) {
        removeChip(lvl, spec, code);
        btn.classList.remove("active");
        return;
      }
      addChipToTray({ level: lvl, specificLevel: spec, subjectCode: code, subjectLabel: label });
      btn.classList.add("active");
    });
    root.appendChild(btn);
  }
}

function _updateEmptyTrayState() {
  const tray = document.getElementById("subjects-tray");
  const emptyMsg = document.getElementById("empty-tray-msg");
  if (!tray || !emptyMsg) return;
  const hasChips = Boolean(tray.querySelector(".tray-item"));
  emptyMsg.style.display = hasChips ? "none" : "block";
}

function addChipToTray({ level, specificLevel, subjectCode, subjectLabel }) {
  const tray = document.getElementById("subjects-tray");
  const emptyMsg = document.getElementById("empty-tray-msg");
  if (!tray) return;

  const lvl = String(level || "").trim();
  const code = String(subjectCode || "").trim();
  const labelText = String(subjectLabel || "").trim() || labelForCanonicalCode(code) || code;
  const spec = String(specificLevel || "").trim();
  if (!lvl || !code) return;

  if (emptyMsg) emptyMsg.style.display = "none";

  const chipId = `${lvl}-${spec || "any"}-${code}`.replace(/\s+/g, "");
  if (document.getElementById(chipId)) return;

  const chip = document.createElement("div");
  chip.className = "tray-item";
  chip.id = chipId;
  chip.dataset.level = lvl;
  chip.dataset.specificLevel = spec;
  chip.dataset.subjectCode = code;
  chip.dataset.subjectLabel = labelText;
  // Accessibility: mark tray as a list and chips as listitems
  const trayEl = document.getElementById("subjects-tray");
  if (trayEl && !trayEl.hasAttribute("role")) trayEl.setAttribute("role", "list");
  chip.setAttribute("role", "listitem");
  chip.tabIndex = 0;

  const label = document.createElement("span");
  const levelTag = document.createElement("span");
  levelTag.className = "text-muted-foreground font-normal mr-1";
  levelTag.textContent = lvl;
  label.appendChild(levelTag);
  label.appendChild(document.createTextNode(spec ? ` ${spec} - ${labelText}` : ` ${labelText}`));

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "hover:text-red-400 transition ml-1";
  removeBtn.setAttribute("aria-label", `Remove ${lvl}${spec ? ` ${spec}` : ""} ${labelText}`);
  removeBtn.addEventListener("click", () => {
    chip.remove();
    _updateEmptyTrayState();
    updateSubjects();
  });

  const removeIcon = document.createElement("i");
  removeIcon.className = "fa-solid fa-times";
  removeBtn.appendChild(removeIcon);

  chip.appendChild(label);
  chip.appendChild(removeBtn);
  tray.appendChild(chip);
  if (emptyMsg) emptyMsg.style.display = "none";
  updateSubjects();
}

function toggleInfo(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle("hidden");
}

window.selectSingle = selectSingle;
window.toggleBtn = toggleBtn;
window.updateSpecificLevels = updateSpecificLevels;
window.updateSubjects = updateSubjects;
window.toggleInfo = toggleInfo;

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

function getActiveButtonLabels(containerId) {
  const el = document.getElementById(containerId);
  if (!el) return [];
  return Array.from(el.querySelectorAll("button.select-btn.active")).map((b) => b.innerText.trim());
}

function getLearningModesFromLocations() {
  const labels = getActiveButtonLabels("teaching-locations").map((s) => s.toLowerCase());
  const hasOnline = labels.includes("online");
  const hasPhysical = labels.some((s) => s !== "online");

  if (hasOnline && hasPhysical) return ["Online", "Face-to-Face", "Hybrid"];
  if (hasOnline) return ["Online"];
  if (hasPhysical) return ["Face-to-Face"];
  return [];
}

function parseTrayPreferences() {
  const chips = Array.from(document.querySelectorAll("#subjects-tray .tray-item"));
  const subjects = uniq(chips.map((c) => c.dataset.subjectCode).filter(Boolean));
  const levels = uniq(chips.map((c) => c.dataset.level).filter(Boolean));
  const specificStudentLevels = uniq(chips.map((c) => c.dataset.specificLevel).filter(Boolean));
  const subjectPairs = chips
    .map((c) => ({
      level: String(c.dataset.level || "").trim(),
      specific_level: String(c.dataset.specificLevel || "").trim(),
      subject: String(c.dataset.subjectCode || "").trim(),
    }))
    .filter((x) => x.level && x.subject);
  return { subjects, levels, specificStudentLevels, subjectPairs };
}

function setStatus(message, kind = "info") {
  const el = document.getElementById("profile-save-status");
  if (!el) return;
  el.textContent = message || "";
  el.className = "text-sm font-medium mb-4";
  if (kind === "error") el.className += " text-red-400";
  else if (kind === "success") el.className += " text-emerald-300";
  else el.className += " text-muted-foreground";
}

function normalizeSgPostalCode(value) {
  const raw = String(value || "").trim();
  const digits = raw.replace(/\D+/g, "");
  if (!digits) return "";
  if (digits.length !== 6) return null;
  return digits;
}

async function saveProfile() {
  if (!isBackendEnabled()) {
    setStatus("Backend not configured (VITE_BACKEND_URL missing). Profile not saved.", "error");
    return;
  }

  const uid = await getCurrentUid();
  if (!uid) {
    setStatus("You must be signed in to save your profile.", "error");
    return;
  }

  const teachingLocations = uniq(getActiveButtonLabels("teaching-locations"));
  const learningModes = getLearningModesFromLocations();
  const { subjects, levels, subjectPairs } = parseTrayPreferences();
  const contactPhone = String(document.getElementById("contact-phone")?.value || "").trim();

  const postalInput = document.getElementById("tutor-postal-code");
  const postalNormalized = normalizeSgPostalCode(postalInput?.value);
  if (postalNormalized === null) {
    setStatus("Postal code must be 6 digits (or leave it blank).", "error");
    return;
  }

  const dmRadiusEl = document.getElementById("dm-max-distance-km");
  let dmMaxDistanceKm = 5;
  if (dmRadiusEl) {
    const v = parseFloat(String(dmRadiusEl.value || "").trim());
    if (!Number.isNaN(v) && v > 0) {
      dmMaxDistanceKm = Math.max(0.5, Math.min(50, v));
    }
  }

  // Canonicalize subject pairs where necessary before saving
  const canonicalPairs = [];
  for (const p of subjectPairs || []) {
    const lvl = String(p.level || "").trim();
    let subj = String(p.subject || "").trim();
    const spec = String(p.specific_level || "").trim();
    // Heuristic: if it looks like a canonical code (contains a dot and uppercase), keep as-is
    const looksLikeCode = subj.includes(".") && subj === subj.toUpperCase();
    if (!looksLikeCode) {
      try {
        const first = canonicalizePair(lvl, subj);
        if (first) subj = first;
      } catch {
        // fallback: keep original
      }
    }
    if (lvl && subj) canonicalPairs.push({ level: lvl, specific_level: spec || "", subject: subj });
  }

  setStatus("Saving profile...", "info");
  await upsertTutor(uid, {
    subjects,
    levels,
    subject_pairs: canonicalPairs,
    learning_modes: learningModes,
    teaching_locations: teachingLocations,
    postal_code: postalNormalized,
    dm_max_distance_km: dmMaxDistanceKm,
    contact_phone: contactPhone || null,
  });
  try {
    await trackEvent({ eventType: "profile_save" });
  } catch {}
  setStatus("Profile saved.", "success");
}

function activateButtonsByText(containerEl, textList) {
  const want = new Set((textList || []).map((s) => String(s).trim()).filter(Boolean));
  if (!containerEl || want.size === 0) return;
  Array.from(containerEl.querySelectorAll("button.select-btn")).forEach((btn) => {
    const label = btn.innerText.trim();
    btn.classList.toggle("active", want.has(label));
  });
}

async function loadProfile() {
  if (!isBackendEnabled()) return;
  const uid = await getCurrentUid();
  if (!uid) return;

  const profile = await getTutor(uid);
  if (!profile) return;

  const telegramStatusEl = document.getElementById("telegram-link-status");
  if (telegramStatusEl) {
    telegramStatusEl.textContent = profile.chat_id ? "Linked to Telegram (DMs enabled)" : "Not linked to Telegram yet";
    telegramStatusEl.className = profile.chat_id ? "text-sm font-semibold text-emerald-300" : "text-sm font-semibold text-muted-foreground";
  }

  const locationsContainer = document.getElementById("teaching-locations");
  if (Array.isArray(profile.teaching_locations) && profile.teaching_locations.length) {
    activateButtonsByText(locationsContainer, profile.teaching_locations);
  } else if (Array.isArray(profile.learning_modes) && profile.learning_modes.some((m) => String(m).toLowerCase().includes("online"))) {
    activateButtonsByText(locationsContainer, ["Online"]);
  }

  const phoneEl = document.getElementById("contact-phone");
  if (phoneEl && typeof profile.contact_phone === "string") {
    phoneEl.value = profile.contact_phone;
  }

  const tgHandleEl = document.getElementById("contact-telegram-handle");
  if (tgHandleEl && typeof profile.contact_telegram_handle === "string") {
    tgHandleEl.value = profile.contact_telegram_handle;
  }

  const postalEl = document.getElementById("tutor-postal-code");
  if (postalEl && typeof profile.postal_code === "string") {
    postalEl.value = profile.postal_code;
  }

  const dmRadiusEl = document.getElementById("dm-max-distance-km");
  if (dmRadiusEl) {
    const v = profile?.dm_max_distance_km;
    dmRadiusEl.value = String(typeof v === "number" && Number.isFinite(v) ? v : 5);
  }

  if (Array.isArray(profile.subject_pairs) && profile.subject_pairs.length) {
    const tray = document.getElementById("subjects-tray");
    if (tray) {
      tray.querySelectorAll(".tray-item").forEach((el) => el.remove());
      for (const pair of profile.subject_pairs) {
        const lvl = String(pair?.level || "").trim();
        const rawSubject = String(pair?.subject || "").trim();
        if (!lvl || !rawSubject) continue;

        let subjectCode = rawSubject;
        const looksLikeCode = rawSubject.includes(".") && rawSubject === rawSubject.toUpperCase();
        if (!looksLikeCode) {
          const first = canonicalizePair(lvl, rawSubject);
          if (first) subjectCode = first;
        }
        const label = labelForCanonicalCode(subjectCode);
        addChipToTray({
          level: lvl,
          specificLevel: pair?.specific_level,
          subjectCode,
          subjectLabel: label && label !== subjectCode ? label : rawSubject,
        });
      }
      _updateEmptyTrayState();
    }
  }
}

async function initProfilePage() {
  const emailEl = document.getElementById("contact-email");
  if (emailEl) {
    emailEl.setAttribute("readonly", "readonly");
    emailEl.setAttribute("aria-readonly", "true");
  }

  const form = document.getElementById("profile-form");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await saveProfile();
      } catch (err) {
        console.error(err);
        reportError(err, { context: "saveProfile" });
        setStatus(`Save failed: ${err?.message || err}`, "error");
      }
    });
  }

  const linkBtn = document.getElementById("generate-link-code");
  const linkDisplay = document.getElementById("link-code-display");
  const linkBox = document.getElementById("link-code-box");
  const copyLinkBtn = document.getElementById("copy-link-command");
  _setDmBotLinks();
  if (linkBtn && linkDisplay) {
    linkBtn.addEventListener("click", async () => {
      try {
        if (!isBackendEnabled()) {
          setStatus("Backend not configured (VITE_BACKEND_URL missing).", "error");
          return;
        }
        const uid = await getCurrentUid();
        if (!uid) {
          setStatus("You must be signed in to generate a link code.", "error");
          return;
        }
        setStatus("Generating link code...", "info");
        const res = await createTelegramLinkCode(uid, { ttlSeconds: 600 });
        if (!res?.ok || !res?.code) {
          throw new Error(res?.error || "Failed to generate code.");
        }
        linkDisplay.textContent = res.code;
        if (linkBox) linkBox.classList.remove("hidden");
        _setDmBotLinks({ code: res.code });
        setStatus("Link code generated. Send it to the DM bot.", "success");
      } catch (err) {
        console.error(err);
        reportError(err, { context: "generateLinkCode" });
        setStatus(`Link code failed: ${err?.message || err}`, "error");
      }
    });
  }

  if (copyLinkBtn && linkDisplay) {
    copyLinkBtn.addEventListener("click", async () => {
      const code = String(linkDisplay.textContent || "").trim();
      if (!code) return;
      const cmd = `/link ${code}`;
      try {
        await navigator.clipboard.writeText(cmd);
        setStatus("Copied /link command.", "success");
      } catch {
        window.prompt("Copy this command:", cmd);
      }
    });
  }

  const matchBtn = document.getElementById("check-match-counts");
  const matchBox = document.getElementById("match-counts-box");
  const match7 = document.getElementById("match-count-7d");
  const match14 = document.getElementById("match-count-14d");
  const match30 = document.getElementById("match-count-30d");
  const matchNote = document.getElementById("match-counts-note");

  async function runMatchCount() {
    if (!isBackendEnabled()) {
      setStatus("Backend not configured (VITE_BACKEND_URL missing).", "error");
      return;
    }
    const uid = await getCurrentUid();
    if (!uid) {
      setStatus("You must be signed in to check matches.", "error");
      return;
    }

    const { subjects, levels, specificStudentLevels } = parseTrayPreferences();
    if (!subjects || subjects.length === 0) {
      setStatus("Select at least one subject to check matches.", "error");
      if (matchBox) matchBox.classList.remove("hidden");
      if (match7) match7.textContent = "-";
      if (match14) match14.textContent = "-";
      if (match30) match30.textContent = "-";
      if (matchNote) matchNote.textContent = " (select at least one subject)";
      return;
    }

    if (matchBtn) matchBtn.disabled = true;
    if (matchBox) matchBox.classList.remove("hidden");
    if (match7) match7.textContent = "...";
    if (match14) match14.textContent = "...";
    if (match30) match30.textContent = "...";
    if (matchNote) matchNote.textContent = " (all assignments, based on published_at)";

    try {
      const res = await getRecentMatchCounts({ levels, subjects, specificStudentLevels });
      const c = res?.counts || {};
      const windowField = String(res?.window_field || "").trim();
      if (windowField && matchNote) matchNote.textContent = ` (all assignments, based on ${windowField})`;
      if (match7) match7.textContent = String(c?.["7"] ?? "-");
      if (match14) match14.textContent = String(c?.["14"] ?? "-");
      if (match30) match30.textContent = String(c?.["30"] ?? "-");
    } catch (err) {
      console.error(err);
      reportError(err, { context: "getRecentMatchCounts", levels, subjects, specificStudentLevels });
      if (matchNote) matchNote.textContent = ` (${err?.message || err})`;
      if (match7) match7.textContent = "-";
      if (match14) match14.textContent = "-";
      if (match30) match30.textContent = "-";
    } finally {
      if (matchBtn) matchBtn.disabled = false;
    }
  }

  if (matchBtn) {
    matchBtn.addEventListener("click", () => void runMatchCount());
  }

  try {
    await waitForAuth();
    const user = await getCurrentUser();
    if (emailEl && user?.email) emailEl.value = user.email;

    const levelSelect = document.getElementById("level-select");
    if (levelSelect) {
      levelSelect.addEventListener("change", () => {
        const searchEl = document.getElementById("subject-search");
        if (searchEl) searchEl.value = "";
        updateSpecificLevels();
        updateSubjects();
      });
    }

    const specificSelect = document.getElementById("specific-level-select");
    if (specificSelect) {
      specificSelect.addEventListener("change", () => updateSubjects());
    }

    const subjectSearch = document.getElementById("subject-search");
    if (subjectSearch) {
      subjectSearch.addEventListener("input", () => updateSubjects());
    }

    const clearSearchBtn = document.getElementById("clear-subject-search");
    if (clearSearchBtn) {
      clearSearchBtn.addEventListener("click", () => {
        const searchEl = document.getElementById("subject-search");
        if (searchEl) searchEl.value = "";
        updateSubjects();
      });
    }

    const clearLevelSelBtn = document.getElementById("clear-level-selection");
    if (clearLevelSelBtn) {
      clearLevelSelBtn.addEventListener("click", () => {
        const levelEl = document.getElementById("level-select");
        const specEl = document.getElementById("specific-level-select");
        if (levelEl) levelEl.value = "";
        if (specEl) {
          specEl.innerHTML = '<option value="" selected>Select Specific Level (Optional)</option>';
          specEl.disabled = true;
        }
        const searchEl = document.getElementById("subject-search");
        if (searchEl) searchEl.value = "";
        updateSubjects();
      });
    }

    const clearAllBtn = document.getElementById("clear-tray");
    if (clearAllBtn) {
      clearAllBtn.addEventListener("click", () => {
        const tray = document.getElementById("subjects-tray");
        if (tray) tray.querySelectorAll(".tray-item").forEach((el) => el.remove());
        _updateEmptyTrayState();
        updateSubjects();
      });
    }

    const clearThisLevelBtn = document.getElementById("clear-this-level");
    if (clearThisLevelBtn) {
      clearThisLevelBtn.addEventListener("click", () => {
        const level = String(document.getElementById("level-select")?.value || "").trim();
        if (!level) return;
        const tray = document.getElementById("subjects-tray");
        if (!tray) return;
        tray.querySelectorAll(".tray-item").forEach((el) => {
          if (String(el.dataset.level || "").trim() === level) el.remove();
        });
        _updateEmptyTrayState();
        updateSubjects();
      });
    }

    await loadProfile();
    _updateEmptyTrayState();

    // Set user context for error reporting
    const uid = await getCurrentUid();
    if (uid) {
      setUserContext(uid);
      addBreadcrumb("Profile page loaded", { uid }, "navigation");
    }
  } catch (err) {
    console.error(err);
    reportError(err, { context: "initProfilePage" });
  }
}

initProfilePage();
