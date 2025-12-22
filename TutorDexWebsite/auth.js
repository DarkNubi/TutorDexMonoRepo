/* global firebase */

let _authInstance = null;
let _authReadyResolve = null;
const _authReady = new Promise((resolve) => {
  _authReadyResolve = resolve;
});

let _authStateReadyResolve = null;
const _authStateReady = new Promise((resolve) => {
  _authStateReadyResolve = resolve;
});

export async function waitForAuth() {
  if (_authInstance) return _authInstance;
  return _authReady;
}

export async function waitForAuthState() {
  await waitForAuth();
  return _authStateReady;
}

export async function getCurrentUser() {
  const auth = await waitForAuth();
  await waitForAuthState();
  return auth?.currentUser || null;
}

export async function getCurrentUid() {
  const user = await getCurrentUser();
  return user?.uid || null;
}

export async function getIdToken(forceRefresh = false) {
  const user = await getCurrentUser();
  if (!user?.getIdToken) return null;
  try {
    return await user.getIdToken(forceRefresh);
  } catch {
    return null;
  }
}

function isTruthy(value) {
  return value === true || value === "true";
}

function showAuthInitError(message) {
  const el = document.getElementById("auth-init-error");
  if (!el) return;
  if (message) el.textContent = String(message);
  el.classList.remove("hidden");
}

function hideAuthInitError() {
  const el = document.getElementById("auth-init-error");
  if (!el) return;
  el.classList.add("hidden");
}

function getHelpfulAuthHint(code) {
  switch (code) {
    case "auth/configuration-not-found":
      return "Firebase Auth is misconfigured for this site/project. Ensure the Firebase project has a Web app (Project settings -> Your apps) and that you're running/deployed against the correct project.";
    case "auth/unauthorized-domain":
      return "This domain isn't authorized for Firebase Auth. Add it in Firebase Console -> Authentication -> Settings -> Authorized domains.";
    case "auth/operation-not-allowed":
      return "This sign-in method isn't enabled. Enable it in Firebase Console -> Authentication -> Sign-in method.";
    default:
      return "";
  }
}

function getParam(name) {
  try {
    const url = new URL(window.location.href);
    return url.searchParams.get(name);
  } catch {
    return null;
  }
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

function setBusy(form, busy) {
  if (!form) return;
  form.querySelectorAll("button, input, select, textarea").forEach((el) => {
    if (busy) el.setAttribute("disabled", "disabled");
    else el.removeAttribute("disabled");
  });
}

function initAuth() {
  if (!window.firebase || !firebase.auth) {
    console.error("Firebase SDK not loaded. Ensure /__/firebase/* scripts are included before auth.js");
    showAuthInitError("Firebase SDK not loaded. If you're running locally, use `npm run serve:firebase`.");
    return;
  }

  const app = firebase.apps?.[0] || null;
  const options = app?.options || {};
  const hasApiKey = Boolean(options.apiKey);
  const hasProjectId = Boolean(options.projectId);

  if (!hasApiKey || !hasProjectId) {
    console.error("Firebase initialized with incomplete config. /__/firebase/init.js likely missing Web App config.", {
      projectId: options.projectId,
      authDomain: options.authDomain,
      apiKeyPresent: hasApiKey,
    });
    showAuthInitError(
      "Firebase config incomplete (missing apiKey/projectId). This often causes `auth/configuration-not-found`. In Firebase Console -> Project settings -> Your apps, add a Web app and redeploy (or re-run the Hosting emulator)."
    );
    return;
  }

  console.info("Firebase app ready", { projectId: options.projectId, authDomain: options.authDomain });

  const auth = firebase.auth();
  _authInstance = auth;
  if (_authReadyResolve) _authReadyResolve(auth);
  const googleProvider = new firebase.auth.GoogleAuthProvider();

  const pageRequireAuth = isTruthy(document.body?.dataset?.requireAuth);
  const pageName = window.location.pathname.split("/").pop() || "index.html";
  const isIndexPage = pageName === "index.html";

  const signInStateEls = document.querySelectorAll("[data-auth-state]");
  const userEmailEls = document.querySelectorAll("[data-auth-user-email]");

  const loginForm = document.getElementById("login-form");
  const loginEmail = document.getElementById("login-email");
  const loginPassword = document.getElementById("login-password");
  const loginError = document.getElementById("login-error");
  const loginGoogleBtn = document.getElementById("login-google");

  const signupForm = document.getElementById("signup-form");
  const signupName = document.getElementById("signup-name");
  const signupEmail = document.getElementById("signup-email");
  const signupPassword = document.getElementById("signup-password");
  const signupConfirm = document.getElementById("signup-confirm");
  const signupError = document.getElementById("signup-error");
  const signupGoogleBtn = document.getElementById("signup-google");

  const logoutBtns = document.querySelectorAll("[data-auth-logout]");

  function closeIndexModalsIfAny() {
    if (!isIndexPage) return;
    try {
      if (typeof window.hideAllModals === "function") window.hideAllModals();
    } catch {}
  }

  function redirectAfterAuth() {
    const next = getParam("next");
    if (next && next !== "index.html") {
      window.location.replace(next);
      return;
    }
    window.location.replace("assignments.html");
  }

  async function doGoogleSignIn() {
    try {
      setText(loginError, "");
      setText(signupError, "");
      await auth.signInWithPopup(googleProvider);
      closeIndexModalsIfAny();
    } catch (err) {
      const message = err?.message || "Google sign-in failed.";
      const hint = getHelpfulAuthHint(err?.code);
      setText(loginError, message);
      setText(signupError, message);
      console.error("Google sign-in failed", {
        code: err?.code,
        message: err?.message,
        customData: err?.customData,
      });
      if (hint) showAuthInitError(hint);
    }
  }

  function updateAuthUI(user) {
    signInStateEls.forEach((el) => {
      const showWhen = el.getAttribute("data-auth-state");
      const shouldShow = showWhen === (user ? "signed-in" : "signed-out");
      el.classList.toggle("hidden", !shouldShow);
    });

    userEmailEls.forEach((el) => {
      setText(el, user?.email || "");
    });
  }

  auth.onAuthStateChanged((user) => {
    if (_authStateReadyResolve) {
      _authStateReadyResolve(user || null);
      _authStateReadyResolve = null;
    }

    updateAuthUI(user);

    if (!user && pageRequireAuth) {
      const dest = `index.html?next=${encodeURIComponent(window.location.pathname.split("/").pop() || "")}`;
      window.location.replace(dest);
    }

    if (user && isIndexPage) {
      closeIndexModalsIfAny();
      redirectAfterAuth();
    }
  });

  if (loginGoogleBtn) {
    loginGoogleBtn.addEventListener("click", (e) => {
      e.preventDefault();
      setText(loginError, "");
      doGoogleSignIn();
    });
  }

  if (signupGoogleBtn) {
    signupGoogleBtn.addEventListener("click", (e) => {
      e.preventDefault();
      setText(signupError, "");
      doGoogleSignIn();
    });
  }

  if (loginForm) {
    loginForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      setText(loginError, "");
      setBusy(loginForm, true);
      try {
        await auth.signInWithEmailAndPassword(loginEmail.value.trim(), loginPassword.value);
        const next = getParam("next");
        if (next) window.location.assign(next);
        else window.location.assign("assignments.html");
      } catch (err) {
        setText(loginError, err?.message || "Login failed.");
        console.error("Email/password sign-in failed", {
          code: err?.code,
          message: err?.message,
          customData: err?.customData,
        });
        const hint = getHelpfulAuthHint(err?.code);
        if (hint) showAuthInitError(hint);
      } finally {
        setBusy(loginForm, false);
      }
    });
  }

  if (signupForm) {
    signupForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      setText(signupError, "");

      const email = signupEmail.value.trim();
      const pass = signupPassword.value;
      const confirm = signupConfirm.value;

      if (pass.length < 8) {
        setText(signupError, "Password must be at least 8 characters long.");
        return;
      }
      if (pass !== confirm) {
        setText(signupError, "Passwords do not match.");
        return;
      }

      setBusy(signupForm, true);
      try {
        const cred = await auth.createUserWithEmailAndPassword(email, pass);
        const displayName = signupName?.value?.trim();
        if (displayName && cred?.user?.updateProfile) {
          await cred.user.updateProfile({ displayName });
        }
        const next = getParam("next");
        if (next) window.location.assign(next);
        else window.location.assign("profile.html");
      } catch (err) {
        setText(signupError, err?.message || "Sign up failed.");
        console.error("Email/password sign-up failed", {
          code: err?.code,
          message: err?.message,
          customData: err?.customData,
        });
        const hint = getHelpfulAuthHint(err?.code);
        if (hint) showAuthInitError(hint);
      } finally {
        setBusy(signupForm, false);
      }
    });
  }

  logoutBtns.forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      try {
        await auth.signOut();
        window.location.assign("index.html");
      } catch (err) {
        console.error(err);
      }
    });
  });

  hideAuthInitError();
}

function startAuthBootstrap() {
  // Firebase Hosting provides init.js which initializes firebase for the site.
  // If scripts load slowly, retry a few times.
  let triesLeft = 30;
  const handle = window.setInterval(() => {
    if (window.firebase?.apps?.length) {
      window.clearInterval(handle);
      initAuth();
      return;
    }
    triesLeft -= 1;
    if (triesLeft <= 0) {
      window.clearInterval(handle);
      showAuthInitError(
        "Firebase init did not complete. If you're running locally, use `npm run serve:firebase` (Hosting emulator serves `__/firebase/init.js`). If deployed, confirm Firebase Hosting is serving `__/firebase/init.js` and you're on the correct Firebase project."
      );
      console.error("Firebase init did not complete. Check Firebase Hosting init scripts and project configuration.");
    }
  }, 100);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", startAuthBootstrap);
} else {
  startAuthBootstrap();
}
