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
| Frontend Engineer | `frontend/CLAUDE.md` | `frontend/` |
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

## Practical Rules
- Prefer reproducible CLI workflows.
- Keep file naming conventions stable.
- Do not commit generated csv/json/pkl artifacts unless explicitly requested.
- When changing schema or feature columns, verify downstream compatibility.
