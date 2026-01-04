# TutorDex Website

## Firebase Hosting

This site is a static multi-page site in `TutorDexWebsite/` (`index.html`, `assignments.html`, `profile.html`), built with Vite for cache-busted assets.

### One-time setup

1. Create a Firebase project (Firebase Console).
2. Install the Firebase CLI:
   - `npm i -g firebase-tools`
3. Authenticate:
   - `firebase login`
4. Set the project id:
   - Edit `TutorDexWebsite/.firebaserc` and replace `REPLACE_WITH_YOUR_FIREBASE_PROJECT_ID`, or run `firebase use --add` from `TutorDexWebsite/`.

### Local preview

From `TutorDexWebsite/`:
- `npm i`
- `npm run serve:firebase`

`vite dev` does not serve Firebase Hosting auto-init endpoints (`/__/firebase/init.js`), so use the Hosting emulator for auth flows.

### Deploy

From `TutorDexWebsite/`:
- `npm i`
- `firebase deploy --only hosting`

`TutorDexWebsite/firebase.json` runs `npm run build` automatically on deploy (predeploy hook), producing `dist/` with hashed assets for safe long-term caching.

### GitHub Actions (optional)

This repo includes `.github/workflows/firebase-hosting.yml` to deploy on pushes to `main` and create preview deploys for pull requests (works for both monorepo `TutorDexWebsite/` and a standalone website repo).

Required GitHub repo secrets:
- `FIREBASE_SERVICE_ACCOUNT`: JSON for a Firebase service account with Hosting deploy permissions
- `VITE_BACKEND_URL` (required)
Optional GitHub repo variable:
- `VITE_DM_BOT_HANDLE`: e.g. `@TutorDexSniperBot` (displayed on the Profile page)

Required GitHub repo variable:
- `FIREBASE_PROJECT_ID`: your Firebase project id (set as a repo variable; does not need to be secret)

Note: The `VITE_*` values are embedded into the static website at build time. If you treat your backend URL as public (typical), you can store it as a repo variable instead of a secret.

Workflow behavior:
- `push` to `main`: deploys to the `live` channel
- `pull_request`: deploys to a preview channel named `pr-<number>` (expires in 7 days)

## Firebase Authentication

This site uses Firebase Auth via Firebase Hosting auto-init (`/__ /firebase/init.js`) and supports:
- Email/password sign up + sign in (no email verification)
- Google sign-in (popup)

### One-time Firebase Console setup

Firebase Console → Build → Authentication → Sign-in method:
- Enable **Email/Password**
- Enable **Google**

Firebase Console → Build → Authentication → Settings → Authorized domains:
- Ensure your Hosting domain(s) are listed (usually automatic for `*.web.app` / `*.firebaseapp.com`).

### If you see `auth/configuration-not-found`

This usually means Firebase Auth can't find valid project configuration for the API key being used.
Common causes:
- You haven't created a **Web app** in Firebase Console (so `/__/firebase/init.js` initializes with incomplete config).
- You're running the Hosting emulator / deploying against the **wrong Firebase project** (check `TutorDexWebsite/.firebaserc` and `firebase use`).
- Firebase Auth isn't set up for the project yet (enable providers under Authentication → Sign-in method).

## Backend (required)

This website is backend-only for data. Configure:
- `VITE_BACKEND_URL`: e.g. `http://127.0.0.1:8000`

To receive DMs, tutors must link their Telegram chat id (Profile page generates a short code; send `/link <code>` to the DM bot; see `TutorDexBackend/telegram_link_bot.py`).
