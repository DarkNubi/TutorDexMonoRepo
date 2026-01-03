// Website-level enums for dropdowns (levels + specific levels).
// Subjects lists are derived from the shared taxonomy v2 JSON.

export const LEVELS = [
  "Pre-School",
  "Primary",
  "Secondary",
  "IGCSE",
  "IB",
  "Junior College",
  "Diploma",
  "Degree",
  "Olympiads",
  "Independent Learner - Languages",
  "Independent Learner - Computing",
  "Independent Learner - Music",
  "Independent Learner - Others",
];

export const SPECIFIC_LEVELS = {
  "Pre-School": ["Nursery", "Kindergarten 1", "Kindergarten 2"],
  Primary: ["Primary 1", "Primary 2", "Primary 3", "Primary 4", "Primary 5", "Primary 6"],
  Secondary: ["Secondary 1", "Secondary 2", "Secondary 3", "Secondary 4", "Secondary 5"],
  IGCSE: ["Pre-IGCSE Grade 6", "Pre-IGCSE Grade 7", "Pre-IGCSE Grade 8", "IGCSE Grade 9", "IGCSE Grade 10"],
  IB: ["IB MYP Grade 6", "IB MYP Grade 7", "IB MYP Grade 8", "IB MYP Grade 9", "IB MYP Grade 10", "IB DP Year 1", "IB DP Year 2"],
  "Junior College": ["JC 1", "JC 2", "JC 3", "Private Candidate"],
  Diploma: ["Poly Year 1", "Poly Year 2", "Poly Year 3"],
  Olympiads: ["Primary School Olympiad", "Olympiads Secondary", "Olympiads JC"],
};

