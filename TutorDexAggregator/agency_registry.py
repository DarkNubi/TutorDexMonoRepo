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
    "t.me/tutorsociety": AgencyInfo(examples_key="tutorsociety", display_name="Tutor Society"),
    "t.me/pthtassignments": AgencyInfo(examples_key="pthtassignments", display_name="Premium Tutors"),
    "t.me/eduaidtuition": AgencyInfo(examples_key="eduaidtuition", display_name="Edu Aid"),
    "t.me/nanyangtuitionjobs": AgencyInfo(examples_key="nanyangtuitionjobs", display_name="Nanyang Learning"),
    "t.me/tuition": AgencyInfo(examples_key="tuitionjobs_sg", display_name="Tuition Jobs SG"),
    "t.me/ministryoftuitionsg": AgencyInfo(examples_key="ministryoftuitionsg", display_name="Ministry of Tuition"),
    "t.me/championtutorsg": AgencyInfo(examples_key="championtutorsg", display_name="ChampionTutor"),
    "t.me/lumielessons": AgencyInfo(examples_key="lumielessons", display_name="Lumie Lessons"),
    "t.me/tutortrustjobs": AgencyInfo(examples_key="tutortrustjobs", display_name="TutorTrust"),
    "t.me/learntogethersg": AgencyInfo(examples_key="learntogethersg", display_name="LearnTogether"),
    "t.me/cocoassignments": AgencyInfo(examples_key="cocoassignments", display_name="CocoTutors"),
    "t.me/tuittysg": AgencyInfo(examples_key="tuittysg", display_name="Tuitty"),
    "t.me/mindworkstuitionassignment": AgencyInfo(examples_key="mindworkstuitionassignment", display_name="Mindworks Tuition"),
    "t.me/sgtuitions": AgencyInfo(examples_key="sgtuitions", display_name="SG Tuitions"),
    "t.me/starttuition": AgencyInfo(examples_key="starttuition", display_name="Start Tuition"),
    "t.me/newtuitionassignments": AgencyInfo(examples_key="newtuitionassignments", display_name="Tuition Assignments SG"),
}


def get_agency_info(chat: str) -> Optional[AgencyInfo]:
    return AGENCIES_BY_CHAT.get(normalize_chat_ref(chat))


def get_agency_examples_key(chat: str) -> Optional[str]:
    info = get_agency_info(chat)
    return info.examples_key if info else None


def get_agency_display_name(chat: str, default: str = "Agency") -> str:
    info = get_agency_info(chat)
    return info.display_name if info else default
