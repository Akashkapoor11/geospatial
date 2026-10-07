# Reviewer Runbook — Fastest Path to a Complete Demo

## Option A — Docker (zero local setup)

```bash
# 1. Clone the repo
git clone <YOUR_REPO_URL>
cd geospatial-api

# 2. Copy env config (defaults work out of the box)
cp .env.example .env

# 3. Start everything
docker compose up --build

# API is ready when you see:
#   api_1  | INFO:     Application startup complete.
```

Then open **http://localhost:8000/docs** in your browser.

---

## Option B — Local Python

```bash
# Install system GDAL (Ubuntu/Debian)
sudo apt-get install -y gdal-bin libgdal-dev libgeos-dev libproj-dev

# macOS
brew install gdal

python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

---

## Demo walkthrough (Swagger UI at /docs)

### Step 1 — Upload the sample KML

```bash
curl -X POST http://localhost:8000/api/files/ \
  -F "file=@sample_data/demo.kml" \
  -H "accept: application/json"
```

Copy the returned `id`.

### Step 2 — Check processing status

```bash
curl http://localhost:8000/api/files/<ID>/
```

Expected: `"status": "COMPLETED"`, `"crs": "EPSG:4326"`, `"feature_count": 4`.

### Step 3 — Get measurements

```bash
curl http://localhost:8000/api/files/<ID>/measurements/
```

Expected: 2 polygon features with `"unit": "m²"`, 1 line with `"unit": "m"`, 1 point with `"status": "NOT_REQUIRED"`.

### Step 4 — Verify projected CRS

Confirm that `measurement_crs` is a UTM zone (e.g. `EPSG:32643`) — **not** `EPSG:4326`.

### Step 5 — Upload the Shapefile ZIP

```bash
# Regenerate sample if needed
python scripts/generate_sample_shapefile.py

curl -X POST http://localhost:8000/api/files/ \
  -F "file=@sample_data/demo_shapefile.zip"
```

### Step 6 — List all files

```bash
curl "http://localhost:8000/api/files/?page=1&page_size=10"
```

### Step 7 — Delete a file

```bash
curl -X DELETE http://localhost:8000/api/files/<ID>/
# Returns 204 No Content
```

---

## Run the test suite

```bash
pytest --cov=app --cov-report=term-missing
# Should show 40+ passing tests
```

---

## Key reviewer checklist

| Requirement | Where to check |
|---|---|
| KML upload accepted | `POST /api/files/` → 202 |
| Shapefile ZIP accepted | same endpoint, `.zip` file |
| Feature extraction | `GET /api/files/{id}/features/` |
| Polygon area in m² | `GET /api/files/{id}/measurements/` |
| LineString length in m | same |
| Point → NOT_REQUIRED | same |
| Projected CRS, not EPSG:4326 | `measurement_crs` field |
| CRS shown in file info | `GET /api/files/{id}/` → `crs` field |
| Graceful unsupported geometry | measurement `status=UNSUPPORTED` |
| File listing | `GET /api/files/` |
| Delete | `DELETE /api/files/{id}/` → 204 |
| Swagger docs | http://localhost:8000/docs |
| Health check | `GET /health` → `{"status":"ok"}` |
| Readiness check | `GET /ready` → `{"status":"ready","database":"ok"}` |

---

## Interview talking points

1. **Why FastAPI?** — API-first, strong Pydantic v2 integration, auto-OpenAPI, native async support.
2. **Why 202 Accepted?** — Geospatial processing is CPU/IO-bound; returning immediately keeps the HTTP thread responsive.
3. **How is ZIP path traversal prevented?** — Every entry name is checked with `PurePosixPath` for `..` and absolute paths before extraction.
4. **Why can't area/length be calculated in EPSG:4326?** — Degrees are angular, not linear. 1° of longitude near the equator ≠ 1° near the poles. Treating them as distances yields wildly wrong measurements.
5. **How is the projected CRS selected?** — `estimate_utm_crs()` from GeoPandas selects the optimal UTM zone from the geometry's geographic bounds. Falls back to a local azimuthal projection for edge cases.
6. **How do you prevent one bad feature from failing everything?** — Each feature's measurement is wrapped in a `try/except`. The overall file still reaches `COMPLETED` even if individual features carry `FAILED` or `UNSUPPORTED` measurements.
7. **Why support both PostgreSQL and SQLite?** — PostgreSQL is the robust production default (via Docker), while SQLite allows zero-infrastructure local development and CI testing.
8. **Why store JSON geometry instead of PostGIS?** — Keeps the schema portable. PostGIS can be introduced via a migration without changing the HTTP API contract.
9. **What would you do for multi-instance deployment?** — Replace `BackgroundTasks` with Celery + Redis, replace local storage with S3, add PostGIS for spatial indexing.
