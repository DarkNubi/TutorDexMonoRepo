from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AgencyInfo:
    examples_key: str
    display_name: str


def normalize_chat_ref(value: str) -> str:
    """
    Normalize a chat/channel reference to `t.me/<username>` (lowercase).

    Accepts inputs like:
    - `t.me/ChannelUsername`
    - `https://t.me/ChannelUsername`
    - `@ChannelUsername`
    - `ChannelUsername`
    """
    v = (value or "").strip()
    if not v:
        return ""

    lv = v.lower()
    if lv.startswith("https://") or lv.startswith("http://"):
        v = v.rstrip("/").split("/")[-1]
        lv = v.lower()

    if lv.startswith("t.me/"):
        v = v.split("/", 1)[1]

    if v.startswith("@"):
        v = v[1:]

    return f"t.me/{v}".lower()


AGENCIES_BY_CHAT: dict[str, AgencyInfo] = {
    "t.me/tuitionassignmentssg": AgencyInfo(examples_key="mindflex", display_name="MindFlex"),
    "t.me/tuitionassignmentsttrsg": AgencyInfo(examples_key="ttrsg", display_name="TTR"),
    "t.me/tutoranywhr": AgencyInfo(examples_key="tutoranywhr", display_name="TutorAnywhr"),
    "t.me/elitetutorsg": AgencyInfo(examples_key="elitetutorsg", display_name="EliteTutor"),
    "t.me/ftassignments": AgencyInfo(examples_key="ftassignments", display_name="FamilyTutor"),
    "t.me/tutornowassignments": AgencyInfo(examples_key="tutornow", display_name="TutorNow"),
}


def get_agency_info(chat: str) -> Optional[AgencyInfo]:
    return AGENCIES_BY_CHAT.get(normalize_chat_ref(chat))


def get_agency_examples_key(chat: str) -> Optional[str]:
    info = get_agency_info(chat)
    return info.examples_key if info else None


def get_agency_display_name(chat: str, default: str = "Agency") -> str:
    info = get_agency_info(chat)
    return info.display_name if info else default

