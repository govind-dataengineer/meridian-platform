# Meridian build roadmap

One repo, grown module by module. Every phase ends with tests that pass in CI
and a working `make up`. Tick the boxes as you go; open one PR per checkbox to
practise the Git/GitHub flow (branch → PR → green CI → merge).

Guiding rules that keep it future-proof:

- **Same stack locally and in CI.** CI runs the same `docker-compose.yml`.
- **Config only through env vars** (`MERIDIAN_*`). Floci becomes real AWS by
  clearing `MERIDIAN_AWS_ENDPOINT_URL`, with no code changes.
- **Pure logic, thin I/O.** Rules and decisions are plain functions with unit
  tests; databases, S3 and LLMs sit behind small adapters.
- **Python decides, the model explains.** The deterministic layer you build now
  is what the agent will call as tools later.

---

## Phase 1: Data foundation & ingestion (Modules 1–2) ✅ scaffolded

- [x] MySQL 8.4 seeded with the course `meridian_retail` schema (20k orders, 25k cases)
- [x] Floci S3 landing bucket, `meridian upload`
- [x] Rules VR-001…VR-009 as tested Python, routes to publish / review / reject
- [x] Idempotent, transactional writes + run audit trail
- [x] GitHub Actions: lint, mypy, unit, integration, image build; Dependabot
- [ ] Add the Class 8 migrations (customers, products, case_routes) as numbered init scripts
- [ ] Introduce **Alembic** for the landing schema instead of `create_all`
- [ ] Structured JSON logging (`structlog`) with `run_id` on every line
- [ ] Async/concurrent S3 reads for multi-day backfills (Module 2 concurrency)
- [ ] Optional: PySpark job over a generated 1M-row delivery, writing Parquet to S3

## Phase 2: Backend API (Module 3)

- [ ] `services/api`: **FastAPI** app, OpenAPI contract, `/healthz`
- [ ] Endpoints: orders, cases, review queue (claim / decide), ingestion runs
- [ ] Auth: OAuth2 password flow + JWT; roles `support_agent`, `ops_reviewer`, `admin` (RBAC)
- [ ] Order state machine (PLACED → PAID → SHIPPED → DELIVERED / RETURNED) with tests for illegal transitions
- [ ] Payments + notifications via **Floci SQS/SNS** (outbox pattern so DB and queue never disagree)
- [ ] **Redis** cache for hot reads; Server-Sent Events for live review-queue updates
- [ ] Add **Postgres + pgvector** service: JSONB case notes, full-text search, embeddings later
- [ ] OpenTelemetry traces → Jaeger container; dbt + DuckDB reporting models

## Phase 3: Ops dashboard (Module 4)

- [ ] `apps/web`: React + TypeScript (Vite), typed API client generated from OpenAPI
- [ ] Login, protected routes, KPI tiles (open cases, ageing, review SLA)
- [ ] Review-queue table with filters; decide a VR-006 conflict from the UI
- [ ] Playwright smoke test in CI

## Phase 4: RAG support assistant (Module 5)

- [ ] Knowledge base: return policy, care guides, product catalogue → chunks in pgvector
- [ ] `/assist/answer` endpoint: retrieval + LLM answer **with citations**
- [ ] Model behind an adapter: a local model via Ollama for dev, hosted API optional
- [ ] Versioned prompts in `prompts/`, regression eval set (RAGAS) gated in CI
- [ ] PII redaction before anything reaches the model

## Phase 5: The agent (Module 6)

- [ ] **LangGraph** agent whose tools are your Phase 1–2 functions: look up order,
      check return window, open review, issue refund (needs human approval)
- [ ] Expose the same tools as an **MCP server** so any MCP client can use them
- [ ] Human-in-the-loop: consequential actions land in the review queue, not executed
- [ ] Webhook connector for a "legacy" system (a mock service in compose)
- [ ] Red-team test suite: prompt injection in customer messages must not trigger tools

## Phase 6: Scale & AI platform (Modules 7–8)

- [ ] Black Friday load test (k6/Locust) against the API; rate limiting
- [ ] Kafka (Redpanda container) for order events; saga for order → payment → inventory
- [ ] Model gateway (routing, caching, cost tracking); MLflow for prompt/model runs
- [ ] Evals as a CI job with a pass threshold

## Phase 7: Ship it (Modules 9–11)

- [ ] Multi-stage, non-root images for every service; image scanning (Trivy) in CI
- [ ] Local Kubernetes (kind or k3d) + Helm chart; ArgoCD GitOps
- [ ] Terraform for S3/SQS/RDS/EKS, applied **against Floci first**, then real AWS
- [ ] CI: build → push to ECR → deploy to EKS on tag

## Phase 8: Harden (Modules 12–14)

- [ ] SLOs + alerts; chaos test (kill MySQL, kill a pod) with runbooks in `docs/runbooks/`
- [ ] Secrets via AWS Secrets Manager (Floci locally); OWASP ZAP scan in CI
- [ ] Threat model + incident playbook; final demo script for the capstone
