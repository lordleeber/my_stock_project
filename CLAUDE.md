# Stock Analysis Project - AI Assistant Guide

## First Step: Ask User Role
At session start, ask which role to take:

1. Frontend Engineer
2. Backend and Data Engineer
3. EPS Training Engineer
4. Strategy Engineer
5. Backtester Engineer

Then read the corresponding guide.

## Role Guides
| Role | Guide | Scope |
|---|---|---|
| Frontend Engineer | `frontend/CLAUDE.md` | `frontend/`, `backend_lite/`, `scripts/deploy_gcp.sh`, `scripts/upload_to_gcs.sh` |
| Backend and Data Engineer | `backend/CLAUDE.md` | `backend/`, `common/`, ETL and API related modules |
| EPS Training Engineer | `train_eps/CLAUDE.md` | `train_eps/`, `models_eps/` |
| Strategy Engineer | `strategies/CLAUDE.md` | `strategies/` |
| Backtester Engineer | `backtester/CLAUDE.md` | `backtester/` |

## Boundary Rules
- Stay inside the selected role scope.
- If task crosses domains, state it clearly and request the correct role.
- Do not silently edit unrelated modules.

## Shared Infrastructure
Be careful when changing:
- `docker-compose.yml`
- `common/schema.py` and shared DB contracts
- `data/` shared artifacts
- `scripts/` — GCP deploy and upload scripts affect production

## GCP Deployment Overview
The web UI is deployed to Google Cloud Run. Key facts for AI assistants:

- **`backend_lite/`** — Standalone FastAPI service, only `/selection/score`. No DB dependency. Reads files from GCS bucket mounted at `/mnt/data` via Cloud Run gcsfuse volume mount. Port 8080.
- **`frontend/`** — Next.js 14 app. Calls backend via internal proxy route `src/app/api/score/route.ts` (server-side). `BACKEND_URL` env var is set at Cloud Run runtime — NOT a `NEXT_PUBLIC_` build-time var. Port 8080.
- **GCS bucket layout** mirrors local paths:
  - `gs://<bucket>/strategies/output/<year>/<MM>/dataset_strategy.csv`
  - `gs://<bucket>/models_selection/<year>/<MM>/selection_model.pkl`
- **Data sync**: run `./scripts/upload_to_gcs.sh <bucket>` after each new model/strategy month is generated.
- **Deploy**: run `./scripts/deploy_gcp.sh <project_id> <bucket> <region>`.
- **Local dev**: frontend calls `/api/score` (proxy) → `BACKEND_URL=http://localhost:8000` → local `backend/` (full API).

## Practical Rules
- Prefer reproducible CLI workflows.
- Keep file naming conventions stable.
- Do not commit generated csv/json/pkl artifacts unless explicitly requested.
- When changing schema or feature columns, verify downstream compatibility.
- When changing `backend_lite/main.py`, verify `backend/main.py` `/selection/score` stays in sync if both need the same fix.
