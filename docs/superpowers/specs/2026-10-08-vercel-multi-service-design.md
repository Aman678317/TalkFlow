# Vercel Multi-Service Deployment Design

## Goal

Deploy the repository's main web frontend, FastAPI API, and Amazon Connect V2V
frontend as independently built services within one Vercel project and shared
domain. Preserve the existing public API paths and make the Connect frontend
work from the `/connect/` path.

## Service topology

| Service | Root | Framework | Public routes |
| --- | --- | --- | --- |
| `web` | `apps/web` | Vite | Catch-all, after more-specific routes |
| `api` | `services/api` | FastAPI | `/api/*`, `/v2/*`, `/v3/*`, `/ws/*`, API docs, health, readiness, and metrics |
| `connect` | `apps/amazon-connect-v2v/webapp` | Vite | `/connect/*` |

The selected API is `services/api`, matching the README's `run_api.py`
launcher. Do not deploy `apps/api` as a second API: it is a separate
implementation and the project has selected `services/api` as authoritative.
The root launcher, `ai` Python package, and `sdk/python/desi-python` SDK are
not independent network services and should not appear as services.

## Routing and service communication

Top-level rewrites send API routes to `api`, `/connect/*` to `connect`, then
all remaining paths to `web`. More-specific rewrites precede the catch-all.
The `/connect/:path*` rewrite selects `/:path*` inside the static service so
Vercel can find files at the service root while the browser-visible URL keeps
the `/connect/` prefix.
The API route list includes legacy `/v2` and `/v3` endpoints and websocket
routes in addition to `/api`, since the FastAPI app exposes all of those at
their current root-level paths.

No service bindings are added. The main browser frontend uses same-origin
public API paths, the AI code is a Python dependency rather than a network
service, and the Connect frontend's session/language proxy URLs are external
AWS Lambda endpoints supplied as Vercel build-time environment variables.
Browser code must not consume service-binding variables.

The Connect Vite build uses `/connect/` as its asset base. Its Lambda URLs
remain deployment configuration, not Vercel service bindings.

## API build integration

The `api` service uses `services/api` and the FastAPI application entrypoint
there. It must install the repository-local Python AI package as a dependency;
the AI directory is not separately exposed as a service.

## Validation

- Validate the Vercel services configuration and local service routing.
- Build both Vite applications with production settings, including the
  `/connect/` base path.
- Run focused API tests for the selected `services/api` application.
- Confirm rewrites cover all existing public API and websocket prefixes.
