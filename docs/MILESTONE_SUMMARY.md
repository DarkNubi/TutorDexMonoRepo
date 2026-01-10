# TutorDex: Next Milestones - Executive Summary

**Date:** January 8, 2026

---

## Current Status: ✅ Milestone 1 Complete

**Achievement:** Aggregation Accuracy
- Multi-channel Telegram aggregation with LLM parsing
- Redis matching engine + Supabase persistence
- Comprehensive observability (Prometheus, Grafana, Loki)
- Firebase-authenticated website with filtering and profile management
- Production-ready infrastructure with automated CI/CD

**What's Working:**
- ✅ Automated message collection from multiple agencies
- ✅ Duplicate detection and quality validation
- ✅ DM delivery to matched tutors
- ✅ Website with advanced filtering and search
- ✅ Full monitoring and alerting (50+ metrics, 17 alerts)

---

## Next Three Recommended Milestones

### 🎯 Milestone 2: Product Analytics & Loop Validation (2-3 weeks)

**Goal:** Understand tutor behavior and validate the product loop works.

**Why:** Currently flying blind - no data on how tutors actually use the product.

**Key Deliverables:**
1. **Frontend analytics events** (list_view, assignment_view, apply_click, preferences_update)
2. **Tutor feedback UI** (report filled/scam/no-reply, hide assignments)
3. **KPI dashboard** (WAU, apply rate, dead-end rate, time-to-fill)
4. **Backend enhancements** (history API, hide/save endpoints)

**Success Metrics:**
- Can answer: "What % of viewed assignments get applied to?"
- Can answer: "What % of applications result in no reply/scam?"
- 10+ tutors use reporting UI weekly
- Data-driven product decisions become possible

---

### 🚀 Milestone 3: One-Click Apply & Application Flow (3-4 weeks)

**Goal:** Route applications through TutorDex to build agency leverage.

**Why:** Currently TutorDex is invisible to agencies - no data moat, no monetization path.

**Key Deliverables:**
1. **Application storage** (tutor_applications table, tracking schema)
2. **One-click apply UI** (modal with pre-filled tutor info)
3. **Backend API** (apply endpoint, application history)
4. **Delivery system** (email relay to agencies, tracking)
5. **Application analytics** (funnel, success rates, agency performance)

**Success Metrics:**
- One-click apply works end-to-end
- 20%+ of applications use one-click (vs external link)
- Applications delivered within 5 minutes
- Can measure success rate per agency
- Agencies become aware of TutorDex traffic

---

### 💰 Milestone 4: Soft Monetization & Tiers (2-3 weeks)

**Goal:** Validate willingness to pay without alienating free users.

**Why:** Need revenue to offset costs and prove financial viability for agency partnerships.

**Key Deliverables:**
1. **User tier system** (free/supporter/premium in database)
2. **Payment flow** (start with manual PayNow, later automate with Stripe)
3. **Premium features** (instant DMs, tighter filters, historical data, market intelligence)
4. **Tier analytics** (conversion rate, MRR, churn, feature gates)

**Tier Comparison:**

| Feature | Free | Supporter ($5/mo) | Premium ($15/mo) |
|---------|------|-------------------|------------------|
| DM notifications | 10/day, 10min delay | 30/day, instant | Unlimited, instant |
| Distance filter | ❌ | ±5km | ±1km |
| Rate filter | ❌ | ≥$25/hr | Custom |
| Historical data | 7 days | 30 days | Unlimited |
| Market intel | ❌ | ❌ | ✅ |

**Success Metrics:**
- 5%+ of active tutors upgrade to paid tier
- No significant free user churn
- Revenue covers 50%+ of infrastructure costs
- Clear data on which features drive upgrades

---

## Estimated Timeline

**Total: 7-10 weeks** (one full-time developer)

```
Week 1-2:   Milestone 2.1 (Frontend Events) ← START HERE
Week 3-4:   Milestone 2.2 (Feedback UI)
Week 5-6:   Milestone 2.3-2.4 (Dashboard + Backend)
Week 7-9:   Milestone 3.1-3.3 (One-Click Apply Core)
Week 10-12: Milestone 3.4-3.5 (Application Delivery)
Week 13-15: Milestone 4 (Monetization)
```

---

## Critical Path: Start with Milestone 2.1

**Why frontend analytics events first?**
- Can't make decisions without data
- Fast to implement (2-3 days)
- Unblocks everything else
- High leverage (informs all future work)

**Implementation:**
```javascript
// TutorDexWebsite/src/page-assignments.js
trackEvent({
  event_type: "assignment_list_view",
  meta: { filters, sort, surface: "website" }
});

trackEvent({
  event_type: "assignment_view",
  assignment_external_id,
  agency_name
});

trackEvent({
  event_type: "assignment_apply_click",
  assignment_external_id,
  agency_name
});
```

---

## What Comes After? (Milestones 5-8)

**M5: Agency API & Dependence** → agencies receive applications via API, dashboard  
**M6: Market Intelligence** → premium analytics, recommendations  
**M7: Commission Negotiation** → monetize agencies (5-10% commission)  
**M8: Scale & Automation** → 1000+ tutors, 10+ agencies

---

## Strategic Positioning

**Where you are now:**
- ✅ Technical foundation complete
- ✅ Infrastructure production-ready
- ✅ Core aggregation working

**Where you need to be:**
- 📊 **Understand user behavior** (Milestone 2)
- 🔗 **Build agency leverage** (Milestone 3)
- 💰 **Prove monetization** (Milestone 4)

**The inflection point:**
You've built the hard part (infrastructure). Now build the product layer that creates value for tutors and leverage with agencies.

---

## Key Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Tutors don't use reporting features | Make it 1-click simple, show impact |
| Low engagement/apply rate | Good to know early, pivot to fix |
| Agencies reject TutorDex applications | Start with friendly agencies, professional formatting |
| Nobody pays for premium | Start soft (buy me coffee), genuine value, learn from data |
| Paid users churn | Over-deliver, exceptional support, frequent updates |

---

## Recommendation

**Execute Milestone 2 immediately.** It's the fastest path to understanding whether the product is working and what needs to change. Everything else depends on having this data.

**Expected outcome after M2-M4:**
- Data-driven product roadmap
- Applications flowing through TutorDex
- Revenue covering infrastructure costs
- Ready to negotiate agency partnerships

---

**Full details:** See [NEXT_MILESTONES.md](NEXT_MILESTONES.md)  
**Questions?** Open an issue or discussion in this repo.
