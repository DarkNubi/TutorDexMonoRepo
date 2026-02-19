import { sanitizeNext, sanitizeNotice, waitForAuth } from "../auth.js";

function getParam(name) {
  try {
    const url = new URL(window.location.href);
    return url.searchParams.get(name);
  } catch {
    return null;
  }
}

function setParam(name, value) {
  try {
    const url = new URL(window.location.href);
    if (value == null || value === "") url.searchParams.delete(name);
    else url.searchParams.set(name, String(value));
    window.history.replaceState({}, "", url.toString());
  } catch {}
}

function $id(id) {
  return document.getElementById(id);
}

function setText(el, text) {
  if (!el) return;
  el.textContent = text || "";
}

function show(el) {
  if (!el) return;
  el.classList.remove("hidden");
}

function hide(el) {
  if (!el) return;
  el.classList.add("hidden");
}

function setBusy(container, busy) {
  if (!container) return;
  container.querySelectorAll("button, input, select, textarea").forEach((el) => {
    if (busy) el.setAttribute("disabled", "disabled");
    else el.removeAttribute("disabled");
  });
}

const NOTICE_COPY = Object.freeze({
  password_reset_success: "Password updated. Please sign in.",
  signed_out: "You have signed out.",
  session_expired: "Please sign in to continue.",
  password_reset_email_sent: "If an account exists for that email, you’ll receive a password reset link shortly.",
  password_reset_link_invalid: "This password reset link is invalid or has expired. Please request a new one.",
});

const SIGN_IN_ERROR_COPY = Object.freeze({
  invalid_email_or_password: "Invalid email or password.",
  invalid_email: "Enter a valid email address.",
  default: "Sign in failed. Please try again.",
});

const FORGOT_COPY = Object.freeze({
  success: "If an account exists for that email, you’ll receive a password reset link shortly.",
  invalid_email: "Enter a valid email address.",
  default: "Unable to send reset email right now. Please try again later.",
});

const PASSWORD_COPY = Object.freeze({
  tooShort: "Password must be at least 8 characters.",
  mismatch: "Passwords do not match.",
});

function normalizeMode(raw) {
  const m = String(raw || "").trim().toLowerCase();
  if (m === "login" || m === "signup" || m === "forgot") return m;
  return "login";
}

function redirectAfterEmailPasswordSignIn() {
  const dest = sanitizeNext(getParam("next"));
  if (dest && dest !== "index.html") window.location.replace(dest);
  else window.location.replace("assignments.html");
}

function redirectAfterEmailPasswordSignUp() {
  const dest = sanitizeNext(getParam("next"));
  if (dest && dest !== "index.html") window.location.replace(dest);
  else window.location.replace("profile.html");
}

function copyForSignInError(code) {
  if (code === "auth/user-not-found" || code === "auth/wrong-password") return SIGN_IN_ERROR_COPY.invalid_email_or_password;
  if (code === "auth/invalid-email") return SIGN_IN_ERROR_COPY.invalid_email;
  return SIGN_IN_ERROR_COPY.default;
}

function isGooglePopupFallbackCode(code) {
  return (
    code === "auth/popup-blocked" ||
    code === "auth/popup-closed-by-user" ||
    code === "auth/cancelled-popup-request" ||
    code === "auth/operation-not-supported-in-this-environment"
  );
}

function showOnlyView(viewId) {
  const ids = ["auth-view-login", "auth-view-signup", "auth-view-forgot", "auth-view-signed-in"];
  for (const id of ids) {
    const el = $id(id);
    if (!el) continue;
    el.classList.toggle("hidden", id !== viewId);
  }
}

function activeViewElForMode(mode) {
  if (mode === "signup") return $id("auth-view-signup");
  if (mode === "forgot") return $id("auth-view-forgot");
  return $id("auth-view-login");
}

function renderNoticeBanner() {
  const banner = $id("auth-notice");
  const text = $id("auth-notice-text");
  const noticeKey = sanitizeNotice(getParam("notice"));
  if (getParam("notice") && !noticeKey) setParam("notice", null);
  if (!noticeKey) {
    hide(banner);
    setText(text, "");
    return;
  }
  const copy = NOTICE_COPY[noticeKey] || "";
  if (!copy) {
    hide(banner);
    setText(text, "");
    return;
  }
  setText(text, copy);
  show(banner);
}

function clearNoticeFromUrl() {
  setParam("notice", null);
  renderNoticeBanner();
}

function setMode(mode) {
  const normalized = normalizeMode(mode);
  setParam("mode", normalized);
  clearNoticeFromUrl();
  showOnlyView(normalized === "signup" ? "auth-view-signup" : normalized === "forgot" ? "auth-view-forgot" : "auth-view-login");
}

function wireModeButtons() {
  const toSignup = $id("auth-to-signup");
  const toForgot = $id("auth-to-forgot");
  const toLogin = $id("auth-to-login");
  const forgotToLogin = $id("auth-forgot-to-login");

  if (toSignup) toSignup.addEventListener("click", () => setMode("signup"));
  if (toForgot) toForgot.addEventListener("click", () => setMode("forgot"));
  if (toLogin) toLogin.addEventListener("click", () => setMode("login"));
  if (forgotToLogin) forgotToLogin.addEventListener("click", () => setMode("login"));
}

function clearErrorsAndStatuses() {
  setText($id("auth-login-error"), "");
  setText($id("auth-signup-error"), "");
  setText($id("auth-forgot-error"), "");
  setText($id("auth-forgot-status"), "");
}

async function init() {
  const nextKey = sanitizeNext(getParam("next"));
  if (getParam("next") && !nextKey) setParam("next", null);
  renderNoticeBanner();
  wireModeButtons();

  const initialMode = normalizeMode(getParam("mode"));
  setParam("mode", initialMode);
  showOnlyView(initialMode === "signup" ? "auth-view-signup" : initialMode === "forgot" ? "auth-view-forgot" : "auth-view-login");

  const loginForm = $id("auth-login-form");
  const loginEmail = $id("auth-login-email");
  const loginPassword = $id("auth-login-password");
  const loginError = $id("auth-login-error");
  const loginGoogle = $id("auth-login-google");

  const signupForm = $id("auth-signup-form");
  const signupName = $id("auth-signup-name");
  const signupEmail = $id("auth-signup-email");
  const signupPassword = $id("auth-signup-password");
  const signupConfirm = $id("auth-signup-confirm");
  const signupError = $id("auth-signup-error");
  const signupGoogle = $id("auth-signup-google");

  const forgotForm = $id("auth-forgot-form");
  const forgotEmail = $id("auth-forgot-email");
  const forgotStatus = $id("auth-forgot-status");
  const forgotError = $id("auth-forgot-error");

  const signedInEmail = $id("auth-signed-in-email");
  const signedInContinue = $id("auth-signed-in-continue");
  const signedInSignOut = $id("auth-signed-in-signout");

  const auth = await waitForAuth();
  const googleProvider = new firebase.auth.GoogleAuthProvider();

  async function doGoogle(modeHint) {
    const view = activeViewElForMode(modeHint);
    setBusy(view, true);
    clearErrorsAndStatuses();
    try {
      await auth.signInWithPopup(googleProvider);
      if (modeHint === "signup") redirectAfterEmailPasswordSignUp();
      else redirectAfterEmailPasswordSignIn();
    } catch (err) {
      if (isGooglePopupFallbackCode(err?.code)) {
        await auth.signInWithRedirect(googleProvider);
        return;
      }
      const msg = copyForSignInError(err?.code);
      if (modeHint === "signup") setText(signupError, msg);
      else setText(loginError, msg);
    } finally {
      setBusy(view, false);
    }
  }

  async function handleRedirectResultIfAny() {
    try {
      const res = await auth.getRedirectResult();
      if (!res?.user) return false;
      const m = normalizeMode(getParam("mode"));
      if (m === "signup") redirectAfterEmailPasswordSignUp();
      else redirectAfterEmailPasswordSignIn();
      return true;
    } catch (err) {
      const m = normalizeMode(getParam("mode"));
      const msg = copyForSignInError(err?.code);
      if (m === "signup") setText(signupError, msg);
      else setText(loginError, msg);
      return false;
    }
  }

  const redirected = await handleRedirectResultIfAny();
  if (redirected) return;

  auth.onAuthStateChanged((user) => {
    clearErrorsAndStatuses();
    if (user) {
      showOnlyView("auth-view-signed-in");
      setText(signedInEmail, user?.email || "");
      return;
    }
    const m = normalizeMode(getParam("mode"));
    showOnlyView(m === "signup" ? "auth-view-signup" : m === "forgot" ? "auth-view-forgot" : "auth-view-login");
  });

  if (signedInContinue) {
    signedInContinue.addEventListener("click", () => {
      const dest = sanitizeNext(getParam("next"));
      if (dest && dest !== "index.html") window.location.replace(dest);
      else window.location.replace("assignments.html");
    });
  }

  if (signedInSignOut) {
    signedInSignOut.addEventListener("click", async () => {
      const view = $id("auth-view-signed-in");
      setBusy(view, true);
      try {
        await auth.signOut();
        window.location.replace("auth.html?mode=login&notice=signed_out");
      } finally {
        setBusy(view, false);
      }
    });
  }

  if (loginGoogle) loginGoogle.addEventListener("click", () => doGoogle("login"));
  if (signupGoogle) signupGoogle.addEventListener("click", () => doGoogle("signup"));

  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearNoticeFromUrl();
      setText(loginError, "");
      const email = String(loginEmail?.value || "").trim();
      const pass = String(loginPassword?.value || "");
      if (!email) {
        setText(loginError, SIGN_IN_ERROR_COPY.invalid_email);
        return;
      }
      const view = $id("auth-view-login");
      setBusy(view, true);
      try {
        await auth.signInWithEmailAndPassword(email, pass);
        redirectAfterEmailPasswordSignIn();
      } catch (err) {
        setText(loginError, copyForSignInError(err?.code));
      } finally {
        setBusy(view, false);
      }
    });
  }

  if (signupForm) {
    signupForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearNoticeFromUrl();
      setText(signupError, "");

      const email = String(signupEmail?.value || "").trim();
      const pass = String(signupPassword?.value || "");
      const confirm = String(signupConfirm?.value || "");

      if (pass.length < 8) {
        setText(signupError, PASSWORD_COPY.tooShort);
        return;
      }
      if (pass !== confirm) {
        setText(signupError, PASSWORD_COPY.mismatch);
        return;
      }

      const view = $id("auth-view-signup");
      setBusy(view, true);
      try {
        const cred = await auth.createUserWithEmailAndPassword(email, pass);
        const displayName = String(signupName?.value || "").trim();
        if (displayName && cred?.user?.updateProfile) {
          await cred.user.updateProfile({ displayName });
        }
        redirectAfterEmailPasswordSignUp();
      } catch (err) {
        if (err?.code === "auth/invalid-email") {
          setText(signupError, SIGN_IN_ERROR_COPY.invalid_email);
        } else if (err?.code === "auth/email-already-in-use") {
          setText(signupError, "An account already exists for that email.");
        } else {
          setText(signupError, "Sign up failed. Please try again.");
        }
      } finally {
        setBusy(view, false);
      }
    });
  }

  if (forgotForm) {
    forgotForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      clearNoticeFromUrl();
      setText(forgotError, "");
      setText(forgotStatus, "");

      const email = String(forgotEmail?.value || "").trim();
      if (!email) {
        setText(forgotError, FORGOT_COPY.invalid_email);
        return;
      }

      const view = $id("auth-view-forgot");
      setBusy(view, true);
      try {
        const url = `${window.location.origin}/reset-password.html`;
        await auth.sendPasswordResetEmail(email, { url });
        setText(forgotStatus, FORGOT_COPY.success);
      } catch (err) {
        if (err?.code === "auth/invalid-email") {
          setText(forgotError, FORGOT_COPY.invalid_email);
        } else if (err?.code === "auth/user-not-found") {
          setText(forgotStatus, FORGOT_COPY.success);
        } else {
          setText(forgotError, FORGOT_COPY.default);
        }
      } finally {
        setBusy(view, false);
      }
    });
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
