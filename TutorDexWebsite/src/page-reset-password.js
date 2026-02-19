import { waitForAuth } from "../auth.js";

function $id(id) {
  return document.getElementById(id);
}

function setText(el, text) {
  if (!el) return;
  el.textContent = text || "";
}

function setBusy(form, busy) {
  if (!form) return;
  form.querySelectorAll("button, input, select, textarea").forEach((el) => {
    if (busy) el.setAttribute("disabled", "disabled");
    else el.removeAttribute("disabled");
  });
}

function getParam(name) {
  try {
    const url = new URL(window.location.href);
    return url.searchParams.get(name);
  } catch {
    return null;
  }
}

const COPY = Object.freeze({
  invalid: "This password reset link is invalid or has expired. Please request a new one.",
  tooShort: "Password must be at least 8 characters.",
  mismatch: "Passwords do not match.",
});

async function init() {
  const status = $id("reset-status");
  const form = $id("reset-form");
  const passEl = $id("reset-password");
  const confirmEl = $id("reset-confirm");
  const requestNew = $id("reset-request-new");

  const mode = String(getParam("mode") || "");
  const oobCode = String(getParam("oobCode") || "");

  function invalidateAndDisable() {
    setText(status, COPY.invalid);
    if (requestNew) requestNew.href = "auth.html?mode=forgot&notice=password_reset_link_invalid";
    if (form) {
      form.classList.add("hidden");
      setBusy(form, true);
    }
  }

  if (mode !== "resetPassword" || !oobCode) {
    invalidateAndDisable();
    return;
  }

  const auth = await waitForAuth();
  if (requestNew) requestNew.href = "auth.html?mode=forgot";

  try {
    await auth.verifyPasswordResetCode(oobCode);
    setText(status, "");
  } catch {
    invalidateAndDisable();
    return;
  }

  if (!form) return;
  form.classList.remove("hidden");
  setBusy(form, false);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    setText(status, "");

    const pass = String(passEl?.value || "");
    const confirm = String(confirmEl?.value || "");

    if (pass.length < 8) {
      setText(status, COPY.tooShort);
      return;
    }
    if (pass !== confirm) {
      setText(status, COPY.mismatch);
      return;
    }

    setBusy(form, true);
    try {
      await auth.confirmPasswordReset(oobCode, pass);
      window.location.replace("auth.html?mode=login&notice=password_reset_success");
    } catch (err) {
      if (err?.code === "auth/invalid-action-code" || err?.code === "auth/expired-action-code") {
        invalidateAndDisable();
        return;
      }
      setText(status, "Unable to reset password right now. Please try again.");
    } finally {
      setBusy(form, false);
    }
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

