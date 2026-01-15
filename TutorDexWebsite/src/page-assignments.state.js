import { SPECIFIC_LEVELS } from "./academicEnums.js";

export const BUILD_TIME = typeof __BUILD_TIME__ !== "undefined" ? __BUILD_TIME__ : "";
export const specificLevelsData = SPECIFIC_LEVELS || {};
export const MAX_SUBJECT_CHIPS = 3;

export const E = {
  grid: document.getElementById("assignments-grid"),
  noResults: document.getElementById("no-results"),
  countLabel: document.getElementById("job-count"),
  resultsSummary: document.getElementById("results-summary"),
  loadError: document.getElementById("load-error"),
  loadErrorMessage: document.getElementById("load-error-message"),
  retryLoadBtn: document.getElementById("retry-load-assignments"),
  loadMoreBtn: document.getElementById("load-more"),
  facetHint: document.getElementById("facet-hint"),
};

export const S = {
  selectedSubjects: { general: [], canonical: [] },
  selectedSubjectOrder: [],

  allAssignments: [],
  totalAssignments: 0,
  nextCursorLastSeen: null,
  nextCursorId: null,
  nextCursorDistanceKm: null,
  lastFacets: null,
  activeLoadToken: 0,

  hasPostalCoords: null,
  didRestoreFiltersFromStorage: false,
  viewMode: "full",
  lastVisitCutoffMs: 0,
  myTutorProfile: null,
  currentUid: null,
};
