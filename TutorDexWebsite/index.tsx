import React, { useState, useEffect, useRef } from "react"
import { motion, useScroll } from "framer-motion"
import { 
  ChevronRight, 
  Menu, 
  X, 
  ArrowRight,
  MapPin,
  DollarSign,
  Clock,
  BookOpen,
  Zap,
  Search,
  Filter,
  TrendingUp,
  Users,
  Shield,
  CheckCircle2
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ThemeToggle } from "@/components/ui/theme-toggle"

import type { AssignmentRow } from "@/generated/assignmentRow"

// Utility function
const cn = (...classes: (string | undefined | null | false)[]) => {
  return classes.filter(Boolean).join(" ")
}

// Animation variants
const fadeIn = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.6 },
  },
}

const staggerContainer = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
    },
  },
}

const itemFadeIn = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5 },
  },
}

// Types
interface Assignment {
  id: string
  subject: string
  level: string
  location: string
  rate: string
  timing: string
  posted: string
  agency: string
  messageLink?: string
}

const MS_PER_DAY = 24 * 60 * 60 * 1000

function isBackendEnabled(): boolean {
  const raw = (import.meta as unknown as { env?: Record<string, unknown> })?.env?.VITE_BACKEND_URL
  return Boolean(String(raw ?? "").trim())
}

function backendUrl(): string {
  const raw = (import.meta as unknown as { env?: Record<string, unknown> })?.env?.VITE_BACKEND_URL
  return String(raw ?? "").trim().replace(/\/$/, "")
}

async function fetchAssignmentsPage({
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
  const m = s.match(/(\d{1,4})/)
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

function mapRowToLandingAssignment(row: AssignmentRow): Assignment {
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
  const timing =
    schedule[0] || timeNote[0] || (learningMode ? `${learningMode} · Flexible` : "Flexible")

  const postedIso = String(row.published_at ?? row.created_at ?? row.last_seen ?? "").trim()
  const posted = postedIso ? formatRelativeTime(postedIso) : ""

  const agency = String(row.agency_name ?? "").trim() || "Partner agency"
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

// Logo Component
const TutorDexLogo = ({ className }: { className?: string }) => {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-blue-500 via-indigo-500 to-teal-500 flex items-center justify-center shadow-lg">
        <BookOpen className="h-5 w-5 text-white" />
      </div>
      <span className="font-bold text-xl">TutorDex</span>
    </div>
  )
}

function openLogin() {
  // Provided by index.html (kept in plain JS so auth.js can bind to DOM IDs)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).showAuth?.()
}

function openSignup() {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).showSignUp?.()
}

function goAssignments() {
  window.location.assign("assignments.html")
}

// Header Component
const Header = () => {
  const [menuState, setMenuState] = useState(false)
  const [scrolled, setScrolled] = useState(false)
  const { scrollYProgress } = useScroll()

  useEffect(() => {
    const unsubscribe = scrollYProgress.on("change", (latest) => {
      setScrolled(latest > 0.05)
    })
    return () => unsubscribe()
  }, [scrollYProgress])

  const menuItems = [
    { name: "Features", href: "#features" },
    { name: "How It Works", href: "#how-it-works" },
    { name: "Assignments", href: "#assignments" },
  ]

  return (
    <header>
      <nav
        data-state={menuState && "active"}
        className={cn(
          "group fixed z-50 w-full border-b transition-colors duration-150",
          scrolled && "bg-background/80 backdrop-blur-xl shadow-sm"
        )}
      >
        <div className="container mx-auto max-w-7xl px-6 transition-all duration-300">
          <div className="relative flex flex-wrap items-center justify-between gap-6 py-4 lg:gap-0">
            <div className="flex w-full items-center justify-between gap-12 lg:w-auto">
              <TutorDexLogo />

              <button
                onClick={() => setMenuState(!menuState)}
                aria-label={menuState ? "Close Menu" : "Open Menu"}
                className="relative z-20 -m-2.5 -mr-4 block cursor-pointer p-2.5 lg:hidden"
              >
                <Menu className="group-data-[state=active]:rotate-180 group-data-[state=active]:scale-0 group-data-[state=active]:opacity-0 m-auto size-6 duration-200" />
                <X className="group-data-[state=active]:rotate-0 group-data-[state=active]:scale-100 group-data-[state=active]:opacity-100 absolute inset-0 m-auto size-6 -rotate-180 scale-0 opacity-0 duration-200" />
              </button>

              <div className="hidden lg:block">
                <ul className="flex gap-8 text-sm">
                  {menuItems.map((item, index) => (
                    <li key={index}>
                      <a
                        href={item.href}
                        className="text-muted-foreground hover:text-foreground block duration-150"
                      >
                        <span>{item.name}</span>
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="bg-background group-data-[state=active]:block lg:group-data-[state=active]:flex mb-6 hidden w-full flex-wrap items-center justify-end space-y-8 rounded-3xl border p-6 shadow-2xl md:flex-nowrap lg:m-0 lg:flex lg:w-fit lg:gap-6 lg:space-y-0 lg:border-transparent lg:bg-transparent lg:p-0 lg:shadow-none">
              <div className="lg:hidden">
                <ul className="space-y-6 text-base">
                  {menuItems.map((item, index) => (
                    <li key={index}>
                      <a
                        href={item.href}
                        className="text-muted-foreground hover:text-foreground block duration-150"
                        onClick={() => setMenuState(false)}
                      >
                        <span>{item.name}</span>
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="flex w-full flex-col space-y-3 sm:flex-row sm:gap-3 sm:space-y-0 md:w-fit">
                <div className="flex gap-3">
                  <ThemeToggle />
                  <Button variant="outline" size="sm" onClick={openLogin} className="rounded-xl flex-1 sm:flex-initial">
                    Sign In
                  </Button>
                </div>
                <Button
                  size="sm"
                  onClick={openSignup}
                  className="rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700"
                >
                  Join TutorDex
                </Button>
              </div>
            </div>
          </div>
        </div>
      </nav>
    </header>
  )
}

// Main Landing Page Component
export function TutorDexLanding() {
  const sampleAssignments: Assignment[] = [
    {
      id: "1",
      subject: "H2 Mathematics",
      level: "JC2",
      location: "Bishan",
      rate: "$80-100/hr",
      timing: "Weekends, 2hrs/week",
      posted: "2 hours ago",
      agency: "Elite Tutors SG"
    },
    {
      id: "2",
      subject: "IGCSE Physics & Chemistry",
      level: "Sec 3-4",
      location: "Tampines",
      rate: "$70-85/hr",
      timing: "Weekdays after 6pm",
      posted: "5 hours ago",
      agency: "SmartLearn Agency"
    },
    {
      id: "3",
      subject: "Primary 5 English & Math",
      level: "Primary 5",
      location: "Clementi",
      rate: "$50-60/hr",
      timing: "Tue & Thu, 4-6pm",
      posted: "1 day ago",
      agency: "TutorMatch SG"
    }
  ]

  const [heroAssignments, setHeroAssignments] = useState<Assignment[]>(sampleAssignments.slice(0, 2))
  const [liveAssignments, setLiveAssignments] = useState<Assignment[]>(sampleAssignments)
  const [isLiveLoading, setIsLiveLoading] = useState<boolean>(false)
  const [lastLiveUpdatedMs, setLastLiveUpdatedMs] = useState<number>(0)
  const [usingMock, setUsingMock] = useState<boolean>(!isBackendEnabled())

  const pollTimerRef = useRef<number | null>(null)
  const liveAbortRef = useRef<AbortController | null>(null)

  function stopPolling() {
    if (pollTimerRef.current != null) {
      window.clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
    if (liveAbortRef.current) {
      liveAbortRef.current.abort()
      liveAbortRef.current = null
    }
  }

  function idsOf(items: Assignment[]): string {
    return items.map((x) => x.id).join("|")
  }

  async function refreshFromBackend({ reason }: { reason: "initial" | "poll" }): Promise<void> {
    if (!isBackendEnabled()) {
      setUsingMock(true)
      return
    }

    if (liveAbortRef.current) liveAbortRef.current.abort()
    const ctrl = new AbortController()
    liveAbortRef.current = ctrl

    if (reason === "initial") setIsLiveLoading(true)
    try {
      // Fetch a small window so we can compute both hero "top paying" and live "latest" without extra calls.
      const page = await fetchAssignmentsPage({ limit: 50, signal: ctrl.signal })
      const rows = Array.isArray(page?.items) ? page!.items : []
      if (!rows.length) {
        setUsingMock(true)
        return
      }

      setUsingMock(false)

      const mapped = rows.map(mapRowToLandingAssignment).filter((a) => a.id)
      // Live: latest 3 (defensive sort by published time)
      const latest3 = [...rows]
        .sort((a, b) => publishedMs(b) - publishedMs(a))
        .slice(0, 3)
        .map(mapRowToLandingAssignment)
        .filter((a) => a.id)

      // Hero: top 2 by max rate among past 7 days
      const cutoff = Date.now() - 7 * MS_PER_DAY
      const scored = rows.map((r) => {
        const { maxRate } = formatRate(r)
        return { row: r, maxRate: maxRate ?? 0, t: publishedMs(r) }
      })
      const recent = scored.filter((x) => x.t >= cutoff)
      const pool = (recent.length ? recent : scored)
        .slice()
        .sort((a, b) => (b.maxRate - a.maxRate) || (b.t - a.t))
        .slice(0, 2)
        .map((x) => mapRowToLandingAssignment(x.row))
        .filter((a) => a.id)

      setHeroAssignments((prev) => {
        const next = pool.length ? pool : prev
        return idsOf(prev) === idsOf(next) ? prev : next
      })

      setLiveAssignments((prev) => {
        const next = latest3.length ? latest3 : prev
        return idsOf(prev) === idsOf(next) ? prev : next
      })

      // Keep a reference to avoid lint complaints (and to show intent that mapped can be used later)
      void mapped
      setLastLiveUpdatedMs(Date.now())
    } catch (e) {
      // Poll failures should be silent; keep the last known data.
      if (String((e as Error)?.name || "") !== "AbortError") {
        setUsingMock(true)
      }
    } finally {
      if (reason === "initial") setIsLiveLoading(false)
    }
  }

  useEffect(() => {
    // Initial load + polling for live updates.
    void refreshFromBackend({ reason: "initial" })

    stopPolling()
    if (isBackendEnabled()) {
      const POLL_MS = 25_000
      pollTimerRef.current = window.setInterval(() => {
        void refreshFromBackend({ reason: "poll" })
      }, POLL_MS)
    }

    return () => stopPolling()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <Header />

      <main className="flex-1 pt-16">
        {/* Hero Section */}
        <section className="w-full py-16 md:py-24 lg:py-32 overflow-hidden">
          <div className="container mx-auto max-w-7xl px-6">
            <div className="grid gap-8 lg:grid-cols-2 lg:gap-12 items-center">
              <motion.div
                initial="hidden"
                whileInView="visible"
                viewport={{ once: true }}
                variants={fadeIn}
                className="flex flex-col justify-center space-y-6"
              >
                <motion.div
                  initial={{ opacity: 0, scale: 0.8 }}
                  whileInView={{ opacity: 1, scale: 1 }}
                  transition={{ duration: 0.5 }}
                  className="inline-flex items-center rounded-full bg-gradient-to-r from-blue-100 to-indigo-100 dark:from-blue-950 dark:to-indigo-950 px-4 py-2 text-sm w-fit"
                >
                  <Zap className="mr-2 h-4 w-4 text-blue-600" />
                  <span className="font-medium text-blue-700 dark:text-blue-300">For Tutors in Singapore</span>
                </motion.div>

                <motion.h1
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.7, delay: 0.2 }}
                  className="text-4xl font-bold tracking-tight sm:text-5xl xl:text-6xl"
                >
                  All tuition assignments.{" "}
                  <span className="bg-gradient-to-r from-blue-600 via-indigo-600 to-teal-500 bg-clip-text text-transparent">
                    One platform.
                  </span>
                </motion.h1>

                <motion.p
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.7, delay: 0.4 }}
                  className="text-lg text-muted-foreground max-w-xl"
                >
                  Stop scrolling through endless Telegram channels. TutorDex aggregates assignments from multiple agencies in real-time, so you can find and apply faster.
                </motion.p>

                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.7, delay: 0.6 }}
                  className="flex flex-col gap-3 sm:flex-row"
                >
                  <Button
                    size="lg"
                    onClick={openSignup}
                    className="rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 group shadow-lg shadow-blue-500/25"
                  >
                    Join TutorDex
                    <motion.span
                      initial={{ x: 0 }}
                      whileHover={{ x: 5 }}
                      transition={{ type: "spring", stiffness: 400, damping: 10 }}
                    >
                      <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
                    </motion.span>
                  </Button>
                  <Button variant="outline" size="lg" onClick={goAssignments} className="rounded-xl">
                    View Live Assignments
                  </Button>
                </motion.div>
              </motion.div>

              <motion.div
                initial={{ opacity: 0, x: 100 }}
                whileInView={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.8 }}
                className="relative"
              >
                <div className="relative rounded-3xl overflow-hidden border bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-950/20 dark:to-indigo-950/20 p-6 shadow-2xl">
                  <div className="space-y-4">
                      {heroAssignments.slice(0, 2).map((assignment, idx) => (
                      <motion.div
                        key={assignment.id}
                        initial={{ opacity: 0, y: 20 }}
                        whileInView={{ opacity: 1, y: 0 }}
                        transition={{ delay: idx * 0.2 }}
                        className="bg-background rounded-2xl p-5 shadow-md border hover:shadow-lg transition-shadow"
                      >
                        <div className="flex items-start justify-between mb-3">
                          <div>
                            <h3 className="font-semibold text-lg">{assignment.subject}</h3>
                            <p className="text-sm text-muted-foreground">{assignment.level}</p>
                          </div>
                          <Badge className="bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300">
                            New
                          </Badge>
                        </div>
                        <div className="grid grid-cols-2 gap-3 text-sm">
                          <div className="flex items-center gap-2">
                            <MapPin className="h-4 w-4 text-muted-foreground" />
                            <span>{assignment.location}</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <DollarSign className="h-4 w-4 text-muted-foreground" />
                            <span className="font-medium text-blue-600">{assignment.rate}</span>
                          </div>
                          <div className="flex items-center gap-2 col-span-2">
                            <Clock className="h-4 w-4 text-muted-foreground" />
                            <span>{assignment.timing}</span>
                          </div>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                  <div className="absolute -bottom-10 -right-10 w-40 h-40 bg-gradient-to-br from-blue-400 to-indigo-500 rounded-full blur-3xl opacity-20"></div>
                  <div className="absolute -top-10 -left-10 w-40 h-40 bg-gradient-to-br from-teal-400 to-blue-500 rounded-full blur-3xl opacity-20"></div>
                </div>
              </motion.div>
            </div>
          </div>
        </section>

        {/* Social Proof */}
        <section className="w-full py-12 md:py-16 bg-muted/30">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={fadeIn}
            className="container mx-auto max-w-7xl px-6"
          >
            <div className="text-center mb-8">
              <p className="text-sm text-muted-foreground mb-4">Trusted by tutors across Singapore</p>
              <div className="flex flex-wrap justify-center gap-8 md:gap-16">
                <div className="text-center">
                  <div className="text-3xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                    500+
                  </div>
                  <div className="text-sm text-muted-foreground">Active Tutors</div>
                </div>
                <div className="text-center">
                  <div className="text-3xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                    15+
                  </div>
                  <div className="text-sm text-muted-foreground">Partner Agencies</div>
                </div>
                <div className="text-center">
                  <div className="text-3xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
                    1000+
                  </div>
                  <div className="text-sm text-muted-foreground">Assignments Monthly</div>
                </div>
              </div>
            </div>
            <div className="flex flex-wrap justify-center items-center gap-4 text-sm text-muted-foreground">
              <div className="flex items-center gap-2">
                <Shield className="h-4 w-4 text-green-600" />
                <span>No spam, ever</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-green-600" />
                <span>100% free for tutors</span>
              </div>
              <div className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-green-600" />
                <span>Real-time updates</span>
              </div>
            </div>
          </motion.div>
        </section>

        {/* Value Propositions */}
        <section id="features" className="w-full py-16 md:py-24">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={fadeIn}
            className="container mx-auto max-w-7xl px-6"
          >
            <div className="text-center mb-12">
              <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                whileInView={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.5 }}
                className="inline-block rounded-full bg-blue-100 dark:bg-blue-950 px-4 py-2 text-sm mb-4"
              >
                <span className="font-medium text-blue-700 dark:text-blue-300">Why TutorDex?</span>
              </motion.div>
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl mb-4">
                Everything you need in one place
              </h2>
              <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                Save time, find better assignments, and grow your tutoring career
              </p>
            </div>

            <motion.div
              variants={staggerContainer}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true }}
              className="grid gap-6 md:grid-cols-2 lg:grid-cols-4"
            >
              {[
                {
                  icon: <Search className="h-8 w-8 text-blue-600" />,
                  title: "Aggregated Assignments",
                  description: "All assignments from multiple agencies in one feed. No more jumping between Telegram channels."
                },
                {
                  icon: <Zap className="h-8 w-8 text-indigo-600" />,
                  title: "Faster Discovery",
                  description: "Advanced filters by subject, level, location, and rate. Find what fits you in seconds."
                },
                {
                  icon: <Filter className="h-8 w-8 text-teal-600" />,
                  title: "Clean & Structured",
                  description: "No messy screenshots or unclear details. Every listing is formatted, verified, and easy to read."
                },
                {
                  icon: <TrendingUp className="h-8 w-8 text-purple-600" />,
                  title: "Always Free",
                  description: "Zero fees for tutors. We partner with agencies so you can focus on teaching, not paying."
                }
              ].map((feature, index) => (
                <motion.div
                  key={index}
                  variants={itemFadeIn}
                  whileHover={{ y: -8, transition: { duration: 0.3 } }}
                >
                  <Card className="h-full border-2 hover:border-blue-200 dark:hover:border-blue-800 transition-colors hover:shadow-lg">
                    <CardHeader>
                      <div className="mb-4 inline-flex items-center justify-center rounded-2xl bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-950/30 dark:to-indigo-950/30 p-3">
                        {feature.icon}
                      </div>
                      <CardTitle className="text-xl">{feature.title}</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <CardDescription className="text-base">
                        {feature.description}
                      </CardDescription>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
            </motion.div>
          </motion.div>
        </section>

        {/* How It Works */}
        <section id="how-it-works" className="w-full py-16 md:py-24 bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-950/10 dark:to-indigo-950/10">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={fadeIn}
            className="container mx-auto max-w-7xl px-6"
          >
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl mb-4">
                How it works
              </h2>
              <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                Get started in minutes and start applying to assignments today
              </p>
            </div>

            <motion.div
              variants={staggerContainer}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true }}
              className="grid gap-8 md:grid-cols-3"
            >
              {[
                {
                  step: "1",
                  title: "Sign Up",
                  description: "Create your free account with your email. Add your subjects, levels, and preferred locations."
                },
                {
                  step: "2",
                  title: "Browse Assignments",
                  description: "See all available assignments in one clean feed. Filter by what matters to you."
                },
                {
                  step: "3",
                  title: "Apply Instantly",
                  description: "Click to apply and we'll connect you directly with the agency. No middleman, no delays."
                }
              ].map((step, index) => (
                <motion.div
                  key={index}
                  variants={itemFadeIn}
                  className="relative"
                >
                  <div className="flex flex-col items-center text-center">
                    <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-blue-600 to-indigo-600 text-2xl font-bold text-white shadow-lg">
                      {step.step}
                    </div>
                    <h3 className="text-xl font-semibold mb-2">{step.title}</h3>
                    <p className="text-muted-foreground">{step.description}</p>
                  </div>
                  {index < 2 && (
                    <div className="hidden md:block absolute top-8 left-[60%] w-[80%] h-0.5 bg-gradient-to-r from-blue-300 to-indigo-300 dark:from-blue-700 dark:to-indigo-700"></div>
                  )}
                </motion.div>
              ))}
            </motion.div>
          </motion.div>
        </section>

        {/* Sample Assignments */}
        <section id="assignments" className="w-full py-16 md:py-24">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={fadeIn}
            className="container mx-auto max-w-7xl px-6"
          >
            <div className="text-center mb-12">
              <h2 className="text-3xl font-bold tracking-tight sm:text-4xl mb-4">
                Live assignments right now
              </h2>
              <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                Real assignments from our partner agencies, updated in real-time
              </p>
              <div className="mt-4 text-sm text-muted-foreground">
                {usingMock
                  ? "Showing demo data (backend not connected)."
                  : isLiveLoading
                    ? "Loading live assignments…"
                    : lastLiveUpdatedMs
                      ? `Last updated ${Math.max(0, Math.round((Date.now() - lastLiveUpdatedMs) / 1000))}s ago`
                      : ""}
              </div>
            </div>

            <motion.div
              variants={staggerContainer}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true }}
              className="grid gap-6 md:grid-cols-2 lg:grid-cols-3 max-w-6xl mx-auto"
            >
              {liveAssignments.slice(0, 3).map((assignment, index) => (
                <motion.div
                  key={assignment.id}
                  variants={itemFadeIn}
                  whileHover={{ y: -8, transition: { duration: 0.3 } }}
                >
                  <Card className="h-full hover:shadow-xl transition-shadow border-2 hover:border-blue-200 dark:hover:border-blue-800">
                    <CardHeader>
                      <div className="flex items-start justify-between mb-2">
                        <div>
                          <CardTitle className="text-xl mb-1">{assignment.subject}</CardTitle>
                          <Badge variant="secondary">{assignment.level}</Badge>
                        </div>
                        <Badge className="bg-green-100 text-green-700 dark:bg-green-950 dark:text-green-300">
                          {assignment.posted || ""}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <div className="flex items-center gap-2 text-sm">
                        <MapPin className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                        <span>{assignment.location}</span>
                      </div>
                      <div className="flex items-center gap-2 text-sm">
                        <DollarSign className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                        <span className="font-semibold text-blue-600">{assignment.rate}</span>
                      </div>
                      <div className="flex items-center gap-2 text-sm">
                        <Clock className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                        <span>{assignment.timing}</span>
                      </div>
                      <div className="pt-3 border-t">
                        <p className="text-xs text-muted-foreground mb-3">via {assignment.agency}</p>
                        <Button
                          className="w-full rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700"
                          onClick={() => {
                            if (assignment.messageLink) {
                              window.open(assignment.messageLink, "_blank", "noopener,noreferrer")
                            } else {
                              goAssignments()
                            }
                          }}
                        >
                          Apply Now
                        </Button>
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
            </motion.div>

            <div className="text-center mt-12">
              <Button size="lg" variant="outline" className="rounded-xl">
                View All Assignments
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </div>
          </motion.div>
        </section>

        {/* Final CTA */}
        <section className="w-full py-16 md:py-24 bg-gradient-to-br from-blue-600 via-indigo-600 to-teal-500 text-white">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true }}
            variants={fadeIn}
            className="container mx-auto max-w-4xl px-6 text-center"
          >
            <motion.h2
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6 }}
              className="text-3xl font-bold tracking-tight sm:text-4xl md:text-5xl mb-6"
            >
              Ready to find your next assignment?
            </motion.h2>
            <motion.p
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="text-lg md:text-xl mb-8 text-blue-50"
            >
              Join hundreds of tutors who've already saved hours every week. Free forever.
            </motion.p>
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.4 }}
              className="flex flex-col sm:flex-row gap-4 justify-center"
            >
              <Button
                size="lg"
                onClick={openSignup}
                className="rounded-xl bg-white text-blue-600 hover:bg-blue-50 shadow-xl"
              >
                Join TutorDex Now
                <ArrowRight className="ml-2 h-5 w-5" />
              </Button>
              <Button
                size="lg"
                variant="outline"
                onClick={() => window.location.assign("#features")}
                className="rounded-xl border-2 border-white text-white hover:bg-white/10"
              >
                Learn More
              </Button>
            </motion.div>
            <motion.p
              initial={{ opacity: 0 }}
              whileInView={{ opacity: 1 }}
              transition={{ duration: 0.6, delay: 0.6 }}
              className="mt-8 text-sm text-blue-100"
            >
              No credit card required • Set up in 2 minutes • Cancel anytime
            </motion.p>
          </motion.div>
        </section>
      </main>

      {/* Footer */}
      <footer className="w-full border-t bg-muted/30">
        <div className="container mx-auto max-w-7xl px-6 py-12">
          <div className="grid gap-8 md:grid-cols-4">
            <div className="space-y-4">
              <TutorDexLogo />
              <p className="text-sm text-muted-foreground">
                The smartest way for tutors in Singapore to discover tuition assignments.
              </p>
            </div>
            <div>
              <h3 className="font-semibold mb-4">Product</h3>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li><a href="#features" className="hover:text-foreground">Features</a></li>
                <li><a href="#how-it-works" className="hover:text-foreground">How It Works</a></li>
                <li><a href="#assignments" className="hover:text-foreground">Browse Assignments</a></li>
              </ul>
            </div>
            <div>
              <h3 className="font-semibold mb-4">Company</h3>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li><a href="#" className="hover:text-foreground">About Us</a></li>
                <li><a href="#" className="hover:text-foreground">For Agencies</a></li>
                <li><a href="#" className="hover:text-foreground">Contact</a></li>
              </ul>
            </div>
            <div>
              <h3 className="font-semibold mb-4">Legal</h3>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li><a href="#" className="hover:text-foreground">Privacy Policy</a></li>
                <li><a href="#" className="hover:text-foreground">Terms of Service</a></li>
              </ul>
            </div>
          </div>
          <div className="mt-12 pt-8 border-t text-center text-sm text-muted-foreground">
            <p>&copy; {new Date().getFullYear()} TutorDex. All rights reserved. Made for tutors in Singapore.</p>
          </div>
        </div>
      </footer>
    </div>
  )
}

export default TutorDexLanding