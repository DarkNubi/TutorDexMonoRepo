function getParam(name) {
  try {
    return new URL(window.location.href).searchParams.get(name);
  } catch {
    return null;
  }
}

export function isDebugEnabled() {
  try {
    if (getParam("debug") === "1") return true;
    return window.localStorage?.getItem("tutordex_debug") === "1";
  } catch {
    return false;
  }
}

export function setDebugEnabled(enabled) {
  try {
    window.localStorage?.setItem("tutordex_debug", enabled ? "1" : "0");
  } catch {}
}

export function redactToken(token, { head = 6, tail = 4 } = {}) {
  const s = String(token || "");
  if (!s) return "";
  if (s.length <= head + tail + 3) return `${s.slice(0, 2)}...(${s.length})`;
  return `${s.slice(0, head)}...${s.slice(-tail)} (${s.length})`;
}

export function debugLog(...args) {
  if (!isDebugEnabled()) return;
  // eslint-disable-next-line no-console
  console.log("[TutorDex debug]", ...args);
}

export function debugWarn(...args) {
  if (!isDebugEnabled()) return;
  // eslint-disable-next-line no-console
  console.warn("[TutorDex debug]", ...args);
}

export function debugError(...args) {
  if (!isDebugEnabled()) return;
  // eslint-disable-next-line no-console
  console.error("[TutorDex debug]", ...args);
}

