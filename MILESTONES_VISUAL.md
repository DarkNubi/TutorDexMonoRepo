# TutorDex Milestone Roadmap (Visual)

```
┌─────────────────────────────────────────────────────────────────────┐
│                   CURRENT STATUS: ✅ Milestone 1                     │
│                      (Aggregation Accuracy)                          │
│                                                                       │
│  ✅ Multi-channel Telegram aggregation                               │
│  ✅ LLM extraction + deterministic hardening                         │
│  ✅ Redis matching + Supabase persistence                            │
│  ✅ DM notifications to matched tutors                               │
│  ✅ Website with filtering, search, auth                             │
│  ✅ Full observability stack (50+ metrics, 17 alerts)                │
│                                                                       │
│  STATUS: Production-ready for beta testing                           │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│              🎯 MILESTONE 2: Product Analytics (2-3 weeks)           │
│                                                                       │
│  GOAL: Understand tutor behavior, validate product loop              │
│                                                                       │
│  Tasks:                                                               │
│    Week 1-2: Implement frontend analytics events ⚡ CRITICAL         │
│              - assignment_list_view, assignment_view                 │
│              - assignment_apply_click, preferences_update            │
│                                                                       │
│    Week 3-4: Build tutor feedback UI                                 │
│              - Report filled/scam/no-reply                           │
│              - Hide/save assignments                                 │
│              - Assignment action menu                                │
│                                                                       │
│    Week 5-6: Create KPI dashboard + backend enhancements             │
│              - WAU, apply rate, dead-end rate                        │
│              - Grafana "Product Analytics" dashboard                 │
│              - History/hide/save API endpoints                       │
│                                                                       │
│  Success Metrics:                                                     │
│    ✓ Can answer: "What % of viewed assignments get applied to?"     │
│    ✓ Can answer: "What % of applications have bad outcomes?"        │
│    ✓ 10+ tutors use reporting UI weekly                             │
│    ✓ Data-driven decisions become possible                          │
│                                                                       │
│  UNLOCKS: Understanding of product-market fit                        │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│       🚀 MILESTONE 3: One-Click Apply & App Flow (3-4 weeks)         │
│                                                                       │
│  GOAL: Route applications through TutorDex (agency leverage)         │
│                                                                       │
│  Tasks:                                                               │
│    Week 7-8:  Application storage + management                       │
│              - tutor_applications table                              │
│              - Application tracking schema                           │
│              - Outcome/status tracking                               │
│                                                                       │
│    Week 9:    One-click apply UI                                     │
│              - Apply modal with pre-filled info                      │
│              - Profile completeness check                            │
│              - Applied state indicators                              │
│                                                                       │
│    Week 10:   Backend application API                                │
│              - POST /me/assignments/{id}/apply                       │
│              - GET /me/applications                                  │
│              - Outcome reporting endpoints                           │
│                                                                       │
│    Week 11-12: Application delivery system                           │
│              - Email relay worker                                    │
│              - Agency contact registry                               │
│              - Delivery tracking & retries                           │
│              - Application analytics funnel                          │
│                                                                       │
│  Success Metrics:                                                     │
│    ✓ One-click apply works end-to-end                               │
│    ✓ 20%+ of applications use one-click (vs external)               │
│    ✓ Applications delivered within 5 minutes                        │
│    ✓ Can measure success rate per agency                            │
│    ✓ Agencies become aware of TutorDex traffic                      │
│                                                                       │
│  UNLOCKS: Agency partnerships, data moat, monetization path          │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│         💰 MILESTONE 4: Soft Monetization (2-3 weeks)                │
│                                                                       │
│  GOAL: Validate willingness to pay, offset infrastructure costs      │
│                                                                       │
│  Tasks:                                                               │
│    Week 13-14: User tier system + payment flow                       │
│              - Database schema (free/supporter/premium)              │
│              - Manual PayNow payment (MVP)                           │
│              - Pricing page + upgrade flow                           │
│                                                                       │
│    Week 15:   Premium feature implementation                         │
│              - Tier-aware DM delivery (caps/delays)                  │
│              - Tier-gated filters (distance, rate)                   │
│              - Historical data access tiers                          │
│              - Upgrade prompts & feature gates                       │
│                                                                       │
│    Week 15:   Tier analytics & monitoring                            │
│              - Conversion funnel tracking                            │
│              - MRR/LTV metrics                                       │
│              - Grafana "Monetization" dashboard                      │
│                                                                       │
│  Tier Comparison:                                                     │
│    FREE       : 10 DMs/day (10min delay), 7d history, basic filters │
│    SUPPORTER  : 30 DMs/day (instant), 30d history, ±5km filter      │
│    PREMIUM    : Unlimited DMs, unlimited history, ±1km + intel      │
│                                                                       │
│  Success Metrics:                                                     │
│    ✓ 5%+ of active tutors upgrade to paid tier                      │
│    ✓ No significant free user churn                                 │
│    ✓ Revenue covers 50%+ of infrastructure costs                    │
│    ✓ Clear data on which features drive upgrades                    │
│                                                                       │
│  UNLOCKS: Financial sustainability, agency pitch credibility         │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
                        ┌────────────────┐
                        │  FUTURE WORK   │
                        └────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
    ┌─────────────────┐ ┌─────────────┐  ┌─────────────────┐
    │   Milestone 5   │ │ Milestone 6 │  │   Milestone 7   │
    │   Agency API    │ │   Market    │  │   Commission    │
    │   & Dependence  │ │ Intelligence│  │   Negotiation   │
    └─────────────────┘ └─────────────┘  └─────────────────┘
           3-4w               2-3w              ongoing


═══════════════════════════════════════════════════════════════════════

CRITICAL PATH RECOMMENDATIONS:

Week 1-2:  START HERE → Milestone 2.1 (Frontend Analytics)
           ⚡ HIGHEST PRIORITY - unblocks everything else
           ⚡ Fast to implement (2-3 days)
           ⚡ Essential for data-driven decisions

Week 3-6:  Complete Milestone 2 (Analytics + Feedback)
           → Validate product-market fit
           → Understand tutor behavior
           → Identify what needs fixing

Week 7-12: Execute Milestone 3 (One-Click Apply)
           → Build agency leverage
           → Create data moat
           → Enable monetization

Week 13-15: Launch Milestone 4 (Monetization)
           → Prove financial viability
           → Segment users by value
           → Offset infrastructure costs

═══════════════════════════════════════════════════════════════════════

KEY DEPENDENCIES:

Milestone 2 → Milestone 3
  Why: Need to understand apply behavior before building one-click

Milestone 3 → Agency Partnerships (M5-M7)
  Why: Need application data to negotiate with agencies

Milestone 4 can run in parallel with M3 (low risk)

═══════════════════════════════════════════════════════════════════════

EFFORT SUMMARY:

Total estimated time: 15 weeks (one full-time developer)
  - Milestone 2: 2-3 weeks
  - Milestone 3: 3-4 weeks
  - Milestone 4: 2-3 weeks
  - Buffer/testing/polish: 2 weeks

Critical path: Milestone 2.1 must start immediately
Parallel work possible: M4 can overlap with M3 (weeks 10-15)

═══════════════════════════════════════════════════════════════════════
```

## Quick Reference Links

- **Full Details:** [NEXT_MILESTONES.md](NEXT_MILESTONES.md) (757 lines)
- **Executive Summary:** [MILESTONE_SUMMARY.md](MILESTONE_SUMMARY.md) (196 lines)
- **Strategic Vision:** [TutorDex background info.txt](TutorDex%20background%20info.txt)
- **Observability Status:** [TODO_OBSERVABILITY.md](TODO_OBSERVABILITY.md)

## What to Build First (This Week)

```python
# File: TutorDexWebsite/src/page-assignments.js
# Add after successful data fetch:

await trackEvent({
  event_type: "assignment_list_view",
  meta: {
    filters: currentFilters,
    sort: currentSort,
    surface: "website",
    result_count: allAssignments.length
  }
});

# Add in renderAssignmentCard() when user clicks card:

card.addEventListener('click', async () => {
  await trackEvent({
    event_type: "assignment_view",
    assignment_external_id: assignment.external_id,
    agency_name: assignment.agency_name,
    meta: {
      list_position: index,
      surface: "website"
    }
  });
});

# Add when user clicks "View Contact" or external link:

applyButton.addEventListener('click', async () => {
  await trackEvent({
    event_type: "assignment_apply_click",
    assignment_external_id: assignment.external_id,
    agency_name: assignment.agency_name,
    meta: {
      surface: "website",
      method: "external"
    }
  });
  // Then open link
});
```

## Testing Your Implementation

```bash
# 1. Start your local stack
docker compose up -d

# 2. Open website and browse assignments
# Check browser console for trackEvent calls

# 3. Query Supabase to verify events:
select 
  event_type, 
  count(*), 
  min(event_time), 
  max(event_time)
from public.analytics_events
where event_time > now() - interval '1 hour'
group by event_type
order by count(*) desc;

# 4. Verify in Grafana (after implementing dashboard)
# Navigate to Product Analytics dashboard
# Check "Event Volume" panel
```

---

**Next Steps:**
1. Read [NEXT_MILESTONES.md](NEXT_MILESTONES.md) for full implementation details
2. Start with Milestone 2.1 (Frontend Analytics) this week
3. Open issues for each milestone phase to track progress
4. Schedule weekly reviews to adjust priorities based on data
