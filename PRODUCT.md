# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React + Vite (user-confirmed). Served alongside or proxied to the existing FastAPI Code2Guide API (`/api/v1/*`). Static HTML at `src/api/static/index.html` is the incumbent surface being replaced for this UI shell.

## Users

Primary: mixed audience on one shell —
- **End users** (non-technical operators) who need simple step-by-step Persian UX guides without files, APIs, or citations.
- **Developers / support / technical staff** who need the same guides plus route/form signals, breadcrumbs, and technical grounding.

Situation: someone has a question about how to do a task in an enterprise codebase/app and uses Code2Guide instead of reading source or tribal knowledge.

## Product Purpose

Code2Guide turns a Persian natural-language question about an indexed codebase into a step-by-step Persian UX guide. Success = the user can complete the task in the target app without digging through code.

## Positioning

Unlike generic chat or docs bots, Code2Guide indexes frontend + .NET backend into a knowledge graph (routes, forms, APIs, services, entities, field maps) and answers from that structure — with a dedicated end-user mode that strips technical detail.

## Operating Context

- FastAPI service with `/api/v1/ask`, `/api/v1/ask-enduser`, `/api/v1/index-workspace`, `/api/v1/index/status`, and related trace endpoints.
- Target workspaces are enterprise codebases (sample React FE + .NET backend / MVC portal).
- UI is RTL Persian; Markdown guides are rendered for reading.
- Operators may optionally set a workspace path and trigger indexing before asking.

## Capabilities and Constraints

Confirmed in-product for this UI shell:
- Ask (technical audience) via `POST /api/v1/ask`
- Ask end-user via `POST /api/v1/ask-enduser`
- Index workspace via `POST /api/v1/index-workspace`
- Show guide as Markdown (RTL), plus lightweight meta (routes/forms/breadcrumbs when present)
- Optional workspace path override

Constraints:
- Do not invent customers, benchmarks, or pricing.
- Guides and index stats come from the live API; empty/error/loading states must be honest.
- Persian RTL is required for primary chrome and guide reading.
- Stack for this surface: React + Vite (not a rewrite of the Python agent).

Undecided (explicit): exact deploy packaging (separate Vite build vs FastAPI-served assets) — prefer Vite dev proxy to API; production can mount built assets when chosen later.

## Brand Commitments

- Product name: **Code2Guide**
- Voice: clear, instructional Persian; no hype
- Dual-audience switch is a confirmed product requirement for this shell

## Evidence on Hand

- Live API contracts in `src/api/routes.py`
- Incumbent viewer: `src/api/static/index.html` (evidence of current task flow; not visual authority for redesign)
- Sample workspace under `sample_workspace/` for demos
- No customer logos, testimonials, or marketing assets — do not fabricate them

## Product Principles

1. **Audience honesty** — technical and end-user modes must feel deliberately different in tone of results, not just a label flip.
2. **Guide is the product** — the reading experience of the generated Markdown is the primary surface, not chrome.
3. **Index before ask when needed** — indexing is a first-class operator action, not a hidden admin detail.
4. **Persian-first RTL** — layout, type, and reading direction serve Persian operators by default.
5. **No fake proof** — only show routes/forms/breadcrumbs/index stats the API actually returns.

## Accessibility & Inclusion

Persian RTL primary; keep focus states, form labels, and live regions for status/errors. No product-specific WCAG tier mandated yet — follow sensible defaults.