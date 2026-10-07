# Submission Checklist

## Before pushing to GitHub

- [ ] `pytest` passes locally with green output
- [ ] `make check` (lint + format + typecheck) passes with no errors
- [ ] `python scripts/generate_sample_shapefile.py` generates `sample_data/demo_shapefile.zip`
- [ ] `docker compose up --build` starts without errors and `/health` returns `200`
- [ ] `POST /api/files/` with `sample_data/demo.kml` → status reaches `COMPLETED`
- [ ] `GET /api/files/{id}/measurements/` → 4 features, polygon `m²`, line `m`, point `NOT_REQUIRED`
- [ ] `measurement_crs` on polygon is a UTM zone, **not** `EPSG:4326`
- [ ] No `.env`, `*.sqlite3`, `*.db`, or `storage/uploads/` contents are committed
- [ ] `alembic upgrade head` runs without errors against a fresh SQLite database

## Pushing to GitHub

```bash
git init            # if not already done
git add .
git commit -m "feat: geospatial file measurement API v1.0.0"
git remote add origin <YOUR_GITHUB_URL>
git push -u origin main
```

## Making the repository public

1. Open the repository on GitHub.
2. Go to **Settings** → **Danger Zone** → **Change visibility** → **Make public**.
3. Open the repository in a **private/incognito browser window** and verify it is readable without login.

## Submitting the form

1. Open the Microsoft Form link.
2. Paste the **public GitHub repository URL** into **Assignment Submission URL**.
3. Select **Geospatial File Measurement API** as the task.
4. Paste your **publicly viewable resume URL**.
5. Submit.

## Final review

The repository should be navigable by a reviewer in this order:

1. `README.md` — setup, API reference, architecture, CRS strategy, design decisions, learning, future scope
2. `RUNBOOK.md` — fastest demo path + interview talking points
3. `ARCHITECTURE.md` — deep-dive into the processing pipeline and schema
4. `SECURITY.md` — upload and ZIP threat model
5. `SCOPE.md` — requirements compliance table and enhancements list
6. `http://localhost:8000/docs` — live Swagger UI (after `docker compose up`)
