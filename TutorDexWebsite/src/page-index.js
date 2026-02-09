import "../auth.js";

function _byId(id) {
  return document.getElementById(id);
}

function _setAuthMode(mode) {
  const loginView = _byId("login-view");
  const signupView = _byId("signup-view");
  if (!loginView || !signupView) return;
  const isSignup = String(mode || "").toLowerCase() === "signup";
  loginView.classList.toggle("hidden", isSignup);
  signupView.classList.toggle("hidden", !isSignup);
}

function _showAuth(mode = "login") {
  const authView = _byId("auth-view");
  if (!authView) return;
  _setAuthMode(mode);
  authView.classList.remove("hidden");
  authView.setAttribute("aria-hidden", "false");
  try {
    document.body.style.overflow = "hidden";
  } catch {}
}

function _hideAuth() {
  const authView = _byId("auth-view");
  if (!authView) return;
  authView.classList.add("hidden");
  authView.setAttribute("aria-hidden", "true");
  try {
    document.body.style.overflow = "";
  } catch {}
}

function _initAuthModal() {
  // Expose globals used by the landing React page (see src/landing/actions.ts).
  window.showAuth = () => _showAuth("login");
  window.showSignUp = () => _showAuth("signup");
  window.hideAllModals = () => _hideAuth();

  document.querySelectorAll("[data-auth-close]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      _hideAuth();
    });
  });

  document.querySelectorAll("[data-auth-mode]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      _setAuthMode(el.getAttribute("data-auth-mode"));
    });
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") _hideAuth();
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", _initAuthModal);
} else {
  _initAuthModal();
}
