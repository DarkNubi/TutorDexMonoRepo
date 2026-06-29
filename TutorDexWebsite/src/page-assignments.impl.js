import { initAssignmentsPage } from "./page-assignments.logic.js";

let didInit = false;

function startAssignmentsPage() {
  if (didInit) return;
  didInit = true;
  initAssignmentsPage();
}

if (document.readyState === "complete") {
  startAssignmentsPage();
} else {
  window.addEventListener("load", startAssignmentsPage, { once: true });
}
