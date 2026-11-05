# Meridian Retail Platform

A local, end-to-end build of **Meridian**, the fictional retailer from the Scaler
AI Forward Deployed Engineer programme. It starts with the data and ingestion
work from Modules 1–2 and grows module by module into the full platform: backend,
dashboard, RAG support assistant, agent, then Kubernetes and AWS.

Everything runs on your laptop. AWS is emulated by **[Floci](https://github.com/floci-io/floci)**
(free, no account or auth token), so the same boto3 code later points at real AWS
by changing one environment variable.

```
             ┌──────────── docker compose ─────────────┐
 CSV drop ─► │  Floci  S3  s3://meridian-landing/DATE/ │
             │        │                                │
             │        ▼                                │
             │  meridian ingest  (Python, rules VR-*)  │
             │        │                                │
             │        ▼                                │
             │  MySQL 8.4                              │
             │   ├─ meridian_landing  (runs, staging,  │
             │   │                     review, rejects)│
             │   └─ meridian_retail   (trusted, seeded │
             │                         from course SQL)│
             └─────────────────────────────────────────┘
```

## Prerequisites (MacBook, Apple silicon)

- Docker Desktop (or OrbStack) running
- [uv](https://docs.astral.sh/uv/): `brew install uv`
- Optional: AWS CLI for poking at Floci: `brew install awscli`

## Quick start

```bash
cp .env.example .env
make up            # MySQL + Floci; first start seeds 20,000 orders (~30–60 s)
make sync          # install Python deps into .venv
make trusted-check # proves the course database is loaded
make upload        # put data/landing/*.csv into Floci S3
make ingest        # validate the S3 delivery and write results to MySQL
make ingest        # run it again: status DUPLICATE, nothing double-counted
```

Then look around:

- Floci console: http://localhost:4566/_floci/ui
- Adminer (DB browser): http://localhost:8080, server `mysql`, user `meridian` / `meridian`
- `uv run meridian runs` lists every ingestion run

## What the pipeline does

Each delivery is evaluated by plain Python rules taken from the Class 5
`validation_rules.csv`. The worst finding decides where the row goes:

| Rule | Check | Route |
|---|---|---|
| VR-001 | `case_id` present | REJECT |
| VR-002 | `case_id` unique (both duplicates fail) | REJECT |
| VR-003 | RETURN/DAMAGE case has an order | REJECT |
| VR-004 | `review_status` is PENDING/APPROVED/REJECTED | REJECT |
| VR-005 | `delivery_date` is YYYY-MM-DD; a failed order blocks its case bundle | REJECT |
| VR-006 | Order and issue delivery dates agree | HUMAN_REVIEW |
| VR-007 | All files and columns exist | PAUSE_LOAD (whole run) |
| VR-008 | Extract newer than 24 h | LOAD_WARNING |
| VR-009 | Same content never published twice | run marked DUPLICATE |

On the sample delivery: orders 8 publish / 1 reject; cases 5 / 1 review / 6
reject; issues 5 / 1 review / 4 reject. `tests/test_pipeline.py` asserts every one.

## Day-to-day commands

| Command | What it does |
|---|---|
| `make test` | Unit tests (no Docker needed; S3 faked with moto, DB is SQLite) |
| `make test-integration` | Real Floci + MySQL end-to-end tests (`make up` first) |
| `make lint` | ruff lint + format check + mypy strict |
| `make ci` | Everything CI runs, locally |
| `make reset` | Wipe volumes and reseed from scratch |

## CI (GitHub Actions)

`.github/workflows/ci.yml` runs on every push and pull request:

1. **quality**: ruff, format check, mypy, unit tests with coverage
2. **integration**: `docker compose up` of the same MySQL + Floci stack, then the
   integration tests. No secrets needed, since Floci has no auth token.
3. **image**: builds the app Docker image so a broken Dockerfile fails the PR

## Repo layout

```
src/meridian/            application code
  config.py              all settings (MERIDIAN_* env vars)
  aws.py                 boto3 clients -> Floci now, AWS later
  ingest/                contracts, rules, pipeline (pure), sources, store
db/mysql/init/           course SQL, runs on first MySQL start
data/landing/            the Class 5 sample delivery
tests/                   unit tests; tests/integration needs the stack
docs/ROADMAP.md          phase-by-phase plan mapped to the curriculum
```

The SQL in `db/mysql/init/` and the CSVs in `data/landing/` come from the course
pack (`FDEProjectOverview`). Keep this repo private if you're not sure the course
allows sharing them.
