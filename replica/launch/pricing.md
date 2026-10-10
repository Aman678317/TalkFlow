# Transparent Pricing Architecture: TalkFlow

## 1. Competitive Pricing Benchmark

| Provider | Public Pricing Model | Lowest Paid Plan | Enterprise Tier | Caveats & Customer Complaints |
| --- | --- | --- | --- | --- |
| DeepL Pro | $8.74 to $28.74 / user / month | $8.74 / mo (Advanced: $28.74) | $57.49+ / user | Text/Doc only, no live WebRTC meetings, rigid character limits |
| Zoom AI Companion | $13.33 / host / month (One Pro bundle) | $13.33 / host | $250+ / mo | Limited languages, awkward audio ducking, attendee license walls |
| Interprefy / Kudo | Enterprise quote only | ~$500 – $1,500 / event | Custom contracts | Inaccessible to startups, freelancers, and small cross-border teams |
| **TalkFlow** | **Self-serve monthly / annual plans** | **$19 / month flat** | **$49 / team** | **Zero per-guest fees, 1-click self-serve cancellation** |

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
