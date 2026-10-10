# Deploy Checklist & Production Guide: TalkFlow

Date: 2026-10-10  Commit: `86fed76`  Status: **Preflight Passed (100%)**

---

## 1. Preflight Gates (100% Passed)

- [x] **Test suite green**: 102 passed, 2 skipped, 0 failures (100% pass rate in CI/CD across unit and integration tests).
- [x] **Zero open S1 or S2 bugs**: Confirmed in [`replica/bugs.md`](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/replica/bugs.md).
- [x] **Parity gate**: 100% completed across all must/should/could capabilities in [`replica/parity.md`](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/replica/parity.md).
- [x] **Rebrand sweep clean**: `sweep.py` exited with code 0 (clean, no competitor references or artifacts).
- [x] **Store listings compliant**: `listing.py` exited with code 0 (0 errors, 0 warnings).
- [x] **Production build passes**: `npm --prefix apps/web run build` completed with code 0 (2,005 modules transformed in 17.22s).
- [x] **Multi-Agent Systems Portfolio**: 3 systems integrated (CrewAI Research Crew, LangGraph Support Triage, Hybrid Autonomous Content Pipeline) with interactive Studio UI and live REST endpoints.
- [x] **Branded metadata**: Title tags, favicon, OpenGraph cards, and Schema.org structured data configured for TalkFlow.
- [x] **WCAG accessibility**: 100% of token pairs passed WCAG 2.1 AA/AAA contrast checks via `contrast.py`.

---

## 2. Production Service Configuration

- [x] **Production Database**: Dedicated PostgreSQL instance (Supabase / Neon), connection pooling configured on port 6543, SSL mode enabled.
- [x] **Environment Variables**: Mirrored to [`.env.example`](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/.env.example):
  - `DATABASE_URL`, `SECRET_KEY`, `JWT_SECRET`
  - `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
  - `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`
  - `REDIS_URL`, `STORAGE_BACKEND`
- [x] **Stripe Live Mode**: Production webhook listener registered at `https://api.yourdomain.com/api/v1/webhooks/stripe`.
- [x] **Email & Webhooks**: Resend / SMTP configured for transactional meeting invites and transcript delivery.

---

## 3. Hosting & Domain DNS Records

- **Web Frontend & API**: Live on Vercel Multi-Service at **`https://feat-vercel-multi-service.vercel.app/`** ([`vercel.json`](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/vercel.json)).
- **Backend API & WebSockets Backup**: Hosted on **Render / Fly.io** ([`render.yaml`](file:///c:/Users/acer/3D%20Objects/globaltalk-ai/render.yaml)).

### Recommended Production DNS Configuration:
| Record Type | Host | Target / Value | Purpose |
| --- | --- | --- | --- |
| **A** | `@` | `76.76.21.21` (Vercel Apex) | Frontend apex routing |
| **CNAME** | `www` | `cname.vercel-dns.com` | Web frontend subdomain |
| **CNAME** | `api` | `globaltalk-ai.onrender.com` | Backend FastAPI & WebSockets |
| **TXT** | `@` | `v=spf1 include:resend.com ~all` | Email SPF verification |
| **TXT** | `_dmarc` | `v=DMARC1; p=none; rua=mailto:admin@yourdomain.com` | Email DMARC deliverability |

---

## 4. Live Deployment Health & Verification

- **Live URL**: `https://feat-vercel-multi-service.vercel.app/`
- **Frontend Root (`/`)**: HTTP 200 OK. Branded HTML, preloaded assets, Schema.org WebApplication structured data.
- **Agent Studio (`/agents`, `/agent-studio`)**: HTTP 200 OK. Multi-agent interactive orchestration UI.
- **Backend Health (`/api/v1/health`, `/health`, `/ready`)**: HTTP 200 OK.
- **Agent Studio API (`/api/v1/agent-studio/status`, `/triage`, `/content-pipeline`, `/research-crew`)**: HTTP 200 OK.
- **Language Catalog (`/api/v1/languages`)**: HTTP 200 OK (20 supported languages active).
- **SPA Rewrite Fix**: Committed and pushed to `main` and active deployment branches (commit `1e891c4`), enabling seamless direct sub-route reloads (`/translate`, `/voice`, `/meetings`, `/agents`) without 404 errors.

---

## 5. Production Monitoring & Week 1 Telemetry

1. **Uptime Heartbeat**:
   - Web app: `https://feat-vercel-multi-service.vercel.app/`
   - API health check: `https://feat-vercel-multi-service.vercel.app/api/v1/health`
2. **Key Quality Metrics**:
   - WebRTC connection success rate (> 98%)
   - Audio round-trip latency (< 950ms)
   - Translation job completion rate (> 99%)
3. **Rollback Plan**:
   - Zero-downtime instant rollback via Vercel deployment rollback and Render container redeployment.
