import type { AssignmentRow } from "@/generated/assignmentRow"

import type { LandingAssignment } from "./types"

const MS_PER_DAY = 24 * 60 * 60 * 1000

export function isBackendEnabled(): boolean {
  const raw = (import.meta as unknown as { env?: Record<string, unknown> })?.env?.VITE_BACKEND_URL
  return Boolean(String(raw ?? "").trim())
}

function backendUrl(): string {
  const raw = (import.meta as unknown as { env?: Record<string, unknown> })?.env?.VITE_BACKEND_URL
  return String(raw ?? "").trim().replace(/\/$/, "")
}

export async function fetchAssignmentsPage({
  limit,
  signal,
}: {
  limit: number
  signal?: AbortSignal
}): Promise<{ items: AssignmentRow[] } | null> {
  if (!isBackendEnabled()) return null
  const base = backendUrl()
  if (!base) return null

  const params = new URLSearchParams()
  params.set("limit", String(Math.max(1, Math.min(200, limit))))
  params.set("sort", "newest")
  const url = `${base}/assignments?${params.toString()}`

  const resp = await fetch(url, { method: "GET", signal })
  if (!resp.ok) {
    const text = await resp.text().catch(() => "")
    throw new Error(`Backend GET /assignments failed (${resp.status}): ${text || resp.statusText}`)
  }
  const data = (await resp.json().catch(() => null)) as { items?: AssignmentRow[] } | null
  return data && Array.isArray(data.items) ? { items: data.items } : { items: [] }
}

function firstText(value: unknown): string {
  if (value == null) return ""
  if (Array.isArray(value)) {
    for (const item of value) {
      const s = firstText(item)
      if (s) return s
    }
    return ""
  }
  if (typeof value === "string") return value.trim()
  if (typeof value === "number" && Number.isFinite(value)) return String(value)
  try {
    return String(value).trim()
  } catch {
    return ""
  }
}

function asTextList(value: unknown): string[] {
  if (value == null) return []
  if (Array.isArray(value)) {
    return value
      .flatMap((v) => asTextList(v))
      .map((s) => String(s).trim())
      .filter(Boolean)
  }
  if (typeof value === "string") {
    const s = value.trim()
    if (!s) return []
    if (s.startsWith("[") && s.endsWith("]")) {
      try {
        const parsed = JSON.parse(s)
        if (Array.isArray(parsed)) return parsed.map((x) => String(x ?? "").trim()).filter(Boolean)
      } catch {
        // ignore
      }
    }
    if (s.includes("\n")) return s.split("\n").map((x) => x.trim()).filter(Boolean)
    return [s]
  }
  return [String(value).trim()].filter(Boolean)
}

function parseRateNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value
  const s = String(value ?? "").trim()
  if (!s) return null
  const m = s.match(/(\\d{1,4})/)
  if (!m) return null
  const n = Number.parseInt(m[1], 10)
  return Number.isFinite(n) ? n : null
}

function formatRate(row: AssignmentRow): { label: string; maxRate: number | null } {
  const min = typeof row.rate_min === "number" && Number.isFinite(row.rate_min) ? row.rate_min : parseRateNumber(row.rate_raw_text)
  const max = typeof row.rate_max === "number" && Number.isFinite(row.rate_max) ? row.rate_max : null
  const maxRate = max ?? min

  if (typeof min === "number" && typeof max === "number") {
    if (Math.abs(min - max) < 1e-9) return { label: `$${min}/hr`, maxRate }
    return { label: `$${min}-${max}/hr`, maxRate }
  }
  if (typeof min === "number") return { label: `$${min}/hr`, maxRate }

  const raw = String(row.rate_raw_text ?? "").trim()
  return { label: raw || "N/A", maxRate }
}

function formatRelativeTime(isoString: string): string {
  const t = Date.parse(String(isoString || ""))
  if (!Number.isFinite(t)) return ""
  const deltaMs = Date.now() - t
  if (!Number.isFinite(deltaMs)) return ""
  const mins = Math.floor(deltaMs / 60000)
  if (mins < 1) return "just now"
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 48) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function publishedMs(row: AssignmentRow): number {
  const iso = String(row.published_at ?? row.created_at ?? row.last_seen ?? "")
  const t = Date.parse(iso)
  return Number.isFinite(t) ? t : 0
}

export function mapRowToLandingAssignment(row: AssignmentRow): LandingAssignment {
  const subjects = asTextList(row.signals_subjects)
  const subject = subjects.slice(0, 2).join(" & ") || String(row.academic_display_text ?? "").trim() || "Tuition Assignment"

  const level =
    asTextList(row.signals_specific_student_levels).slice(0, 2).join(" / ") ||
    asTextList(row.signals_levels).slice(0, 2).join(" / ") ||
    ""

  const address = firstText(row.address)
  const postal = firstText(row.postal_code)
  const mrt = firstText(row.nearest_mrt)
  const region = firstText(row.region)
  const location = address || mrt || postal || region || "Singapore"

  const { label: rateLabel } = formatRate(row)

  const schedule = asTextList(row.lesson_schedule)
  const timeNote = asTextList(row.time_availability_note)
  const learningMode = firstText(row.learning_mode)
  const timing = schedule[0] || timeNote[0] || (learningMode ? `${learningMode} · Flexible` : "Flexible")

  const postedIso = String(row.published_at ?? row.created_at ?? row.last_seen ?? "").trim()
  const posted = postedIso ? formatRelativeTime(postedIso) : ""

  const agency =
    String(row.agency_display_name ?? row.agency_telegram_channel_name ?? "").trim() || "Partner agency"
  const externalId = String(row.external_id ?? "").trim()
  const internalId = row.id != null ? String(row.id).trim() : ""
  const id = externalId || (internalId ? `DB-${internalId}` : "")

  const rawLink = String(row.message_link ?? "").trim()
  const messageLink = rawLink.startsWith("t.me/") ? `https://${rawLink}` : rawLink || undefined

  return {
    id,
    subject,
    level,
    location,
    rate: rateLabel,
    timing,
    posted,
    agency,
    messageLink,
  }
}
