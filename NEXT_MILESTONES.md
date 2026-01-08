# TutorDex: Next Three Recommended Milestones

**Document created:** 2026-01-08  
**Analysis date:** January 2026

---

## Executive Summary

Based on a comprehensive review of the TutorDex MonoRepo, the project has achieved **Milestone 1 (Aggregation Accuracy)** with a robust technical foundation:

✅ **Infrastructure Complete:**
- Multi-channel Telegram aggregation with LLM-based parsing
- Raw message persistence and extraction queue for resilience
- Redis-based matching engine with preference storage
- Comprehensive observability stack (Prometheus, Grafana, Loki, Alertmanager)
- Self-hosted Supabase for data persistence
- Firebase-authenticated website with assignments browser and profile management
- Docker-based deployment with automatic CI/CD

✅ **Core Features Working:**
- Automated message collection from multiple Telegram channels
- LLM extraction with deterministic hardening for quality
- Duplicate detection and bump handling
- DM delivery to matched tutors
- Website with advanced filtering, sorting, and search
- Tutor preference management and Telegram linking
- Full observability with 50+ metrics and 17 active alerts

**Current Status:** The system is production-ready for beta testing with real tutors.

---

## Recommended Next Three Milestones

### **Milestone 2: Product Analytics & Loop Validation** 📊

**Goal:** Understand tutor behavior and validate that the "discovery → engagement → application" loop is working.

**Current State:**
- ✅ Analytics infrastructure exists (`analytics_events` table, `/analytics/event` API endpoint)
- ❌ Frontend is NOT emitting analytics events
- ❌ No KPI queries or dashboards set up
- ❌ No tutor feedback mechanisms (assignment filled/scam/no-reply reporting)

**Why This Matters:**
Right now, you're flying blind. You don't know:
- How many tutors actively use the website vs DMs
- Which filters/features tutors actually use
- How many tutors apply to assignments they discover through TutorDex
- Whether tutors get responses from agencies
- Which assignments are high-quality vs dead-ends

Without this data, you can't make informed product decisions or prove value to tutors.

**Implementation Tasks:**

#### 2.1: Frontend Event Emission (Critical Path)
**Effort:** 2-3 days  
**Priority:** P0

Emit analytics events from the website for key user actions:

```javascript
// In page-assignments.js
- assignment_list_view (on page load, with filters/sort in meta)
- assignment_view (when user clicks to view details)
- assignment_apply_click (when user clicks "View Contact" or external link)

// In page-profile.js
- preferences_update (when user saves tutor profile, include changed fields)
- telegram_link_success (when link code generated)
```

**Files to modify:**
- `TutorDexWebsite/src/page-assignments.js`
- `TutorDexWebsite/src/page-profile.js`
- `TutorDexWebsite/src/backend.js` (add `trackEvent` helper if not present)

**Implementation notes:**
- Use existing `trackEvent` function that calls `/analytics/event`
- Include relevant metadata (filters, list_position, surface=website)
- Fire events asynchronously, don't block UI
- Handle auth failures gracefully (log but don't break)

#### 2.2: Tutor Feedback UI (High Impact)
**Effort:** 3-4 days  
**Priority:** P0

Add assignment reporting functionality to the website:

**New Page: Assignment Detail/Action Modal**
- Accessible from assignments list (new "..." menu on each card)
- Actions:
  - ✅ "Applied" → opens modal to report application outcome
  - 🚫 "Hide/Not Interested" → hide assignment, optional reason
  - ⚠️ "Report Issue" → report scam/filled/duplicate/spam
  - ⭐ "Save" → bookmark for later (optional enhancement)

**Reporting Modal:**
```javascript
// When tutor clicks "Applied":
{
  event_type: "assignment_apply_submit",
  assignment_external_id: "...",
  agency_name: "...",
  meta: { method: "external", applied_at: timestamp }
}

// Follow-up reporting (later):
{
  event_type: "assignment_reply_received",
  meta: { reply_time_minutes: 120 }
}

{
  event_type: "assignment_no_reply",
  meta: { days_waited: 3 }
}

{
  event_type: "assignment_filled_report",
  meta: { source: "tutor" }
}

{
  event_type: "assignment_scam_report",
  meta: { category: "fake_contact", notes: "..." }
}

{
  event_type: "assignment_hide",
  meta: { reason: "too_far|rate_low|not_interested|duplicate|other" }
}
```

**Files to create/modify:**
- `TutorDexWebsite/src/components/AssignmentActionsMenu.js` (new)
- `TutorDexWebsite/src/components/AssignmentReportModal.js` (new)
- `TutorDexWebsite/src/page-assignments.js` (integrate actions menu)
- `TutorDexWebsite/assignments.html` (add modal markup)

**Database additions:**
- `user_assignment_actions` table (track hidden/saved assignments per user)
- Index on `analytics_events(event_type, event_time)` for fast KPI queries

#### 2.3: KPI Dashboard Setup
**Effort:** 2-3 days  
**Priority:** P1

Create operational KPI queries and Grafana dashboard:

**Supabase Queries to Implement:**
- Weekly Active Users (WAU)
- Apply rate (views → apply clicks)
- Dead-end rate (no_reply + scam_report + filled_report per apply)
- Preference tuning rate (users who update preferences)
- Time-to-fill proxy (created → first filled report)
- Daily assignment supply (new/open/closed)

**New Grafana Dashboard:** "TutorDex Product Analytics"
- WAU trend graph
- Apply funnel (list views → detail views → apply clicks)
- Quality signals (dead-end rate, scam reports)
- Supply health (daily assignments, open rate)
- Tutor engagement (preference updates, return visits)

**Files to create:**
- `observability/grafana/dashboards/product-analytics.json`
- `docs/ANALYTICS_QUERIES.md` (document KPI queries for Supabase)

#### 2.4: Backend Enhancements
**Effort:** 1-2 days  
**Priority:** P1

Add helper endpoints for analytics:

```python
# In TutorDexBackend/app.py

@app.get("/me/assignments/history")
# Return user's assignment interaction history
# (viewed, applied, reported, hidden)

@app.post("/me/assignments/{assignment_id}/hide")
# Hide assignment for user (soft delete from feed)

@app.post("/me/assignments/{assignment_id}/save")
# Bookmark assignment for later

@app.get("/analytics/kpis")
# Return aggregated KPIs for admin dashboard
# (requires admin API key)
```

**Success Metrics for Milestone 2:**
- [ ] Frontend emits 4+ event types (list_view, view, apply_click, preferences_update)
- [ ] 10+ tutors use the reporting UI weekly
- [ ] KPI dashboard shows actionable metrics
- [ ] Can answer: "What percentage of viewed assignments get applied to?"
- [ ] Can answer: "What percentage of applications result in no reply/scam?"
- [ ] Data-driven decisions become possible (e.g., "filter X is unused, remove it")

**Estimated Total Effort:** 2-3 weeks (one developer)

---

### **Milestone 3: One-Click Apply & Centralized Application Flow** 🚀

**Goal:** Route tutor applications through TutorDex, building the data/leverage needed for agency monetization.

**Current State:**
- ❌ No one-click apply implementation
- ❌ Applications go directly to agencies (TutorDex invisible)
- ❌ No application tracking or success rate measurement
- ❌ No API for agencies to receive applications

**Why This Matters:**
- **Tutor value:** Makes applying faster and easier (competitive advantage)
- **Data moat:** Track application success rates, optimize matching
- **Agency leverage:** Become visible and valuable to agencies, enabling monetization
- **Market intelligence:** Understand which assignments fill fastest, tutor-agency fit

**Implementation Tasks:**

#### 3.1: Application Storage & Management
**Effort:** 3-4 days  
**Priority:** P0

**Database Schema:**
```sql
-- Store tutor applications
create table public.tutor_applications (
  id bigserial primary key,
  user_id bigint not null references public.users(id),
  assignment_id bigint not null references public.assignments(id),
  application_method text not null, -- 'one_click' | 'external'
  applied_at timestamptz not null default now(),
  
  -- One-click specific fields
  tutor_message text,
  tutor_phone text,
  tutor_email text,
  tutor_qualifications jsonb,
  
  -- Outcome tracking
  status text default 'pending', -- pending | contacted | rejected | accepted | expired
  contacted_at timestamptz,
  outcome_reported_at timestamptz,
  outcome_notes text,
  
  -- Delivery tracking
  delivered_to_agency_at timestamptz,
  delivery_method text, -- 'api' | 'email' | 'telegram' | 'manual'
  agency_response_at timestamptz,
  
  meta jsonb
);

create index idx_tutor_applications_user on public.tutor_applications(user_id, applied_at desc);
create index idx_tutor_applications_assignment on public.tutor_applications(assignment_id, applied_at desc);
create unique index idx_tutor_applications_unique on public.tutor_applications(user_id, assignment_id);
```

**Files to create:**
- `TutorDexAggregator/supabase sqls/2026-01-10_tutor_applications.sql`

#### 3.2: One-Click Apply UI
**Effort:** 4-5 days  
**Priority:** P0

**Frontend Components:**

```javascript
// New: One-Click Apply Button (in assignment card)
// Shows when user is logged in and has complete profile

<button class="one-click-apply-btn">
  ⚡ Quick Apply
</button>

// Clicking opens modal:
// - Pre-fills tutor name, phone, email, qualifications from profile
// - Shows optional message field
// - Preview of what will be sent to agency
// - "Send Application" button

// On submit:
POST /me/assignments/{assignment_id}/apply
{
  method: "one_click",
  message: "...",
  confirm_contact_info: true
}

// Success → show confirmation, emit event
// Failure → show error, retry option
```

**Files to modify:**
- `TutorDexWebsite/src/page-assignments.js`
- `TutorDexWebsite/src/components/OneClickApplyModal.js` (new)
- `TutorDexWebsite/assignments.html` (add modal markup)

**UX Considerations:**
- Require complete profile (phone, email, qualifications)
- Show "Complete profile to enable Quick Apply" if incomplete
- Show applied state on cards ("✓ Applied 2 hours ago")
- Prevent duplicate applications (gray out button if already applied)
- Track external applies too (manual "I applied" button)

#### 3.3: Backend Application API
**Effort:** 3-4 days  
**Priority:** P0

```python
# In TutorDexBackend/app.py

@app.post("/me/assignments/{assignment_id}/apply")
def apply_to_assignment(assignment_id: int, req: ApplicationRequest):
    # 1. Verify user is authenticated
    # 2. Load user profile (require phone/email)
    # 3. Load assignment details
    # 4. Check for duplicate application
    # 5. Store application in tutor_applications
    # 6. Queue application for delivery (see 3.4)
    # 7. Emit analytics event (assignment_apply_submit)
    # 8. Return success + application_id

@app.get("/me/applications")
def get_my_applications():
    # Return user's application history
    # Include assignment details, status, outcome

@app.post("/me/applications/{application_id}/outcome")
def report_application_outcome(application_id: int, req: OutcomeRequest):
    # Tutor reports outcome (contacted/rejected/accepted)
    # Update status, emit analytics event

@app.post("/agencies/{agency_id}/applications/webhook")
def agency_application_webhook(agency_id: int, req: AgencyApplicationCallbackRequest):
    # (Future) Agency reports application status
    # Update tutor_applications.agency_response_at
```

**Files to modify:**
- `TutorDexBackend/app.py`
- `TutorDexBackend/supabase_store.py` (add application methods)

#### 3.4: Application Delivery System
**Effort:** 3-4 days  
**Priority:** P1

**Initial delivery method: Email relay**

```python
# New worker: application_delivery_worker.py

# Polls tutor_applications where delivered_to_agency_at is null
# For each pending application:
#   1. Load assignment + agency contact info
#   2. Format email:
#      To: agency_email (from agency registry)
#      Subject: "New Tutor Application for Assignment #{external_id}"
#      Body:
#        - Assignment details
#        - Tutor details (name, phone, email, qualifications)
#        - Tutor message
#        - "Reply-to" tutor email
#        - "Powered by TutorDex" footer (with tracking pixel)
#   3. Send via SMTP/SendGrid
#   4. Update delivered_to_agency_at
#   5. Emit metric (application_delivered)
```

**Files to create:**
- `TutorDexBackend/workers/application_delivery_worker.py`
- `TutorDexBackend/email_delivery.py` (SMTP wrapper)

**Environment variables:**
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`
- `FROM_EMAIL` (e.g., `applications@tutordex.sg`)
- `APPLICATIONS_DELIVERY_ENABLED` (feature flag)

**Future enhancements (post-milestone):**
- Agency API for programmatic application delivery
- Telegram bot DM to agency contacts
- SMS delivery for urgent assignments
- Agency dashboard to view/manage applications

#### 3.5: Application Analytics & Reporting
**Effort:** 2-3 days  
**Priority:** P1

**New analytics events:**
```javascript
assignment_apply_submit   // One-click apply submitted
application_delivered     // Delivered to agency (server-side)
application_contacted     // Agency contacted tutor (tutor-reported)
application_rejected      // Application rejected (tutor-reported)
application_accepted      // Tutor got the job (tutor-reported)
```

**KPI Queries:**
- Application volume (daily/weekly, by agency)
- Application success rate (contacted / submitted)
- Time to contact (applied → contacted)
- Agency response rate
- Tutor application patterns (frequency, timing)

**Grafana Dashboard Updates:**
- Add "Application Funnel" panel to Product Analytics dashboard
- Add "Agency Performance" panel (applications per agency, response rates)

**Success Metrics for Milestone 3:**
- [ ] One-click apply works end-to-end (UI → backend → delivery → tracking)
- [ ] 20%+ of applications use one-click apply (vs external)
- [ ] Applications delivered to agencies within 5 minutes
- [ ] Can measure application success rate per agency
- [ ] Tutors report faster/easier application experience
- [ ] Agencies are aware that applications come through TutorDex

**Estimated Total Effort:** 3-4 weeks (one developer)

---

### **Milestone 4: Soft Monetization & Tutor Segmentation** 💰

**Goal:** Validate willingness to pay without alienating free users. Build infrastructure for tiered features.

**Current State:**
- ❌ No payment integration
- ❌ No premium features
- ❌ No user tiers (free vs paid)
- ❌ No pricing page or upgrade flow

**Why This Matters:**
- **Revenue:** Start offsetting infrastructure costs
- **Product validation:** Prove tutors see enough value to pay
- **Feature experimentation:** Learn which premium features resonate
- **Agency pitch:** Show financial sustainability when approaching agencies

**Implementation Tasks:**

#### 4.1: User Tier System
**Effort:** 2-3 days  
**Priority:** P0

**Database Schema:**
```sql
-- Add tier tracking to users table
alter table public.users
  add column tier text default 'free', -- free | supporter | premium
  add column tier_started_at timestamptz,
  add column tier_expires_at timestamptz,
  add column payment_provider text, -- stripe | paypal | paynow | manual
  add column payment_reference text;

-- Payment history
create table public.payments (
  id bigserial primary key,
  user_id bigint not null references public.users(id),
  amount_cents int not null,
  currency text not null default 'SGD',
  payment_provider text not null,
  payment_reference text not null,
  payment_status text not null, -- pending | completed | failed | refunded
  tier_granted text, -- supporter | premium
  tier_duration_days int,
  processed_at timestamptz default now(),
  meta jsonb
);
```

**Tier Definitions:**

| Feature | Free | Supporter ($5/mo) | Premium ($15/mo) |
|---------|------|-------------------|------------------|
| Assignment access | ✅ Full | ✅ Full | ✅ Full |
| Basic filtering | ✅ | ✅ | ✅ |
| DM notifications | ✅ (delayed 10min, max 10/day) | ✅ (instant, max 30/day) | ✅ (instant, unlimited) |
| Distance-based filtering | ❌ | ✅ (±5km) | ✅ (±1km) |
| Rate threshold filter | ❌ | ✅ (min $25/hr) | ✅ (custom) |
| Assignment ranking | Basic | ✅ Enhanced | ✅ Premium |
| Historical data | 7 days | 30 days | Unlimited |
| Market intelligence | ❌ | ❌ | ✅ (competitiveness, benchmarks) |
| Priority support | ❌ | ❌ | ✅ |
| Badge on profile | ❌ | ⭐ Supporter | 💎 Premium |

**Files to create:**
- `TutorDexAggregator/supabase sqls/2026-01-15_user_tiers.sql`

#### 4.2: Payment Integration (Start with Manual/Simple)
**Effort:** 3-4 days  
**Priority:** P0

**Phase 1: Manual/PayNow (MVP)**
- Don't integrate Stripe/PayPal initially (complex, overhead)
- Start with manual verification:
  1. Tutor clicks "Upgrade to Supporter" on website
  2. Shows instructions:
     ```
     Transfer $5 SGD to:
     PayNow: 91234567
     Reference: [USER_ID]-SUPPORTER-JAN2026
     
     Then send proof of payment to: payment@tutordex.sg
     or Telegram: @TutorDexSupport
     
     Your account will be upgraded within 24 hours.
     ```
  3. Admin manually verifies payment (via bank notifications)
  4. Admin runs script: `python scripts/upgrade_user.py --user-id 123 --tier supporter --days 30`
  5. Script updates database, sends confirmation email/DM

**Phase 2: Automated (later)**
- Integrate Stripe Checkout for international cards
- Add PayPal for alternative payment method
- Auto-verify PayNow via bank API (if available)

**Files to create:**
- `scripts/upgrade_user.py` (manual tier management)
- `TutorDexWebsite/pricing.html` (new page)
- `TutorDexWebsite/src/page-pricing.js`

#### 4.3: Premium Feature Implementation
**Effort:** 4-5 days  
**Priority:** P1

**Backend Changes:**

```python
# In TutorDexBackend/app.py

def _user_tier(request: Request) -> str:
    uid = _get_uid(request)
    if not uid:
        return "free"
    tier = sb.get_user_tier(firebase_uid=uid)
    # Check expiry
    if tier["tier_expires_at"] and tier["tier_expires_at"] < datetime.now():
        return "free"
    return tier["tier"]

@app.get("/assignments")
def list_assignments(...):
    tier = _user_tier(request)
    
    # Apply tier-based limits
    if tier == "free":
        # Limit to last 7 days
        # Basic sorting only
        # No distance filtering
    elif tier == "supporter":
        # Last 30 days
        # Enhanced sorting (match score boost)
        # Distance ±5km
    # Premium gets everything

# DM delivery changes
# In TutorDexAggregator/workers/extract_worker.py or matching logic

def get_dm_recipients(assignment, matched_tutors):
    # Sort by tier: premium first, then supporter, then free
    # Apply daily caps per tier
    # Apply delivery delays (free = 10min, others = instant)
```

**Frontend Changes:**

```javascript
// In page-profile.js: show tier badge
// In page-assignments.js: show tier-gated features with upgrade prompt
// In pricing.html: comparison table, upgrade buttons

// Upgrade prompt modal:
if (user.tier === "free" && user_wants_premium_feature) {
  showModal({
    title: "Upgrade to Supporter",
    body: "Distance filtering is available for Supporter tier ($5/month)",
    actions: ["View Plans", "Cancel"]
  });
}
```

**Files to modify:**
- `TutorDexBackend/app.py`
- `TutorDexBackend/supabase_store.py` (add tier methods)
- `TutorDexBackend/matching.py` (tier-aware ranking)
- `TutorDexAggregator/dm_delivery.py` (tier-aware caps/delays)
- `TutorDexWebsite/src/page-assignments.js`
- `TutorDexWebsite/src/page-profile.js`

#### 4.4: Tier Analytics & Monitoring
**Effort:** 2 days  
**Priority:** P1

**New Metrics:**
- Conversion rate (free → supporter, free → premium)
- Upgrade triggers (which feature prompted upgrade?)
- Churn rate (paid → free)
- Revenue metrics (MRR, LTV)

**New Analytics Events:**
```javascript
tier_upgrade_viewed    // User viewed pricing page
tier_upgrade_started   // User clicked upgrade button
tier_upgrade_completed // Payment processed
tier_downgrade         // User cancelled/expired
feature_gated_shown    // User hit tier gate, saw upgrade prompt
```

**Grafana Dashboard Updates:**
- Add "Monetization" panel: tier distribution, conversion funnel, MRR trend

**Success Metrics for Milestone 4:**
- [ ] Payment flow works end-to-end (manual or automated)
- [ ] 5%+ of active tutors upgrade to paid tier
- [ ] No significant churn/complaints from free users
- [ ] Premium features demonstrably valuable (usage analytics)
- [ ] Revenue covers at least 50% of infrastructure costs
- [ ] Clear data on which features drive upgrades

**Estimated Total Effort:** 2-3 weeks (one developer)

---

## Summary Roadmap

| Milestone | Focus | Duration | Key Outcome |
|-----------|-------|----------|-------------|
| **Milestone 1** | Aggregation Accuracy | ✅ **Complete** | Reliable multi-channel aggregation, tutors trust TutorDex as legitimate source |
| **Milestone 2** | Product Analytics | 2-3 weeks | Understand tutor behavior, validate discovery loop, data-driven decisions |
| **Milestone 3** | One-Click Apply | 3-4 weeks | Applications flow through TutorDex, build leverage with agencies |
| **Milestone 4** | Soft Monetization | 2-3 weeks | Validate willingness to pay, offset costs, segment users |

**Total estimated time for Milestones 2-4:** 7-10 weeks (one full-time developer)

---

## Critical Path: What to Build First

**Week 1-2: Milestone 2.1 (Frontend Events)**
- Most critical: can't make decisions without data
- Unblocks everything else
- Fast to implement, high leverage

**Week 3-4: Milestone 2.2 (Tutor Feedback UI)**
- Essential for loop validation
- Proves (or disproves) product-market fit
- Informs Milestone 3 design

**Week 5-6: Milestone 2.3-2.4 (KPI Dashboard + Backend)**
- Solidifies analytics foundation
- Makes data actionable

**Week 7-9: Milestone 3.1-3.3 (One-Click Apply Core)**
- Biggest strategic priority
- Builds agency leverage
- Competitive moat

**Week 10-12: Milestone 3.4-3.5 (Application Delivery)**
- Completes the application loop
- Starts providing measurable value to agencies

**Week 13-15: Milestone 4 (Monetization)**
- Can overlap with Milestone 3
- Start with manual payments (low risk)
- Proves financial viability

---

## Risk Mitigation

**Milestone 2 Risks:**
- **Risk:** Tutors don't use reporting features  
  **Mitigation:** Make it dead simple (1-click actions), provide incentives (better matches), show impact ("Your report helped 5 other tutors avoid this scam")

- **Risk:** Analytics show poor engagement/loop  
  **Mitigation:** This is actually GOOD to know early. Pivot to fix core issues before scaling.

**Milestone 3 Risks:**
- **Risk:** Agencies reject applications from TutorDex  
  **Mitigation:** Start with friendly agencies, clearly label source, professional email formatting

- **Risk:** Tutors don't use one-click apply  
  **Mitigation:** Make it genuinely easier/faster than copying phone numbers, pre-fill everything, mobile-optimized

- **Risk:** Email delivery fails/gets spam-filtered  
  **Mitigation:** Use reputable SMTP (SendGrid), warm up sending domain, monitor bounce rates, add SPF/DKIM/DMARC

**Milestone 4 Risks:**
- **Risk:** Nobody pays, free tier is "good enough"  
  **Mitigation:** Start with soft ask ("buy me a coffee"), add genuinely valuable premium features (not just cosmetic), learn from data

- **Risk:** Paid users churn after first month  
  **Mitigation:** Over-deliver on premium features, provide exceptional support, regular feature updates

---

## Beyond Milestone 4: Future Horizons

**Milestone 5: Agency API & Dependence** (3-4 weeks)
- Agency-facing API for receiving applications programmatically
- Agency dashboard (view applications, respond, analytics)
- Measure agency dependence (% of filled assignments from TutorDex)

**Milestone 6: Market Intelligence Premium** (2-3 weeks)
- Advanced analytics for premium tutors (competitiveness scores, demand forecasts)
- Personalized recommendations ("You're more likely to get this type of assignment")
- Time-slot optimization ("Best time to apply for max response rate")

**Milestone 7: Commission/Revenue Negotiation** (ongoing)
- Approach agencies with proof of value (fill rates, application volume)
- Negotiate commissions (5-10% of first month's tuition)
- Agency premium tier (promoted listings, priority placement)

**Milestone 8: Scale & Automation** (3-4 weeks)
- Automated agency onboarding
- Self-serve agency dashboard
- Automated financial reporting and invoicing
- Scale to 1000+ active tutors, 10+ agencies

---

## Conclusion

**You've built the hard part:** The technical infrastructure is solid, reliable, and production-ready. The observability stack ensures you'll catch issues before they become critical. The architecture is clean and maintainable.

**Now build the product layer:** Milestones 2-4 are about understanding users, proving value, and building the leverage needed to monetize sustainably.

**The winning move:** Execute Milestone 2 FAST. Get data flowing. Validate (or invalidate) assumptions. Make decisions based on evidence, not intuition.

**You're at the inflection point.** The aggregator phase is done. The tutor behavior shift phase begins now. Focus on making TutorDex indispensable to tutors, then use that leverage to monetize agencies.

---

## Appendix: Quick Wins (Parallel to Milestones)

These are small enhancements that don't belong to any specific milestone but add polish:

1. **Email notifications** (supplement DMs): weekly digest of matched assignments
2. **Push notifications**: web push for assignments (when tutors browse website)
3. **Mobile app** (React Native): faster access, better UX than mobile web
4. **WhatsApp bot**: alternative to Telegram DMs (if SG tutors prefer WhatsApp)
5. **Assignment quality score**: show "high confidence" vs "may be duplicate/scam" badges
6. **Tutor community**: Telegram group for tutors to share tips, experiences
7. **Referral program**: "Invite 3 tutors, get 1 month premium free"
8. **Assignment alerts**: custom alerts ("tell me when assignment in Bedok with rate >$30 appears")
9. **Agency ratings**: let tutors rate agencies (response time, professionalism)
10. **Success stories**: showcase tutors who got jobs through TutorDex (social proof)

---

**Document Maintainer:** GitHub Copilot  
**Next Review Date:** After Milestone 2 completion  
**Feedback:** Open an issue or PR to update this roadmap as priorities evolve.
