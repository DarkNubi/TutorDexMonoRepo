"""
Pydantic models for TutorDexBackend routes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TutorUpsert(BaseModel):
    chat_id: Optional[str] = Field(None, description="Telegram chat id to DM (required to receive DMs)")
    postal_code: Optional[str] = None
    subjects: Optional[List[str]] = None
    levels: Optional[List[str]] = None
    subject_pairs: Optional[List[Dict[str, str]]] = None
    assignment_types: Optional[List[str]] = None
    tutor_kinds: Optional[List[str]] = None
    learning_modes: Optional[List[str]] = None
    teaching_locations: Optional[List[str]] = None
    contact_phone: Optional[str] = None
    contact_telegram_handle: Optional[str] = None
    desired_assignments_per_day: Optional[int] = Field(None, description="Target number of assignments per day (default: 10)")


class MatchPayloadRequest(BaseModel):
    payload: Dict[str, Any]


class TelegramLinkCodeRequest(BaseModel):
    tutor_id: str
    ttl_seconds: Optional[int] = 600


class TelegramClaimRequest(BaseModel):
    code: str
    chat_id: str
    telegram_username: Optional[str] = None


class AnalyticsEventRequest(BaseModel):
    event_type: str
    assignment_external_id: Optional[str] = None
    agency_name: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class ClickTrackRequest(BaseModel):
    event_type: str
    assignment_external_id: Optional[str] = None
    destination_type: Optional[str] = None
    destination_url: Optional[str] = None
    timestamp_ms: Optional[int] = None
    meta: Optional[Dict[str, Any]] = None


class AssignmentRow(BaseModel):
    id: int
    external_id: Optional[str] = None
    message_link: Optional[str] = None
    agency_name: Optional[str] = None
    learning_mode: Optional[str] = None
    assignment_code: Optional[str] = None
    academic_display_text: Optional[str] = None
    address: Optional[List[str]] = None
    postal_code: Optional[List[str]] = None
    postal_code_estimated: Optional[List[str]] = None
    nearest_mrt: Optional[List[str]] = None
    region: Optional[str] = None
    nearest_mrt_computed: Optional[str] = None
    nearest_mrt_computed_line: Optional[str] = None
    nearest_mrt_computed_distance_m: Optional[int] = None
    lesson_schedule: Optional[List[str]] = None
    start_date: Optional[str] = None
    time_availability_note: Optional[str] = None
    rate_min: Optional[int] = None
    rate_max: Optional[int] = None
    rate_raw_text: Optional[str] = None
    tutor_types: Optional[List[Dict[str, Any]]] = None
    rate_breakdown: Optional[Dict[str, Any]] = None
    signals_subjects: Optional[List[str]] = None
    signals_levels: Optional[List[str]] = None
    signals_specific_student_levels: Optional[List[str]] = None
    subjects_canonical: Optional[List[str]] = None
    subjects_general: Optional[List[str]] = None
    canonicalization_version: Optional[int] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    last_seen: Optional[str] = None
    freshness_tier: Optional[str] = None
    distance_km: Optional[float] = None
    distance_sort_key: Optional[float] = None
    postal_coords_estimated: Optional[bool] = None

    class Config:
        extra = "allow"


class AssignmentListResponse(BaseModel):
    ok: bool = True
    total: int = 0
    items: List[AssignmentRow] = Field(default_factory=list)
    next_cursor_last_seen: Optional[str] = None
    next_cursor_id: Optional[int] = None
    next_cursor_distance_km: Optional[float] = None


class AssignmentFacetsResponse(BaseModel):
    ok: bool = True
    facets: Dict[str, Any] = Field(default_factory=dict)


class MatchCountsRequest(BaseModel):
    levels: Optional[List[str]] = None
    specific_student_levels: Optional[List[str]] = None
    subjects: Optional[List[str]] = None
    subjects_canonical: Optional[List[str]] = None
    subjects_general: Optional[List[str]] = None

