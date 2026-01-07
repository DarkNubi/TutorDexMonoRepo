export interface AssignmentRow {
  id: number;
  external_id?: string | null;
  message_link?: string | null;
  agency_name?: string | null;
  learning_mode?: string | null;
  assignment_code?: string | null;
  academic_display_text?: string | null;
  address?: string[] | null;
  postal_code?: string[] | null;
  postal_code_estimated?: string[] | null;
  nearest_mrt?: string[] | null;
  region?: string | null;
  nearest_mrt_computed?: string | null;
  nearest_mrt_computed_line?: string | null;
  nearest_mrt_computed_distance_m?: number | null;
  lesson_schedule?: string[] | null;
  start_date?: string | null;
  time_availability_note?: string | null;
  rate_min?: number | null;
  rate_max?: number | null;
  rate_raw_text?: string | null;
  signals_subjects?: string[] | null;
  signals_levels?: string[] | null;
  signals_specific_student_levels?: string[] | null;
  subjects_canonical?: string[] | null;
  subjects_general?: string[] | null;
  canonicalization_version?: number | null;
  status?: string | null;
  created_at?: string | null;
  published_at?: string | null;
  last_seen?: string | null;
  freshness_tier?: string | null;
  distance_km?: number | null;
  distance_sort_key?: number | null;
  postal_coords_estimated?: boolean | null;
  [k: string]: unknown;
}

