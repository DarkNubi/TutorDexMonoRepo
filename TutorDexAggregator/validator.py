from copy import deepcopy
from typing import Dict, Any, List, Set
import re


# =========================
# CANONICAL DEFINITIONS
# =========================

LEVELS: List[str] = [
    "Pre-School", "Primary", "Secondary", "IGCSE", "IB",
    "Junior College", "Polytechnic", "Degree", "Olympiads",
    "Independent Learner - Languages", "Independent Learner - Computing",
    "Independent Learner - Music", "Independent Learner - Others"
]

SPECIFIC_LEVELS: Dict[str, List[str]] = {
    "Pre-School": ["Nursery", "Kindergarten 1", "Kindergarten 2"],
    "Primary": ["Primary 1", "Primary 2", "Primary 3", "Primary 4", "Primary 5", "Primary 6"],
    "Secondary": ["Secondary 1", "Secondary 2", "Secondary 3", "Secondary 4", "Secondary 5"],
    "IGCSE": ["Pre-IGCSE Grade 6", "Pre-IGCSE Grade 7", "Pre-IGCSE Grade 8", "IGCSE Grade 9", "IGCSE Grade 10"],
    "IB": ["IB MYP Grade 6", "IB MYP Grade 7", "IB MYP Grade 8", "IB MYP Grade 9", "IB MYP Grade 10", "IB DP Year 1", "IB DP Year 2"],
    "Junior College": ["JC 1", "JC 2", "JC 3", "Private Candidate"],
    "Polytechnic": ["Poly Year 1", "Poly Year 2", "Poly Year 3"],
    "Olympiads": ["Primary School Olympiad", "Olympiads Secondary", "Olympiads JC"]
}

SUBJECTS: Dict[str, List[str]] = {
    "Pre-School": [
        "English", "Chinese", "Maths", "Phonics",
        "Creative Writing", "Malay", "Tamil"
    ],
    "Primary": [
        "English", "Maths", "Science", "Chinese", "Higher Chinese",
        "Malay", "Higher Malay", "Tamil", "Higher Tamil",
        "Hindi", "Creative Writing", "Phonics",
        "Maths Olympiad", "Science Olympiad"
    ],
    "Secondary": [
        "English", "Chinese", "Higher Chinese", "Maths", "Science",
        "E Maths", "A Maths", "Physics", "Chemistry", "Biology",
        "Physics/Chem", "Bio/Physics", "Bio/Chem",
        "Geography", "History", "Literature",
        "Accounting (POA)", "Social Studies",
        "Geo/S.Studies", "Hist/S.Studies",
        "Malay", "Tamil", "Higher Malay", "Higher Tamil",
        "Hindi", "Creative Writing", "Music"
    ],
    "Junior College": [
        "General Paper", "Maths", "Physics", "Chemistry", "Biology",
        "Economics", "Accounting", "History", "Geography", "Literature",
        "Chinese", "Malay", "Tamil",
        "Chinese Studies", "Malay Studies", "Tamil Studies",
        "Knowledge & Inquiry", "Project Work", "Computing", "Art",
        "Theatre Studies & Drama", "Management of Business",
        "H3 Literature", "H3 Modern Physics", "H3 Chemistry",
        "H3 Proteomics", "H3 Maths", "H3 Geography", "H3 History",
        "H3 Economics", "Chinese Language and Literature",
        "Malay Language and Literature", "Tamil Language and Literature"
    ],
    "IB/IGCSE": [
        "English Language", "English Literature", "Chinese",
        "Mathematics", "Mathematical Studies",
        "Physics", "Chemistry", "Biology",
        "Business Management", "Economics", "Psychology",
        "Theory of Knowledge", "Extended Essay",
        "Theatre", "Environmental Systems", "Design Technology",
        "Geography", "History", "Malay", "Tamil",
        "Religious Knowledge", "Music", "Visual Arts",
        "Drama", "Art & Design", "IGTS"
    ],
    "Polytechnic": [
        "Business & Finance", "Computing & Technology",
        "Engineering & Applied Sciences",
        "Health & Life Sciences",
        "Arts, Humanities & Social Sciences"
    ],
    "Degree": [
        "Business & Finance", "Computing & Technology",
        "Engineering & Applied Sciences",
        "Health & Life Sciences",
        "Arts, Humanities & Social Sciences"
    ],
    "Olympiads": [
        "Primary School Math Olympiads", "Primary School Science Olympiads",
        "SMO (Junior)", "SJPO", "SJCHO", "SJBO",
        "SMO (Senior)", "SMO (Open)",
        "SPHO", "SCHO", "SBO", "APHO", "IPHO", "IOI", "NRC"
    ],
    "Independent Learner - Languages": [
        "Japanese", "Korean", "French", "German", "Spanish", "Russian",
        "Italian", "English", "Chinese", "Portuguese", "Arabic",
        "Vietnamese", "Thai", "Indonesian", "Tagalog", "Hindi", "Bengali"
    ],
    "Independent Learner - Computing": [
        "Python", "C++", "C#", "Java", "JavaScipt", "ASP", "PHP", "VB",
        "MSSQL", "Oracle", "Photoshop", "Illustrator", "Autocad",
        "GIS", "3D Design", "Flash", "Web Design", "Linux", "Macintosh",
        "Solaris", "Windows", "MS Office", "MySQL"
    ],
    "Independent Learner - Music": [
        "Music Theory", "Piano", "Guitar", "Drum", "Violin",
        "Flute", "Clarinet", "Trumpet", "Saxophone", "Dance", "Gu Zheng"
    ],
    "Independent Learner - Others": ["Others"]
}


# =========================
# PRECOMPUTED SETS
# =========================

ALL_SUBJECTS: Set[str] = set()
for subjects in SUBJECTS.values():
    ALL_SUBJECTS.update(subjects)

ALL_SPECIFIC_LEVELS: Set[str] = set()
for lvls in SPECIFIC_LEVELS.values():
    ALL_SPECIFIC_LEVELS.update(lvls)


# =========================
# ALIAS NORMALIZATION
# =========================

SUBJECT_ALIASES = {

    # ======================
    # MATHS
    # ======================
    "math": "Maths",
    "maths": "Maths",
    "mathematics": "Maths",
    "mathmatic": "Maths",
    "mathmatics": "Maths",

    "emath": "E Maths",
    "emaths": "E Maths",
    "e math": "E Maths",
    "e maths": "E Maths",
    "e-math": "E Maths",
    "e-maths": "E Maths",
    "elementary math": "E Maths",
    "elementary maths": "E Maths",

    "amath": "A Maths",
    "amaths": "A Maths",
    "a math": "A Maths",
    "a maths": "A Maths",
    "a-math": "A Maths",
    "a-maths": "A Maths",
    "additional math": "A Maths",
    "additional maths": "A Maths",

    "h3 math": "H3 Maths",
    "h3 maths": "H3 Maths",

    # ======================
    # SCIENCE (GENERAL)
    # ======================
    "science": "Science",
    "sci": "Science",
    "sci.": "Science",

    "physics": "Physics",
    "phy": "Physics",
    "phys": "Physics",
    "h3 physics": "H3 Modern Physics",

    "chemistry": "Chemistry",
    "chem": "Chemistry",
    "h3 chemistry": "H3 Chemistry",

    "biology": "Biology",
    "bio": "Biology",
    "h3 biology": "H3 Proteomics",

    "physics and chemistry": "Physics/Chem",
    "physics & chemistry": "Physics/Chem",
    "phy/chem": "Physics/Chem",
    "phys/chem": "Physics/Chem",

    "biology and chemistry": "Bio/Chem",
    "biology & chemistry": "Bio/Chem",
    "bio/chem": "Bio/Chem",
    "chem/bio": "Bio/Chem",

    "biology and physics": "Bio/Physics",
    "biology & physics": "Bio/Physics",
    "bio/phy": "Bio/Physics",

    # ======================
    # HUMANITIES
    # ======================
    "geography": "Geography",
    "geo": "Geography",
    "geog": "Geography",
    "h3 geography": "H3 Geography",

    "history": "History",
    "hist": "History",
    "h3 history": "H3 History",

    "literature": "Literature",
    "lit": "Literature",
    "english literature": "Literature",
    "h3 literature": "H3 Literature",

    "social studies": "Social Studies",
    "ss": "Social Studies",

    "accounting": "Accounting (POA)",
    "poa": "Accounting (POA)",
    "principles of accounts": "Accounting (POA)",

    # ======================
    # LANGUAGES
    # ======================
    "english": "English",
    "eng": "English",

    "chinese": "Chinese",
    "chi": "Chinese",

    "higher chinese": "Higher Chinese",
    "hcl": "Higher Chinese",

    "malay": "Malay",
    "higher malay": "Higher Malay",

    "tamil": "Tamil",
    "higher tamil": "Higher Tamil",

    "japanese": "Japanese",
    "korean": "Korean",
    "french": "French",
    "german": "German",
    "spanish": "Spanish",
    "russian": "Russian",
    "italian": "Italian",
    "arabic": "Arabic",
    "portuguese": "Portuguese",
    "thai": "Thai",
    "vietnamese": "Vietnamese",
    "indonesian": "Indonesian",
    "tagalog": "Tagalog",
    "hindi": "Hindi",
    "bengali": "Bengali",

    # ======================
    # JC / IB CORE
    # ======================
    "gp": "General Paper",
    "general paper": "General Paper",

    "economics": "Economics",
    "econs": "Economics",
    "h3 economics": "H3 Economics",

    "tok": "Theory of Knowledge",
    "theory of knowledge": "Theory of Knowledge",

    "ee": "Extended Essay",
    "extended essay": "Extended Essay",

    "project work": "Project Work",
    "pw": "Project Work",

    "knowledge and inquiry": "Knowledge & Inquiry",

    # ======================
    # COMPUTING / TECH
    # ======================
    "computing": "Computing",
    "computer science": "Computing",
    "cs": "Computing",
    "it": "Computing",

    "python": "Python",
    "java": "Java",
    "c++": "C++",
    "c#": "C#",
    "php": "PHP",
    "javascript": "JavaScipt",
    "js": "JavaScipt",

    "mysql": "MySQL",
    "mssql": "MSSQL",
    "oracle": "Oracle",

    "linux": "Linux",
    "windows": "Windows",
    "mac": "Macintosh",
    "macos": "Macintosh",

    # ======================
    # BUSINESS / MANAGEMENT
    # ======================
    "business": "Business Management",
    "business management": "Business Management",
    "management of business": "Management of Business",

    # ======================
    # ARTS
    # ======================
    "art": "Art",
    "visual arts": "Visual Arts",
    "art and design": "Art & Design",
    "theatre": "Theatre",
    "drama": "Drama",
    "theatre studies": "Theatre Studies & Drama",

    # ======================
    # MUSIC
    # ======================
    "music": "Music",
    "music theory": "Music Theory",
    "piano": "Piano",
    "violin": "Violin",
    "guitar": "Guitar",
    "drums": "Drum",
    "drum": "Drum",
    "flute": "Flute",
    "clarinet": "Clarinet",
    "saxophone": "Saxophone",
    "trumpet": "Trumpet",

    # ======================
    # OLYMPIADS
    # ======================
    "math olympiad": "Primary School Math Olympiads",
    "maths olympiad": "Primary School Math Olympiads",
    "science olympiad": "Primary School Science Olympiads",

    "smo": "SMO (Junior)",
    "smo jr": "SMO (Junior)",
    "smo senior": "SMO (Senior)",
    "smo open": "SMO (Open)",

    "sjpo": "SJPO",
    "sjcho": "SJCHO",
    "sjbo": "SJBO",
    "spho": "SPHO",
    "scho": "SCHO",
    "sbo": "SBO",
    "apho": "APHO",
    "ipho": "IPHO",
    "ioi": "IOI",
    "nrc": "NRC",

    # ======================
    # WRITING / LANGUAGE ARTS
    # ======================
    "creative writing": "Creative Writing",
    "cw": "Creative Writing",
    "phonics": "Phonics"
}


LEVEL_ALIASES = {
    "jc": "Junior College",
    "junior college": "Junior College",
    "j.c.": "Junior College",

    "pri": "Primary",
    "primary": "Primary",

    "sec": "Secondary",
    "secondary": "Secondary",

    "pre school": "Pre-School",
    "pre-school": "Pre-School",
    "preschool": "Pre-School",

    "ib": "IB",
    "international baccalaureate": "IB",
    "international bacc": "IB",

    "igcse": "IGCSE",

    "poly": "Polytechnic",
    "polytechnic": "Polytechnic",

    "uni": "Degree",
    "university": "Degree",

    "degree": "Degree",
    "diploma": "Polytechnic",

    "olympiad": "Olympiads",
    "olympiads": "Olympiads",
}

CANONICAL_SCIENCE_PAIRS = {
    frozenset(["Physics", "Chemistry"]): "Physics/Chem",
    frozenset(["Biology", "Chemistry"]): "Bio/Chem",
    frozenset(["Biology", "Physics"]): "Bio/Physics",
}


CANONICAL_HUMANITIES_PAIRS = {
    frozenset(["History", "Social Studies"]): "Hist/S.Studies",
    frozenset(["Geography", "Social Studies"]): "Geo/S.Studies",
}


STREAM_KEYWORDS = [
    "pure",
    "combined",
    "core",
    "elective"
]


def strip_stream_keywords(text: str) -> str:
    lowered = text.lower()
    for kw in STREAM_KEYWORDS:
        lowered = re.sub(rf"\b{kw}\b", "", lowered)
    return lowered.strip()


def normalize_science_or_humanities_pair(subject: str) -> str:
    if not subject or not isinstance(subject, str):
        return subject

    raw = subject.strip()

    # Remove stream qualifiers (tag logic only)
    stripped = strip_stream_keywords(raw)

    # Split on common separators (do NOT lowercase original text here)
    tokens = re.split(r"[\/&+\-]", stripped)
    tokens = [t.strip() for t in tokens if t.strip()]

    if len(tokens) != 2:
        return raw

    normalized_tokens = []
    for t in tokens:
        key = t.strip().lower()

        # 1) Alias match
        if key in SUBJECT_ALIASES:
            normalized_tokens.append(SUBJECT_ALIASES[key])
            continue

        # 2) Already canonical?
        if t in ALL_SUBJECTS:
            normalized_tokens.append(t)
            continue

        # Unknown token → abort safely
        return raw

    token_set = frozenset(normalized_tokens)

    if token_set in CANONICAL_SCIENCE_PAIRS:
        return CANONICAL_SCIENCE_PAIRS[token_set]

    if token_set in CANONICAL_HUMANITIES_PAIRS:
        return CANONICAL_HUMANITIES_PAIRS[token_set]

    return raw


def normalize_subject(subject: str) -> str:
    if not subject or not isinstance(subject, str):
        return subject

    raw = subject.strip()
    key = raw.lower()

    # 1. Direct alias match
    if key in SUBJECT_ALIASES:
        return SUBJECT_ALIASES[key]

    # 2. Pair normalization
    pair = normalize_science_or_humanities_pair(raw)
    if pair != raw:
        return pair

    # 3. Fallback
    return raw


def normalize_level(level: str) -> str:
    if not level or not isinstance(level, str):
        return level

    raw = level.strip()
    key = raw.lower()

    if key in LEVEL_ALIASES:
        return LEVEL_ALIASES[key]

    return raw


# =========================
# VALIDATOR
# =========================

def validate(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validates and conservatively cleans extracted assignment JSON.
    Never modifies authoritative fields.
    Returns a cleaned copy with confidence_flags added.
    """

    data = deepcopy(extracted)

    confidence_flags = {
        "lesson_schedule_ambiguous": False,
        "rate_ambiguous": False,
        "time_slots_ambiguous": False,
        "location_ambiguous": False
    }

    # -------------------------
    # LEVEL
    # -------------------------
    if data.get("level"):
        valid_levels: List[str] = []
        raw_levels = data["level"]
        if isinstance(raw_levels, str):
            raw_levels = [raw_levels]
        if isinstance(raw_levels, list):
            normalized_levels = [normalize_level(lvl) for lvl in raw_levels if isinstance(lvl, str) and lvl.strip()]
            valid_levels = [lvl for lvl in normalized_levels if lvl in LEVELS]
            data["level"] = valid_levels or None
        else:
            data["level"] = None
        if not valid_levels:
            confidence_flags["lesson_schedule_ambiguous"] = True

    # -------------------------
    # SPECIFIC STUDENT LEVEL
    # -------------------------
    if data.get("specific_student_level"):
        cleaned = [lvl for lvl in data["specific_student_level"] if lvl in ALL_SPECIFIC_LEVELS]
        data["specific_student_level"] = cleaned or None
        if not cleaned:
            confidence_flags["lesson_schedule_ambiguous"] = True

    # -------------------------
    # SUBJECTS
    # -------------------------
    cleaned_subjects: List[str] = []
    for s in data.get("subjects", []):
        s_norm = normalize_subject(s)
        if s_norm in ALL_SUBJECTS:
            cleaned_subjects.append(s_norm)

    data["subjects"] = cleaned_subjects

    # -------------------------
    # LESSON SCHEDULE SANITY
    # -------------------------
    sched = data.get("lesson_schedule", {})
    if sched:
        lpw = sched.get("lessons_per_week")
        hpl = sched.get("hours_per_lesson")
        total = sched.get("total_hours_per_week")

        if lpw is not None and lpw <= 0:
            sched["lessons_per_week"] = None
            confidence_flags["lesson_schedule_ambiguous"] = True

        if hpl is not None and hpl <= 0:
            sched["hours_per_lesson"] = None
            confidence_flags["lesson_schedule_ambiguous"] = True

        if lpw and hpl:
            computed = lpw * hpl
            if total is None:
                sched["total_hours_per_week"] = computed
            elif abs(total - computed) > 0.01:
                sched["total_hours_per_week"] = None
                confidence_flags["lesson_schedule_ambiguous"] = True

    # -------------------------
    # RATE SANITY
    # -------------------------
    rate = data.get("rate", {})
    if rate:
        rmin = rate.get("min")
        rmax = rate.get("max")

        if rmin is not None and rmin < 0:
            rate["min"] = None
            confidence_flags["rate_ambiguous"] = True

        if rmax is not None and rmax < 0:
            rate["max"] = None
            confidence_flags["rate_ambiguous"] = True

        if rmin is not None and rmax is not None and rmin > rmax:
            rate["min"], rate["max"] = rmax, rmin
            confidence_flags["rate_ambiguous"] = True

        if rate.get("rate_type") not in ("hourly", "per_session", "unknown", None):
            rate["rate_type"] = "unknown"
            confidence_flags["rate_ambiguous"] = True

    # -------------------------
    # TIME AVAILABILITY
    # -------------------------
    time_avail = data.get("time_availability", {})
    if time_avail:
        explicit = time_avail.get("explicit")
        estimated = time_avail.get("estimated")

        if explicit and estimated:
            confidence_flags["time_slots_ambiguous"] = True

    # -------------------------
    # FINALIZE
    # -------------------------
    data["confidence_flags"] = confidence_flags
    return data
