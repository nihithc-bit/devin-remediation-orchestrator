# Devin Remediation Orchestrator

> **Event-driven automation that remediates GitHub issues using Devin as the core primitive.**

---

## Problem Statement

Engineering teams label GitHub issues as "easy wins" — lint cleanups, missing type hints, stale comments, small dep bumps — but these never get prioritized over feature work. Thousands of these issues accumulate in any mature codebase.

This system turns the act of labeling an issue into a fully automated Devin remediation pipeline: Devin creates a branch, makes the smallest safe change, runs tests/lint/types, and opens a PR — all without engineer time. A conversational analytics layer (also powered by Devin) lets leadership ask ad hoc questions about remediation performance and get back chart-ready data.

---

## Architecture

```
GitHub Issue Labeled ──────► FastAPI Orchestrator (/webhooks/github)
                                       │
                              Idempotency check
                              Classify (lint/docs/type-hint/dep/bug)
                                       │
                              POST /v1/sessions (Devin API)
                              structured_output_schema enforced ──► Devin Session
                                       │
                              DevinRun created in Postgres
                              GitHub issue comment posted
                                       │
                     ┌─────────────────┴─────────────────┐
                     │                                   │
               Background Worker                  /runs/{id}/refresh
               (polls every 30s)                  (on-demand)
                     │
               GET /v1/sessions/{id} ───► Map Devin status → RunStatus
               structured_output → pr_url, tests_run, risk_level
               GitHub issue updated with final outcome
                     │
               Postgres (devin_runs, devin_events, analytics_queries)
                     │
          ┌──────────┴───────────┐
          │                      │
    Static Dashboard        POST /analytics/query
    (metrics cards,         NL question → Devin (NL→SQL)
     runs table,            → SQL Guard (sqlglot AST)
     throughput chart)      → Read-only Postgres exec
                            → Chart-ready JSON
```

**Two core uses of Devin:**
1. **Remediation engine** — Devin creates branches, fixes code, runs tests, opens PRs
2. **NL→SQL reasoning** — Devin converts leadership questions into safe, validated PostgreSQL

---

## Quickstart

### Prerequisites

- **Docker + Docker Compose**
- **Python 3.10+** (for running `seed/create_issues.py` locally)
- **[gh CLI](https://cli.github.com/)** (`brew install gh`) — for forking the repo
- **[smee-client](https://github.com/probot/smee-client)** (`npm install -g smee-client`) — GitHub's own webhook proxy
- A **Devin API key** (`apk_...`) from [app.devin.ai/settings](https://app.devin.ai/settings)
- A **GitHub personal access token** with `repo` scope

### 1. Clone and configure

```bash
git clone https://github.com/your-org/devin-remediation-orchestrator
cd devin-remediation-orchestrator

cp .env.example .env
# Edit .env — fill in DEVIN_API_KEY, GITHUB_TOKEN, GITHUB_WEBHOOK_SECRET,
# GITHUB_OWNER, GITHUB_REPO. See Environment Variables below.
```

Generate a random webhook secret:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# Paste the output into GITHUB_WEBHOOK_SECRET in .env
```

### 2. Start the stack

```bash
docker compose up
```

Open **http://localhost:8000** — the dashboard loads immediately. No seed data? Trigger a run:

```bash
curl -s -X POST http://localhost:8000/simulate/issue-labeled \
  -H "Content-Type: application/json" \
  -d '{"issue_number": 1, "issue_title": "fix(lint): remove == False in DAOs", "issue_body": "ruff E712 cleanup"}' \
  | python3 -m json.tool
```

This creates a real Devin session. Refresh the dashboard to see it appear, then watch it advance as Devin works.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DEVIN_API_KEY` | Yes | Devin API key (`apk_...`) from app.devin.ai/settings |
| `GITHUB_TOKEN` | Yes | GitHub PAT with `repo` scope |
| `GITHUB_WEBHOOK_SECRET` | Yes | Random secret shared with GitHub webhook (see setup step 1) |
| `GITHUB_OWNER` | Yes | Your GitHub org or username |
| `GITHUB_REPO` | Yes | Repository name (e.g. `superset`) |
| `DATABASE_URL` | No | Read-write Postgres URL (defaults to Docker `postgres` service) |
| `DATABASE_URL_RO` | No | Read-only Postgres URL for analytics queries |
| `MAX_ACU_LIMIT` | No | Max ACUs per Devin session (default: `50`) |
| `AUTO_REMEDIATE_LABEL` | No | Label that triggers automation (default: `devin:auto-remediate`) |
| `POLL_INTERVAL_SECONDS` | No | Worker poll frequency in seconds (default: `30`) |
| `SKIP_WEBHOOK_SIGNATURE` | No | Set `true` when using smee.io (bypasses HMAC check) |

---

## Real Webhook Setup (End-to-End)

GitHub webhooks require a public URL. Since the orchestrator runs on `localhost:8000`, use [smee.io](https://smee.io) — a webhook proxy maintained by GitHub.

### 1. Fork Apache Superset

```bash
gh repo fork apache/superset --clone=false --org <your-github-username-or-org>
# GitHub disables issues on forks by default — enable them:
gh api repos/<your-github-username-or-org>/superset -X PATCH -f has_issues=true
```

Set `GITHUB_OWNER` and `GITHUB_REPO=superset` in your `.env`.

### 2. Grant Devin write access to your fork

Devin needs to push branches and open PRs. Go to
**https://app.devin.ai/settings/repositories** and add `<your-org>/superset`.

> Without this step Devin sessions will run and complete the fix but stall at
> `BLOCKED` when trying to push — you'll see "I don't have write access" in
> the session log.

### 3. Start smee

Open a dedicated terminal and keep it running for the duration of the demo:

```bash
# Create a unique smee channel (one-time — save this URL)
SMEE_URL=$(curl -si https://smee.io/new | grep -i "^location:" | tr -d '\r' | awk '{print $2}')
echo "Smee URL: $SMEE_URL"

# Forward GitHub webhooks to your local stack
smee --url "$SMEE_URL" --target http://localhost:8000/webhooks/github
```

### 4. Register the webhook on GitHub

In your fork → **Settings** → **Webhooks** → **Add webhook**:
- **Payload URL**: the `$SMEE_URL` value from above
- **Content type**: `application/json`
- **Secret**: leave blank (smee re-signs with its own key; set `SKIP_WEBHOOK_SIGNATURE=true` below instead)
- **Events**: select "Let me select individual events" → check **Issues** only

Add to your `.env`:
```
SKIP_WEBHOOK_SIGNATURE=true
```

### 5. Start the stack

```bash
docker compose up
```

Verify it's healthy: `curl http://localhost:8000/health` → `{"status":"ok"}`

### 6. Install seed script dependencies

The seed script runs locally (outside Docker):

```bash
pip install httpx pyyaml
# or, if you prefer a venv:
python3 -m venv .venv && source .venv/bin/activate && pip install httpx pyyaml
```

### 7. Create seed issues

```bash
python seed/create_issues.py
```

Creates 5 issues on your fork, each labeled `devin:auto-remediate`. Every issue immediately fires a webhook → the orchestrator receives it → a Devin session starts.

### 8. Watch it run

Open **http://localhost:8000** — runs appear in the dashboard within seconds of the webhook arriving. Each issue gets a comment from the orchestrator with the Devin session URL. Runs advance to `READY_FOR_REVIEW` (with a real PR link) once Devin finishes.

---

## Simulating a Webhook Locally

```bash
export GITHUB_WEBHOOK_SECRET=your_secret
./scripts/send_test_webhook.sh 42 "fix(lint): remove == False in daos/"
```

Or use the simulate endpoint (no signature required):

```bash
curl -X POST http://localhost:8000/simulate/issue-labeled \
  -H "Content-Type: application/json" \
  -d '{"issue_number": 1, "issue_title": "fix(lint): remove == False"}'
```

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/webhooks/github` | Real GitHub webhook (HMAC-validated) |
| `POST` | `/simulate/issue-labeled` | Local trigger without a real webhook |
| `POST` | `/runs/{run_id}/refresh` | Force-poll a run's Devin session |
| `GET` | `/runs` | List runs (filter: `?status=RUNNING&classification=lint`) |
| `GET` | `/runs/{run_id}` | Run detail + event timeline |
| `GET` | `/metrics/summary` | Success rate, active/completed counts, mean time to PR |
| `GET` | `/metrics/throughput` | Runs/PRs per day or week |
| `GET` | `/metrics/failures` | Failures grouped by reason |
| `POST` | `/analytics/query` | NL question → Devin SQL → chart JSON |
| `GET` | `/` | Dashboard UI |
| `GET` | `/docs` | Swagger API docs |
| `GET` | `/health` | Health check |

### Example curl commands

```bash
# Check run status
curl http://localhost:8000/runs | python3 -m json.tool

# Force-poll a specific run
curl -X POST http://localhost:8000/runs/<run-id>/refresh

# Metrics summary
curl http://localhost:8000/metrics/summary | python3 -m json.tool

# Analytics chatbot
curl -X POST http://localhost:8000/analytics/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Show Devin remediation success rate by week as a graph"}' \
  | python3 -m json.tool
```

---

## Analytics Chatbot — Example Questions

Ask these at `POST /analytics/query` or in the dashboard chat box:

```
Show Devin remediation success rate by week as a graph
How many issues did Devin fix this month?
Show failed Devin sessions by reason
Graph PRs opened per week
Which issue types consume the most ACUs?
What is average time from issue label to PR opened?
Show active Devin sessions
Why did the Devin runs fail?
```

**Why the chatbot matters:** Dashboards answer known KPIs. The chatbot handles ad hoc questions from VPs and directors that no one pre-configured a chart for. Devin is the reasoning primitive — it converts the question into safe SQL, the guard validates it, and the result comes back as chart-ready JSON.

---

## Safety Controls

| Control | Layer | Detail |
|---|---|---|
| Webhook signature | Transport | HMAC-SHA256, constant-time compare |
| Idempotency | Application | Dedup by `X-GitHub-Delivery` header |
| One session per issue | Application | Block if active session already exists |
| ACU budget | Devin API | `max_acu_limit` enforced server-side |
| Max attempts | Application | Configurable `MAX_ATTEMPTS` per run |
| SQL keyword block | Analytics | sqlglot AST — no regex |
| Table whitelist | Analytics | Only 3 tables, hard-coded |
| LIMIT injection | Analytics | Auto-added if missing |
| Read-only DB role | Database | `analytics_ro` has only SELECT grants |
| No auto-merge | Policy | Terminal success = `READY_FOR_REVIEW` |

---

## Running Tests

```bash
# With venv
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest tests/ -v
```

```bash
# Or inside Docker
docker compose run --rm api pytest tests/ -v
```

74 tests covering: SQL guard (all blocked keywords, whitelist, LIMIT injection), state machine (valid/invalid transitions), webhook signature (good/bad/tampered), classifier (10 issue types, priority/risk), analytics keyword matching, Devin client construction, orchestrator label filtering.

---

## Enterprise Extensions (Phase 2)

| Extension | Trigger | Devin task |
|---|---|---|
| Dependabot/Snyk/CodeQL remediation | Security scan alert | Fix CVE or update dep |
| PagerDuty/Datadog incident response | Alert fired | Investigate logs, propose fix |
| CI failure investigation | Test suite fails | Find root cause, open fix PR |
| Release engineering | Tag pushed | Bump versions, update changelog |
| Slack self-service | `/devin fix issue-123` | Trigger remediation from Slack |
| Executive analytics | Scheduled report | Summarize Devin ROI this quarter |
| Org memory | Historical sessions | Build playbooks from past Devin work |

---

## Project Structure

```
devin-remediation-orchestrator/
├── app/
│   ├── main.py            # FastAPI factory, router mounting
│   ├── config.py          # Pydantic Settings (all required fields)
│   ├── db.py              # RW + RO engines, session factories, create_all
│   ├── models.py          # SQLAlchemy ORM (3 tables)
│   ├── schemas.py         # Pydantic models + JSON Schemas for Devin
│   ├── state.py           # RunStatus enum + transition guard
│   ├── prompts.py         # Remediation + analytics prompt templates
│   ├── worker.py          # Background poller (runs as separate container)
│   ├── routers/
│   │   ├── webhooks.py    # POST /webhooks/github + /simulate
│   │   ├── runs.py        # GET/POST /runs
│   │   ├── metrics.py     # GET /metrics/*
│   │   └── analytics.py   # POST /analytics/query
│   ├── services/
│   │   ├── classifier.py       # Pure heuristic issue classifier
│   │   ├── devin_client.py     # Devin v1 API client
│   │   ├── github_client.py    # GitHub REST + HMAC signature verify
│   │   ├── orchestrator.py     # Core webhook → Devin flow
│   │   ├── poller.py           # Session poll + state machine advance
│   │   ├── reporter.py         # GitHub issue comment composer
│   │   ├── sql_guard.py        # sqlglot AST validator (SELECT-only)
│   │   └── analytics_queries.py # Keyword-matched SQL fallback
│   └── static/index.html  # Single-page dashboard + chatbot (Chart.js)
├── seed/
│   ├── seed_issues.yaml   # 5 curated Superset issues for Devin
│   └── create_issues.py   # Creates + labels them on your fork
├── scripts/
│   ├── init_db.sql        # Creates analytics_ro read-only Postgres role
│   └── send_test_webhook.sh  # Sends a signed test webhook locally
├── tests/                 # 74 tests (pytest, no network required)
├── docker-compose.yml     # postgres + api + worker
├── Dockerfile
├── .env.example
└── pyproject.toml
```
