export function openLogin() {
  // Provided by index.html (kept in plain JS so auth.js can bind to DOM IDs)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window as any).showAuth?.()
}

export function openSignup() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  ;(window as any).showSignUp?.()
}

export function goAssignments() {
  window.location.assign("assignments.html")
}

