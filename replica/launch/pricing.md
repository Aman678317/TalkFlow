# Transparent Pricing Architecture: TalkFlow

## 1. Where this pricing came from

We publish our own numbers. We do not publish characterisations of named
competitors.

An earlier version of this table listed other vendors' prices and a "Caveats &
Customer Complaints" column asserting weaknesses about DeepL, Zoom AI Companion
and Interprefy/Kudo. None of it had a source, a date, or a screenshot, and the
review corpus that was cited elsewhere as its basis turned out to be fabricated
(see `../feedback.md`). Asserting unverified defects about a named competitor is
an unfair-competition and disparagement exposure, not market research, so the
rows are gone.

What remains defensible:

| Provider | Public Pricing Model | Lowest Paid Plan | Enterprise Tier | Caveats & Customer Complaints |
| --- | --- | --- | --- | --- |
| **TalkFlow** | **Self-serve monthly / annual plans** | **$19 / month flat** | **$49 / team** | **Zero per-guest fees, 1-click self-serve cancellation** |

If a competitive comparison is wanted in public material, it has to be built from
each vendor's own published pricing page, captured with the URL and the date it
was read, and limited to what that page states — no inferred complaints.

---

## 2. TalkFlow Pricing Tiers

### Free Tier: $0 / month
- 60 audio translation minutes per month
- 100,000 characters of text / writing translation
- Unlimited 1-on-1 meetings (up to 30 mins/session)
- 3 document translation jobs per month
- Community support

### Pro Tier: $19 / month ($15/mo billed annually)
- **Target**: Global consultants, freelancers, sales representatives
- 300 audio translation minutes per month
- Unlimited text translation & AI writing polish
- Unlimited video meetings with up to 10 participants
- 25 layout-preserved document translations (PDF/DOCX) per month
- 5 custom domain glossaries
- Full SRT/VTT transcript exports
- Priority streaming bandwidth

### Team Tier: $49 / month ($39/mo billed annually)
- **Target**: Cross-border agencies, distributed engineering & operations teams
- 1,200 shared audio translation minutes per month
- Up to 10 team seats included (no per-seat penalties)
- 100 document translations per month
- Unlimited glossaries and shared translation memory
- Developer API access (60 req/min)
- Admin analytics, audit logs, and priority email support

---

## 3. Stripe Products to Provision
1. `prod_talkflow_pro`: $19/month (`price_talkflow_pro_monthly`) & $180/year (`price_talkflow_pro_annual`)
2. `prod_talkflow_team`: $49/month (`price_talkflow_team_monthly`) & $468/year (`price_talkflow_team_annual`)
