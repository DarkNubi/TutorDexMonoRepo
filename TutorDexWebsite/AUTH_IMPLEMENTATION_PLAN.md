# TutorDexWebsite Auth Implementation Plan (Firebase Auth + Firebase Hosting) — Zero Ambiguity

This document is a complete implementation spec. A developer should be able to implement the full auth system (login, sign-up, forgot password, reset password, Google sign-in with robust fallback) using only this plan and the existing repo.

---

## 0) Scope, Non-Goals, and Tech Constraints

### In scope

- Email/password sign-in
- Email/password sign-up
- Google sign-in
  - Prefer popup
  - Fall back to redirect when popup is blocked/unsupported
- Forgot password (send reset email)
- Reset password completion (from email action link)
- Protected-page redirect for pages with `data-require-auth="true"`

### Out of scope (explicit)

- SSO beyond Google
- 2FA
- Custom backend auth (Firebase Auth remains the identity provider)

### Must-follow constraints from this repo

- Firebase Hosting static multi-page site built via Vite (outputs `TutorDexWebsite/dist/`).
- Firebase auto-init is used (`/__/firebase/init.js`).
- Firebase compat SDK is used and must remain (unless you explicitly migrate later):
  - `/__/firebase/10.14.1/firebase-app-compat.js`
  - `/__/firebase/10.14.1/firebase-auth-compat.js`
- Existing auth bootstrap is in `TutorDexWebsite/auth.js` and is shared across pages.

---

## 1) Canonical Pages and Entry Points

### Pages that must exist after implementation

- `index.html` (existing): landing page (keep existing auth modal)
- `assignments.html` (existing)
- `profile.html` (existing; has `data-require-auth="true"` already)
- `auth.html` (new): canonical full-page auth surface (login/signup/forgot)
- `reset-password.html` (new): canonical full-page reset completion surface

### Canonical auth URLs

- Login: `auth.html?mode=login`
- Sign up: `auth.html?mode=signup`
- Forgot password: `auth.html?mode=forgot`

### Canonical reset completion URL

- `reset-password.html` (this is where Firebase reset emails must land)

---

## 2) URL Parameters — Exact Contract

### `auth.html`

- `mode` (string, optional)
  - Allowed: `login`, `signup`, `forgot`
  - Default: `login` if missing/invalid
- `next` (string, optional)
  - Semantics: a same-site file name to redirect to after successful login/sign-up
  - MUST be sanitized by `sanitizeNext()` (see Section 3)
- `notice` (string, optional)
  - Semantics: a UI banner key; non-navigational
  - MUST be sanitized by `sanitizeNotice()` (see Section 3)

### `reset-password.html` (from Firebase email action link)

- `mode` (string)
  - Must equal `resetPassword` to proceed
- `oobCode` (string)
  - Required; used with Firebase reset APIs
- Untrusted extras (must not be used for navigation):
  - `continueUrl`, `apiKey`, `lang`, anything else

---

## 3) Allowlists + Sanitizers — Source of Truth

### `NEXT_ALLOWLIST` (exact values)

Only these values are valid `next` destinations:

- `assignments.html`
- `profile.html`
- `index.html`

Explicitly NOT allowed as `next`:

- `auth.html`
- `reset-password.html`
- Any value containing `/`, `\\`, `..`, `:`, `//`, or whitespace

### `NOTICE_ALLOWLIST` (exact values)

Only these values are valid `notice` keys:

- `password_reset_success`
- `signed_out`
- `session_expired`
- `password_reset_email_sent`
- `password_reset_link_invalid`

### `sanitizeNext(raw)` — exact algorithm

1. Convert `raw` to string, trim it.
2. If empty → return `null`.
3. Reject if it contains any of:
   - `://`
   - starts with `//`
   - contains `\\`
   - contains `/`
   - contains `..`
   - contains whitespace
4. Return `raw` only if it exactly equals one of `NEXT_ALLOWLIST`, else return `null`.

### `sanitizeNotice(raw)` — exact algorithm

1. Convert `raw` to string, trim it.
2. If empty → return `null`.
3. Return `raw` only if it exactly equals one of `NOTICE_ALLOWLIST`, else return `null`.

---

## 4) Password Policy — Exact

Apply the same policy for sign-up and reset completion:

- Minimum: 8 characters (hard requirement)
- Confirm password must match exactly (hard requirement)
- UX hint (not enforced): suggest 12+ characters

Field-level validation messages (use verbatim):

- Too short: `Password must be at least 8 characters.`
- Mismatch: `Passwords do not match.`

---

## 5) User-Facing Copy — Exact “Contract”

To prevent account enumeration and regression, use these strings verbatim.

### Sign-in errors

- For `auth/user-not-found` and `auth/wrong-password`:
  - `Invalid email or password.`
- For `auth/invalid-email`:
  - `Enter a valid email address.`
- Default fallback:
  - `Sign in failed. Please try again.`

### Forgot password

- Always on submit success (regardless of whether the email exists):
  - `If an account exists for that email, you’ll receive a password reset link shortly.`
- For `auth/invalid-email`:
  - `Enter a valid email address.`
- Default fallback:
  - `Unable to send reset email right now. Please try again later.`

### Reset password completion

- Invalid or expired link:
  - `This password reset link is invalid or has expired. Please request a new one.`
- Success behavior:
  - Redirect to `auth.html?mode=login&notice=password_reset_success`

### `auth.html` notice banner copy (exact)

- `password_reset_success`: `Password updated. Please sign in.`
- `signed_out`: `You have signed out.`
- `session_expired`: `Please sign in to continue.`
- `password_reset_email_sent`: `If an account exists for that email, you’ll receive a password reset link shortly.`
- `password_reset_link_invalid`: `This password reset link is invalid or has expired. Please request a new one.`

---

## 6) Redirect Behavior — Exact (No Ambiguity)

### Protected pages (`data-require-auth="true"`)

When auth state resolves and the user is `null`:

- Compute:
  - `currentPage = window.location.pathname.split("/").pop() || "index.html"`
- Redirect with `replace` to:
  - `auth.html?mode=login&next=${encodeURIComponent(currentPage)}&notice=session_expired`

### After successful email/password sign-in

- `dest = sanitizeNext(getParam("next"))`
- If `dest` is non-null and `dest !== "index.html"` → `window.location.replace(dest)`
- Else → `window.location.replace("assignments.html")`

### After successful email/password sign-up

- `dest = sanitizeNext(getParam("next"))`
- If `dest` is non-null and `dest !== "index.html"` → `window.location.replace(dest)`
- Else → `window.location.replace("profile.html")`

### Visiting `auth.html` while already signed in

This must be deterministic and support “switch account”.

- If user is signed in on `auth.html`, DO NOT auto-redirect.
- Show a “Signed in” panel (Section 8) that includes:
  - Continue button:
    - If `dest = sanitizeNext(getParam("next"))` is non-null and not `index.html` → go to `dest`
    - Else → go to `assignments.html`
  - Sign out button:
    - `auth.signOut()` then redirect to `auth.html?mode=login&notice=signed_out`

---

## 7) Google Sign-In — Exact Strategy (Popup → Redirect Fallback)

### Primary attempt

- `auth.signInWithPopup(googleProvider)`

### Trigger set for redirect fallback (exact)

If popup throws an error with `err.code` equal to any of:

- `auth/popup-blocked`
- `auth/popup-closed-by-user`
- `auth/cancelled-popup-request`
- `auth/operation-not-supported-in-this-environment`

Then fall back to:

- `auth.signInWithRedirect(googleProvider)`

### Redirect result handling (canonical)

`auth.html` MUST call `auth.getRedirectResult()` on load after Firebase is ready.

Redirect result completion behavior:

- If a redirect result returns a signed-in user/credential:
  - If the current page `mode` is `signup` → apply “After successful sign-up” redirect rules (Section 6)
  - Else → apply “After successful sign-in” redirect rules (Section 6)
- If it throws:
  - Display a user-friendly message using the sign-in error mapping rules in Section 5 (never raw `err.message`).

Optional (allowed but not required):

- `index.html` may also call `getRedirectResult()` so users who start Google redirect from the landing modal complete cleanly even if they land back on index.

---

## 8) Page UI Specifications — Exact DOM Contract

### `auth.html` — required element IDs

Banner:

- `auth-notice` (banner container; hidden when no notice)
- `auth-notice-text` (banner text node)

Views (exactly one visible at a time):

- `auth-view-login`
- `auth-view-signup`
- `auth-view-forgot`
- `auth-view-signed-in`

Login view:

- Form: `auth-login-form`
- Email: `auth-login-email` (`type="email"`, `autocomplete="email"`)
- Password: `auth-login-password` (`type="password"`, `autocomplete="current-password"`)
- Error container: `auth-login-error` (`role="alert"`)
- Google button: `auth-login-google`
- Link/button to signup: `auth-to-signup`
- Link/button to forgot: `auth-to-forgot`

Signup view:

- Form: `auth-signup-form`
- Name (optional): `auth-signup-name` (`autocomplete="name"`)
- Email: `auth-signup-email`
- Password: `auth-signup-password` (`autocomplete="new-password"`)
- Confirm: `auth-signup-confirm` (`autocomplete="new-password"`)
- Error container: `auth-signup-error` (`role="alert"`)
- Google button: `auth-signup-google`
- Link/button to login: `auth-to-login`

Forgot view:

- Form: `auth-forgot-form`
- Email: `auth-forgot-email`
- Status container: `auth-forgot-status` (`role="status"`)
- Error container: `auth-forgot-error` (`role="alert"`)
- Link/button back to login: `auth-forgot-to-login`

Signed-in view:

- Email display: `auth-signed-in-email`
- Continue button: `auth-signed-in-continue`
- Sign out button: `auth-signed-in-signout`

Busy state requirement (applies to every form submit and Google click):

- Disable all controls within the active view while the request is in-flight.
- Re-enable only after:
  - navigation, or
  - the UI updates to a stable state (e.g., displaying an error or success status).

### `reset-password.html` — required element IDs

- Status container: `reset-status` (`role="alert"`)
- Form: `reset-form`
- New password: `reset-password`
- Confirm: `reset-confirm`
- Link/button to request a new reset email: `reset-request-new`

---

## 9) Implementation Tasks — File by File (Exact)

### 9.1 Create new pages

Create `TutorDexWebsite/auth.html`:

- Must include Firebase compat scripts at end of `<body>` in this order:
  - `/__/firebase/10.14.1/firebase-app-compat.js`
  - `/__/firebase/10.14.1/firebase-auth-compat.js`
  - `/__/firebase/init.js`
- Must include a module script:
  - `<script type="module" src="/src/page-auth.js"></script>`
- Must implement the DOM IDs in Section 8 exactly.

Create `TutorDexWebsite/reset-password.html`:

- Must include the same Firebase scripts at end of `<body>`.
- Must include a module script:
  - `<script type="module" src="/src/page-reset-password.js"></script>`
- Must implement the DOM IDs in Section 8 exactly.

### 9.2 Update Vite build inputs

Modify `TutorDexWebsite/vite.config.js`:

- Add two new HTML entrypoints to `build.rollupOptions.input`:
  - `auth: resolve(__dirname, "auth.html")`
  - `resetPassword: resolve(__dirname, "reset-password.html")`

### 9.3 Add binder scripts (no shared global assumptions)

Create `TutorDexWebsite/src/page-auth.js`:

Required responsibilities (all required):

- Parse `mode`, `next`, `notice` from `window.location.href`.
- Apply sanitizers:
  - `mode`: default to `login` if missing/invalid
  - `next`: only use `sanitizeNext()`
  - `notice`: only use `sanitizeNotice()`
- Render notice banner:
  - If `notice` is valid, show `auth-notice` and set `auth-notice-text` to the exact copy from Section 5.
  - Otherwise hide `auth-notice`.
- Initialize Firebase auth:
  - Wait for Firebase to be ready (use the existing patterns in `TutorDexWebsite/auth.js`).
- On load, call `auth.getRedirectResult()` (Section 7):
  - If result present, complete redirect per Section 7 + Section 6.
- Listen for auth state:
  - If signed in:
    - Show `auth-view-signed-in` only
    - Populate `auth-signed-in-email`
    - Wire Continue + Sign out per Section 6
  - If signed out:
    - Show the view for `mode` (`login`, `signup`, `forgot`)
- Wire login form submit:
  - Validate email presence
  - Attempt `signInWithEmailAndPassword`
  - On success, redirect per Section 6
  - On error, display mapped copy per Section 5 (never raw error message)
- Wire signup form submit:
  - Enforce password policy from Section 4 (including confirm match)
  - Attempt `createUserWithEmailAndPassword`
  - If name provided, set display name (existing behavior)
  - On success, redirect per Section 6
  - On error, show a user-friendly message (do not leak internal details)
- Wire forgot form submit:
  - Validate email format presence
  - Call `sendPasswordResetEmail(email, actionCodeSettings)`
  - ActionCodeSettings requirements:
    - `url` must point to `https://<current-origin>/reset-password.html` (no `continueUrl` by default)
  - Always show the generic success string from Section 5 on “success-like” completion (no enumeration)
- Wire Google buttons:
  - Attempt popup, fall back to redirect using the exact trigger set (Section 7)
  - While in-flight, enforce busy state

Create `TutorDexWebsite/src/page-reset-password.js`:

Required responsibilities (all required):

- Parse `mode` and `oobCode`.
- If `mode !== "resetPassword"` or missing `oobCode`:
  - Set `reset-status` to the invalid/expired copy from Section 5
  - Set `reset-request-new.href = "auth.html?mode=forgot&notice=password_reset_link_invalid"`
  - Do not call Firebase reset APIs
  - Do not attempt to submit the form (disable it or hide it)
- If valid:
  - Call `verifyPasswordResetCode(oobCode)`
  - If verify fails:
    - Show invalid/expired copy and disable/hide the form
  - If verify succeeds:
    - Enable the form
    - On submit:
      - enforce password policy (Section 4)
      - call `confirmPasswordReset(oobCode, newPassword)`
      - on success: `window.location.replace("auth.html?mode=login&notice=password_reset_success")`
      - on failure: show invalid/expired copy if code invalid, otherwise generic “try again” without leaking internal details

### 9.4 Update shared auth bootstrap

Modify `TutorDexWebsite/auth.js`:

Required changes:

- Protected-page redirect destination MUST become `auth.html` (Section 6).
- `sanitizeNext()` MUST exactly implement Section 3.
- Add `sanitizeNotice()` exactly per Section 3.
- Ensure `auth.js` does not require `index.html` modal IDs to exist on pages that do not have them.

### 9.5 Update navigation links to use canonical auth pages

Modify `TutorDexWebsite/assignments.html`:

- Any logged-out “Sign In” links must point to:
  - `auth.html?mode=login&next=assignments.html`

Modify `TutorDexWebsite/profile.html`:

- Any logged-out “Sign In” links must point to:
  - `auth.html?mode=login&next=profile.html`

Optional but recommended:

- Add a visible fallback link on `index.html` to:
  - `auth.html?mode=login`

---

## 10) Firebase Console Configuration — Exact Checklist

1. Authentication → Sign-in method
   - Email/Password: Enabled
   - Google: Enabled
2. Authentication → Settings → Authorized domains
   - Ensure:
     - `<project>.web.app`
     - `<project>.firebaseapp.com`
     - any custom domains used for staging/prod
3. Authentication → Templates
   - Password reset template must direct users to your deployed domain and ultimately load `reset-password.html`.
4. Repeat configuration checks for both staging and production domains.

---

## 11) QA — Exact Test Plan

### Local testing (required)

Must be run via Firebase Hosting emulator because `vite dev` does not serve `/__/firebase/init.js`:

- From `TutorDexWebsite/`: `npm run serve:firebase`

### Manual test cases (must all pass)

Sign in:

- Success:
  - open `auth.html?mode=login&next=profile.html`
  - sign in → must land on `profile.html`
- Wrong credentials:
  - must show exactly `Invalid email or password.`
- Invalid email:
  - must show exactly `Enter a valid email address.`

Sign up:

- Password < 8:
  - must show exactly `Password must be at least 8 characters.`
- Confirm mismatch:
  - must show exactly `Passwords do not match.`
- Success:
  - open `auth.html?mode=signup`
  - sign up → must land on `profile.html`

Forgot password:

- Submit any email:
  - must show exactly `If an account exists for that email, you’ll receive a password reset link shortly.`
- Invalid email:
  - must show exactly `Enter a valid email address.`

Reset password completion:

- Valid link:
  - must allow setting a new password
  - must redirect to `auth.html?mode=login&notice=password_reset_success`
  - must show banner `Password updated. Please sign in.`
- Invalid/expired link:
  - must show exactly `This password reset link is invalid or has expired. Please request a new one.`
  - must include a working `reset-request-new` link to forgot password mode

Google sign-in:

- Popup success: completes and redirects correctly
- Popup blocked path:
  - must fall back to redirect
  - `auth.html` must process `getRedirectResult()` and redirect correctly (no stuck state)

Protected page redirect:

- Visit `profile.html` logged out:
  - must redirect to `auth.html?mode=login&next=profile.html&notice=session_expired`
  - after login, must return to `profile.html`

### Automated tests (required, minimal)

Add unit tests that assert exact behavior of:

- `sanitizeNext()`
- `sanitizeNotice()`

These tests must include:

- valid allowed values
- invalid values (including open redirect attempts)

---

## 12) Deployment, Verification, and Rollback — Exact

### Staging (must be done before production)

- Build staging: `npm run build:staging`
- Deploy staging hosting target

Verify on staging:

- Direct navigation + hard refresh:
  - `https://<staging-domain>/auth.html`
  - `https://<staging-domain>/reset-password.html`
- Trigger forgot password and open email link in a new tab:
  - must land on staging `reset-password.html` and complete successfully
- Confirm Firebase Auth authorized domains include the staging domain.

### Production

- Build prod: `npm run build:prod`
- Deploy prod hosting target

Verify on production:

- Repeat staging verification checklist.

Rollback (explicit):

- If reset links or auth pages are broken in production:
  - Roll back Firebase Hosting to the last known good release/channel.
  - Fix, verify in staging, redeploy.

