import ast
import re
from dataclasses import dataclass
from typing import Any, Dict, List


_ASSIGN_RE = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.+?)\s*$", re.MULTILINE | re.DOTALL)


def _extract_assignment_block(text: str, name: str) -> str:
    # Find "NAME = <python literal>" where literal spans until the next all-caps assignment or EOF.
    pat = re.compile(rf"^\s*{re.escape(name)}\s*=\s*", re.MULTILINE)
    m = pat.search(text)
    if not m:
        raise ValueError(f"Missing {name} assignment")
    start = m.end()

    # Look for next top-level assignment header.
    next_m = re.search(r"^\s*[A-Z_][A-Z0-9_]*\s*=\s*", text[start:], re.MULTILINE)
    end = start + next_m.start() if next_m else len(text)
    return text[start:end].strip()


def parse_python_enums(text: str) -> Dict[str, Any]:
    levels_src = _extract_assignment_block(text, "LEVELS")
    specific_src = _extract_assignment_block(text, "SPECIFIC_LEVELS")
    subjects_src = _extract_assignment_block(text, "SUBJECTS")

    levels = ast.literal_eval(levels_src)
    specific = ast.literal_eval(specific_src)
    subjects = ast.literal_eval(subjects_src)

    if not isinstance(levels, list):
        raise ValueError("LEVELS must be a list")
    if not isinstance(specific, dict):
        raise ValueError("SPECIFIC_LEVELS must be a dict")
    if not isinstance(subjects, dict):
        raise ValueError("SUBJECTS must be a dict")

    return {"LEVELS": levels, "SPECIFIC_LEVELS": specific, "SUBJECTS": subjects}


@dataclass(frozen=True)
class CanonEnums:
    levels: List[str]
    specific_levels: Dict[str, List[str]]
    subjects: Dict[str, List[str]]

    @property
    def all_subjects(self) -> set[str]:
        s: set[str] = set()
        for _lvl, subs in self.subjects.items():
            for sub in subs or []:
                if isinstance(sub, str):
                    s.add(sub)
        return s


def load_canon_enums_from_text(text: str) -> CanonEnums:
    parsed = parse_python_enums(text)
    return CanonEnums(
        levels=[str(x) for x in parsed["LEVELS"]],
        specific_levels={str(k): [str(x) for x in (v or [])] for k, v in parsed["SPECIFIC_LEVELS"].items()},
        subjects={str(k): [str(x) for x in (v or [])] for k, v in parsed["SUBJECTS"].items()},
    )

