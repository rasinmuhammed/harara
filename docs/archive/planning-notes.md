# Planning notes (superseded)

Early synthesis document, kept for reference. The current methodology and
results are in docs/technical_report.md and docs/results_ledger.md.

---

# Harara — Consolidated Plan: One Engine, Multiple Vulnerable Populations

*This is the master synthesis document. It assumes harara-project-writeup.md (technical core) and harara-llm-integration-addendum.md (LLM's real role) as still valid, and replaces the insurance-pivot document (harara-v3-index-pivot.md) with the buyer landscape below, per direct feedback that insurance is not the direction.*

---

## 0. The one-sentence pitch

One calibrated Gulf humid-heat risk engine, one core piece of deep tech, serving multiple populations who are demonstrably and currently under-protected from the same hazard: construction workers, gig delivery riders, and outdoor event participants, sold as an operational decision tool to whoever controls their schedule (a contractor, a delivery platform, an event organizer), not as compliance software and not as insurance.

---

## 1. The core engine (unchanged)

Layers 0–2 from the original write-up stand as designed: public-data ingestion (ERA5, GFS/ECMWF, OTHH METAR), the calibrated bias-correction/downscaling model benchmarked honestly via walk-forward validation against persistence, raw NWP, and climatology, and the physiological risk layer built on public ACGIH/ISO standards. No PHI, no hardware, no individual worker data, in any configuration below.

The LLM's role stays exactly as scoped in the addendum: regulatory/operational-rule extraction from unstructured text (useful across every segment below, each has its own rules, MADLSA's Decision 17/2021 for construction, a platform's own internal duty-of-care policy for delivery, FIFA/event medical protocols for sports), and grounded, tool-using report generation, never free-generated numbers or claims. This is now a supporting capability across all segments, not the product's headline, exactly as you asked.

---

## 2. The landscape: who actually has this problem, with evidence

### 2a. Construction and industrial contractors
Unchanged from the original research: Decision 17/2021 (10am–3:30pm ban, June–September, WBGT stop-work at 32.1°C), documented enforcement (fines, site closures), and the underlying mortality evidence (Pradhan et al., *Cardiology* 2019, on cardiovascular deaths among migrant construction workers). Buyer: HSE managers or, in the reframed version, project directors/cost controllers caring about schedule and labor-hour exposure.

### 2b. App-based delivery/gig riders
Human Rights Watch's June 2026 report, based on February–May 2026 interviews with migrant workers across Qatar, Kuwait, Saudi Arabia, and the UAE, specifically documents bike delivery riders as a population the existing calendar-ban/construction-site framework doesn't reach: no shaded or cooled rest points along delivery routes, device overheating in extreme heat, and platform pressure to keep completing time-sensitive orders during dangerous conditions, with workers reporting dizziness, fainting, and vision distortion from heat. A new ILO convention, adopted the same month, extends occupational safety and health standards to gig/platform workers for the first time, a live, current policy tailwind. Buyer: the delivery platform itself (Snoonu, a Qatari-founded platform, or regional players like Talabat), not the individual rider, structurally a single decision-maker per company rather than hundreds of fragmented contractors.

### 2c. Outdoor major events and organized sport
Qatar's own bid to host the 2036 Olympics explicitly proposes moving the Games to fall specifically because of heat risk. There's active, current academic literature (Mullan et al., *International Journal of Biometeorology*, 2025) modeling heat-risk implications for FIFA World Cup match scheduling, explicitly using the 2022 Qatar tournament's move from summer to winter as the reference case. Qatar has an existing, credible, high-prestige potential partner in this exact space: Aspetar, Qatar's specialist sports medicine hospital, which already provides on-site medical coverage for major tournaments hosted in the country. Buyer: event organizers, sports federations, or a partnership/credibility relationship with a body like Aspetar rather than a direct commercial sale initially.

### 2d. Weaker-evidenced, not yet verified this round
Aviation (heat's effect on aircraft performance/payload at Hamad International) and utility grid-demand forecasting (Kahramaa) remain plausible from earlier reasoning in this conversation but haven't had a fresh research pass. Don't treat them as validated to the same standard as 2a–2c yet.

---

## 3. Why this is genuinely a stronger "impact + profit" story than either compliance or insurance

QSTP's own $30 million Tech Venture Fund criteria explicitly target startups "delivering measurable social and climate impact" alongside commercial potential, and defines deep tech partly as work built on defensible technical novelty with real-world stakes. A single-hazard engine that demonstrably protects multiple populations HRW and the ILO have independently and recently flagged as under-protected, sold as an operational tool the buyer actually wants (schedule reliability, rider safety, event continuity) rather than a regulatory obligation they resent, is a materially better fit for that criteria than either a compliance checkbox tool or an insurance instrument. It's also a more honest impact story: you're not selling risk transfer after the fact (insurance) or a paperwork trail (compliance), you're selling the thing that changes the actual decision, when to work, when to rest, when to deliver, before the harm happens.

---

## 4. Recommended sequencing

**First: gig delivery platforms.** Fastest sales cycle (one company, one decision-maker), freshest and most current evidence base, and a founder-to-founder relationship rather than an outsider cold-calling an established industry. The product: a real-time-plus-forecast risk signal the platform's own dispatch system consumes to throttle non-essential deliveries, redirect riders to cooling points, or adjust incentive structures during dangerous windows, protecting riders while preserving delivery-SLA reliability for the business. This is the wedge, and it also generates the first real outcome data (forecast vs. actual conditions, decisions taken vs. incidents avoided) that strengthens every later pitch.

**Second: construction**, as already fully scoped in the original write-up, larger potential contract sizes, slower sales cycle, deepest existing technical validation.

**Third, as flagship credibility rather than early revenue: events and sport.** This is the story that gets press and funding attention, "the country that moved a World Cup for heat is building the forecasting infrastructure for the next one", pursued through a partnership or research relationship with a body like Aspetar rather than a cold commercial pitch, and not treated as a near-term revenue line.

---

## 5. What's still genuinely open

- Direct validation with a real delivery platform (Snoonu or similar) that this operational framing, throttling/routing decisions rather than compliance or insurance, is something they'd actually pay for or pilot. This hasn't been tested in a real conversation yet.
- Which Layer 1 backbone wins the walk-forward benchmark (gradient-boosted baseline vs. foundation-model-conditioned vs. the frequency-aware hybrid architecture) is still an open empirical question, not yet run.
- Aviation and grid-demand segments remain unverified hypotheses, not validated opportunities, don't build for them yet.
