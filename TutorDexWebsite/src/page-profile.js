import "../subjectsData.js";
import { getCurrentUid, getCurrentUser, waitForAuth } from "../auth.js";
import { createTelegramLinkCode, getTutor, isBackendEnabled, trackEvent, upsertTutor } from "./backend.js";

const subjectsData = window.tutorDexSubjects || window.subjectsData || {};
const specificLevelsData = window.tutorDexSpecificLevels || {};

function getSubjectsKey(level) {
  if (level === "IGCSE" || level === "IB") return "IB/IGCSE";
  return level;
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
  const root = document.getElementById("subject-buttons");
  const searchEl = document.getElementById("subject-search");
  const subjectsKey = getSubjectsKey(level);

  if (!root) return;

  const q = String(searchEl?.value || "")
    .trim()
    .toLowerCase();

  const all = Array.isArray(subjectsData[subjectsKey]) ? subjectsData[subjectsKey] : [];
  const filtered = q ? all.filter((s) => String(s || "").toLowerCase().includes(q)) : all;

  root.innerHTML = "";

  if (!level) {
    const msg = document.createElement("span");
    msg.className = "text-gray-400 text-sm italic w-full text-center";
    msg.textContent = "Pick a level to see subjects…";
    root.appendChild(msg);
    return;
  }

  if (!filtered.length) {
    const msg = document.createElement("span");
    msg.className = "text-gray-400 text-sm italic w-full text-center";
    msg.textContent = q ? "No matching subjects." : "No subjects available for this level.";
    root.appendChild(msg);
    return;
  }

  for (const sub of filtered) {
    const label = String(sub || "").trim();
    if (!label) continue;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "select-btn rounded-full px-4 py-2 font-bold uppercase text-xs tracking-wide";
    btn.textContent = label;
    btn.addEventListener("click", () => {
      const lvl = String(document.getElementById("level-select")?.value || "").trim();
      if (!lvl) return;
      const spec = String(document.getElementById("specific-level-select")?.value || "").trim();
      addChipToTray({ level: lvl, specificLevel: spec, subject: label });
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

function addChipToTray({ level, specificLevel, subject }) {
  const tray = document.getElementById("subjects-tray");
  const emptyMsg = document.getElementById("empty-tray-msg");
  if (!tray) return;

  const lvl = String(level || "").trim();
  const subj = String(subject || "").trim();
  const spec = String(specificLevel || "").trim();
  if (!lvl || !subj) return;

  if (emptyMsg) emptyMsg.style.display = "none";

  const chipId = `${lvl}-${spec || "any"}-${subj}`.replace(/\s+/g, "");
  if (document.getElementById(chipId)) return;

  const chip = document.createElement("div");
  chip.className = "tray-item";
  chip.id = chipId;
  chip.dataset.level = lvl;
  chip.dataset.specificLevel = spec;
  chip.dataset.subject = subj;

  const label = document.createElement("span");
  const levelTag = document.createElement("span");
  levelTag.className = "text-gray-400 font-normal mr-1";
  levelTag.textContent = lvl;
  label.appendChild(levelTag);
  label.appendChild(document.createTextNode(spec ? ` ${spec} - ${subj}` : ` ${subj}`));

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "hover:text-red-400 transition ml-1";
  removeBtn.setAttribute("aria-label", `Remove ${lvl}${spec ? ` ${spec}` : ""} ${subj}`);
  removeBtn.addEventListener("click", () => {
    chip.remove();
    _updateEmptyTrayState();
  });

  const removeIcon = document.createElement("i");
  removeIcon.className = "fa-solid fa-times";
  removeBtn.appendChild(removeIcon);

  chip.appendChild(label);
  chip.appendChild(removeBtn);
  tray.appendChild(chip);
  if (emptyMsg) emptyMsg.style.display = "none";
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

function mapTutorKind(label) {
  const v = String(label || "")
    .trim()
    .toLowerCase();
  if (!v) return "";
  if (v.startsWith("part-time")) return "PT";
  if (v.startsWith("full-time")) return "FT";
  if (v.includes("ex-moe")) return "Ex-MOE";
  if (v.includes("moe")) return "MOE";
  return label;
}

function reverseTutorKind(kind) {
  const k = String(kind || "")
    .trim()
    .toUpperCase();
  if (k === "PT") return "Part-Time";
  if (k === "FT") return "Full-Time";
  if (k === "MOE") return "MOE- trained Tutors";
  if (k === "EX-MOE" || k === "EX-MOE TEACHER") return "Ex-MOE Teacher";
  return "";
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
  const subjects = uniq(chips.map((c) => c.dataset.subject).filter(Boolean));
  const levels = uniq(chips.map((c) => c.dataset.level).filter(Boolean));
  const subjectPairs = chips
    .map((c) => ({
      level: String(c.dataset.level || "").trim(),
      specific_level: String(c.dataset.specificLevel || "").trim(),
      subject: String(c.dataset.subject || "").trim(),
    }))
    .filter((x) => x.level && x.subject);
  return { subjects, levels, subjectPairs };
}

function setStatus(message, kind = "info") {
  const el = document.getElementById("profile-save-status");
  if (!el) return;
  el.textContent = message || "";
  el.className = "text-sm font-medium mb-4";
  if (kind === "error") el.className += " text-red-600";
  else if (kind === "success") el.className += " text-green-600";
  else el.className += " text-gray-600";
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

  const tutorTypeLabel = document.getElementById("input-tutor-type")?.value || "";
  const tutorKinds = uniq([mapTutorKind(tutorTypeLabel)].filter(Boolean));

  const assignmentTypes = uniq(getActiveButtonLabels("assignment-type-options"));
  const teachingLocations = uniq(getActiveButtonLabels("teaching-locations"));
  const learningModes = getLearningModesFromLocations();
  const { subjects, levels, subjectPairs } = parseTrayPreferences();
  const contactPhone = String(document.getElementById("contact-phone")?.value || "").trim();
  const contactTelegramHandle = String(document.getElementById("contact-telegram-handle")?.value || "").trim();

  const postalInput = document.getElementById("tutor-postal-code");
  const postalNormalized = normalizeSgPostalCode(postalInput?.value);
  if (postalNormalized === null) {
    setStatus("Postal code must be 6 digits (or leave it blank).", "error");
    return;
  }

  setStatus("Saving profile...", "info");
  await upsertTutor(uid, {
    subjects,
    levels,
    subject_pairs: subjectPairs,
    assignment_types: assignmentTypes,
    tutor_kinds: tutorKinds,
    learning_modes: learningModes,
    teaching_locations: teachingLocations,
    postal_code: postalNormalized,
    contact_phone: contactPhone || null,
    contact_telegram_handle: contactTelegramHandle || null,
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

function activateTutorTypeButton(label) {
  if (!label) return;
  const buttons = Array.from(document.querySelectorAll("section button.select-btn"));
  for (const btn of buttons) {
    const title = btn.querySelector(".brand-font")?.innerText?.trim();
    if (title === label) {
      selectSingle(btn, "tutor-type");
      return;
    }
  }
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
    telegramStatusEl.className = profile.chat_id ? "text-sm font-semibold text-green-700" : "text-sm font-semibold text-gray-700";
  }

  if (Array.isArray(profile.assignment_types)) {
    const container = document.getElementById("assignment-type-options");
    activateButtonsByText(container, profile.assignment_types);
  }

  if (Array.isArray(profile.tutor_kinds) && profile.tutor_kinds.length) {
    const label = reverseTutorKind(profile.tutor_kinds[0]);
    if (label) activateTutorTypeButton(label);
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

  if (Array.isArray(profile.subject_pairs) && profile.subject_pairs.length) {
    const tray = document.getElementById("subjects-tray");
    if (tray) {
      tray.querySelectorAll(".tray-item").forEach((el) => el.remove());
      for (const pair of profile.subject_pairs) {
        addChipToTray({
          level: pair?.level,
          specificLevel: pair?.specific_level,
          subject: pair?.subject,
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
        setStatus(`Save failed: ${err?.message || err}`, "error");
      }
    });
  }

  const linkBtn = document.getElementById("generate-link-code");
  const linkDisplay = document.getElementById("link-code-display");
  const linkBox = document.getElementById("link-code-box");
  const copyLinkBtn = document.getElementById("copy-link-command");
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
        setStatus("Link code generated. Send it to the DM bot.", "success");
      } catch (err) {
        console.error(err);
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
      });
    }

    await loadProfile();
    _updateEmptyTrayState();
  } catch (err) {
    console.error(err);
  }
}

initProfilePage();
