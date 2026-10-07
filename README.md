# Geospatial File Measurement API

A **production-oriented** geospatial file processing backend built with **FastAPI**.  
Upload a `.kml` file or a `.zip` archive containing a Shapefile and receive **CRS-aware area and length measurements** for every feature.

---

## Features at a glance

| Capability | Details |
|---|---|
| **File formats** | KML (`.kml`) · Shapefile ZIP (`.zip`) |
| **Measurements** | Polygon/MultiPolygon → area (m²) · LineString/MultiLineString → length (m) · Point → not required |
| **CRS handling** | Automatically reprojects geographic coordinates (e.g. EPSG:4326) to a local UTM zone before calculation |
| **Async processing** | HTTP 202 Accepted on upload; background processing with status polling |
| **Paginated endpoints** | All list responses are paginated |
| **Full CRUD** | Upload · list · retrieve · delete |
| **Security** | ZIP path-traversal protection · upload size limits · archive bomb guards · extension allow-list |
| **Persistence** | PostgreSQL (default) or SQLite |
| **Migrations** | Alembic-managed schema |
| **Testing** | Pytest suite covering all endpoints, geometry types, CRS edge-cases, security |
| **Docker** | Single-command startup with Docker Compose |
| **OpenAPI** | Swagger UI and ReDoc auto-generated |
| **CI/CD** | GitHub Actions with lint, type-check, and test steps |

---

## Tech stack

| Area | Technology |
|---|---|
| Language | Python 3.12+ |
| Backend | FastAPI |
| Validation | Pydantic v2 / pydantic-settings |
| ASGI server | Uvicorn |
| ORM | SQLAlchemy 2.x |
| Migrations | Alembic |
| Database | PostgreSQL (default) / SQLite |
| Geospatial | GeoPandas · Shapely · PyProj · Pyogrio |
| Testing | Pytest · HTTPX · pytest-cov |
| Containerization | Docker · Docker Compose |
| Code quality | Ruff · Black · mypy |
| CI/CD | GitHub Actions |
| API docs | OpenAPI / Swagger UI / ReDoc |

---

## Architecture

### High-level flow

```
Client
  │
  │  POST /api/files/   multipart/form-data
  ▼
FastAPI (HTTP handler)
  ├── Extension validation (.kml / .zip)
  ├── Upload-size streaming guard
  ├── Secure file storage   → storage/uploads/<uuid>/
  ├── DB record insert      → status: UPLOADED
  └── BackgroundTask queued → returns 202 Accepted
         │
         ▼  (in-process background thread)
  FileProcessingService.process()
         │
         ├── GeospatialFileReader.read()
         │     ├── KML → gpd.read_file(engine="pyogrio")
         │     └── Shapefile ZIP
         │           ├── ZIP security validation (traversal, bombs, symlinks)
         │           ├── Component presence check (.shp + .shx + .dbf)
         │           └── gpd.read_file(shp_path, engine="pyogrio")
         │
         ├── CRS detection  →  EPSG:xxxx label or None
         │
         ├── For each feature:
         │     ├── Feature extraction  (geometry, properties, validity)
         │     ├── Geometry validity check  (Shapely)
         │     ├── make_valid() repair if needed
         │     ├── CRS selection  (choose_measurement_crs)
         │     │     ├── Already projected  → use as-is
         │     │     ├── Geographic (e.g. EPSG:4326)  → estimate_utm_crs()
         │     │     └── Fallback  → local LAEA / AEQD
         │     ├── Geometry reprojection  (GeoSeries.to_crs())
         │     └── Measurement  (.area / .length in projected units)
         │
         └── DB update  → status: COMPLETED | FAILED
```

### Project structure

```
geospatial/
├── app/
│   ├── api/
│   │   ├── routes/
│   │   │   ├── files.py        # Upload, list, retrieve, delete, features, measurements
│   │   │   └── health.py       # /health and /ready
│   │   ├── dependencies.py     # FastAPI dependency injectors
│   │   └── schemas.py          # Pydantic request/response models
│   ├── core/
│   │   ├── config.py           # Pydantic-settings configuration
│   │   ├── errors.py           # Custom exception hierarchy
│   │   └── logging.py          # Structured logging configuration
│   ├── db/
│   │   ├── base.py             # SQLAlchemy declarative base
│   │   ├── database.py         # Engine, session factory, table creation
│   │   ├── models.py           # UploadedFile, Feature, Measurement ORM models
│   │   └── repositories.py     # Reusable DB query helpers
│   ├── geospatial/
│   │   ├── crs.py              # CRS decision logic (UTM estimation, fallbacks)
│   │   ├── measurement.py      # MeasurementEngine (area, length, unsupported handling)
│   │   ├── reader.py           # GeospatialFileReader (KML + secure Shapefile ZIP)
│   │   └── utils.py            # json_safe() for numpy/pandas serialization
│   ├── services/
│   │   ├── processor.py        # FileProcessingService — full pipeline orchestration
│   │   └── storage.py          # FileStorageService — streaming upload to disk
│   └── main.py                 # Application factory (create_app)
├── alembic/                    # Database migrations
├── tests/                      # Pytest test suite
├── sample_data/                # Demo KML and Shapefile ZIP
├── scripts/                    # Utility scripts (generate sample shapefile)
├── .github/workflows/ci.yml    # GitHub Actions CI
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
└── pyproject.toml
```

---

## API reference

### Base URL

```
http://localhost:8000
```

### Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/files/` | Upload a KML or Shapefile ZIP |
| `GET` | `/api/files/` | List all uploaded files (paginated) |
| `GET` | `/api/files/{id}/` | Get file metadata and status |
| `DELETE` | `/api/files/{id}/` | Delete a file and all its data |
| `GET` | `/api/files/{id}/measurements/` | Get measurements for all features |
| `GET` | `/api/files/{id}/features/` | Get extracted features with geometry |
| `GET` | `/api/files/{id}/features/{feature_id}/` | Get a single feature |
| `GET` | `/health` | Liveness check |
| `GET` | `/ready` | Readiness check (tests database connectivity) |
| `GET` | `/` | API info and links |
| `GET` | `/docs` | Swagger UI |
| `GET` | `/redoc` | ReDoc |

---

### 1. Upload a file

```http
POST /api/files/
Content-Type: multipart/form-data
```

**Form field:**

| Field | Type | Description |
|---|---|---|
| `file` | file | `.kml` file or `.zip` containing a Shapefile |

**Response — 202 Accepted:**

```json
{
  "id": "9dcbf4e0-4f7c-4a3d-9f83-e0c7cc7d43f1",
  "filename": "survey.kml",
  "file_type": "kml",
  "file_size": 2184,
  "status": "UPLOADED",
  "created_at": "2026-10-07T14:30:00Z"
}
```

**Error responses:**

| Code | Reason |
|---|---|
| `415` | Unsupported file extension or invalid ZIP |
| `422` | Missing file field |

---

### 2. List files

```http
GET /api/files/?page=1&page_size=20&status=COMPLETED
```

**Query parameters:**

| Parameter | Default | Description |
|---|---|---|
| `page` | `1` | Page number (1-indexed) |
| `page_size` | `20` | Items per page (max 200) |
| `status` | — | Filter by status: `UPLOADED`, `PROCESSING`, `COMPLETED`, `FAILED` |

**Response — 200 OK:**

```json
{
  "page": 1,
  "page_size": 20,
  "total": 5,
  "items": [
    {
      "id": "9dcbf4e0-...",
      "filename": "survey.kml",
      "file_type": "kml",
      "file_size": 2184,
      "feature_count": 4,
      "crs": "EPSG:4326",
      "status": "COMPLETED",
      "created_at": "2026-10-07T14:30:00Z",
      "processing_started_at": "2026-10-07T14:30:00Z",
      "processing_completed_at": "2026-10-07T14:30:01Z"
    }
  ]
}
```

---

### 3. File information

```http
GET /api/files/{id}/
```

**Response — 200 OK:**

```json
{
  "id": "9dcbf4e0-4f7c-4a3d-9f83-e0c7cc7d43f1",
  "filename": "survey.kml",
  "file_type": "kml",
  "file_size": 2184,
  "feature_count": 4,
  "crs": "EPSG:4326",
  "status": "COMPLETED",
  "error_message": null,
  "created_at": "2026-10-07T14:30:00Z",
  "processing_started_at": "2026-10-07T14:30:00Z",
  "processing_completed_at": "2026-10-07T14:30:01Z"
}
```

**Status lifecycle:**

```
UPLOADED → PROCESSING → COMPLETED
                      ↘ FAILED
```

---

### 4. Measurements

```http
GET /api/files/{id}/measurements/?page=1&page_size=50
```

**Response — 200 OK:**

```json
{
  "file_id": "9dcbf4e0-4f7c-4a3d-9f83-e0c7cc7d43f1",
  "page": 1,
  "page_size": 50,
  "total": 4,
  "items": [
    {
      "feature_id": 1,
      "feature_index": 0,
      "geometry_type": "Polygon",
      "source_crs": "EPSG:4326",
      "measurement_type": "area",
      "measurement": 548234.127,
      "unit": "m²",
      "measurement_crs": "EPSG:32643",
      "status": "COMPLETED",
      "message": "A local UTM CRS was estimated from the feature bounds.",
      "geometry_repaired": false
    },
    {
      "feature_id": 2,
      "feature_index": 1,
      "geometry_type": "LineString",
      "source_crs": "EPSG:4326",
      "measurement_type": "length",
      "measurement": 1432.85,
      "unit": "m",
      "measurement_crs": "EPSG:32643",
      "status": "COMPLETED",
      "message": "A local UTM CRS was estimated from the feature bounds.",
      "geometry_repaired": false
    },
    {
      "feature_id": 3,
      "feature_index": 2,
      "geometry_type": "Point",
      "source_crs": "EPSG:4326",
      "measurement_type": null,
      "measurement": null,
      "unit": null,
      "measurement_crs": null,
      "status": "NOT_REQUIRED",
      "message": "Point geometries do not require a measurement.",
      "geometry_repaired": false
    },
    {
      "feature_id": 4,
      "feature_index": 3,
      "geometry_type": "Polygon",
      "source_crs": "EPSG:4326",
      "measurement_type": "area",
      "measurement": 441180.334,
      "unit": "m²",
      "measurement_crs": "EPSG:32643",
      "status": "COMPLETED",
      "message": "A local UTM CRS was estimated from the feature bounds.",
      "geometry_repaired": false
    }
  ]
}
```

**Measurement status values:**

| Status | Meaning |
|---|---|
| `COMPLETED` | Measurement calculated successfully |
| `NOT_REQUIRED` | Point or MultiPoint — no measurement needed |
| `UNSUPPORTED` | Geometry type not eligible for measurement (e.g. GeometryCollection) |
| `UNAVAILABLE` | Source CRS is unknown; measurement would be unreliable |
| `FAILED` | Unexpected error during measurement |

---

### 5. Features

```http
GET /api/files/{id}/features/?page=1&page_size=50
```

**Response — 200 OK:**

```json
{
  "file_id": "9dcbf4e0-...",
  "page": 1,
  "page_size": 50,
  "total": 4,
  "items": [
    {
      "id": 1,
      "feature_index": 0,
      "geometry_type": "Polygon",
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[77.5913, 12.9766], ...]]
      },
      "properties": {
        "Name": "Cubbon Park Approximate Boundary",
        "Description": "A polygon approximating Cubbon Park, Bengaluru.",
        "category": "park"
      },
      "source_crs": "EPSG:4326",
      "is_valid": true,
      "validity_issue": null
    }
  ]
}
```

---

### 6. Delete a file

```http
DELETE /api/files/{id}/
```

**Response — 204 No Content**

Permanently removes the database record, all features, measurements, and the stored file.

---

## CRS strategy

Measurements are **never calculated directly from longitude/latitude degrees.**

### Decision tree

```
Source CRS known?
  No  →  status: UNAVAILABLE (measurement skipped, reason reported)
  Yes →
    Already projected?
      Yes →  use source CRS as-is (report its linear unit)
      No  →
        Is geographic (lat/lon)?
          Yes →  estimate_utm_crs() from feature bounds
            UTM found?  Yes →  project to UTM, calculate in metres
            UTM failed? →  build local LAEA/AEQD from feature centroid, calculate in metres
          No  →  build local projection (non-standard CRS)
```

### Why UTM?

UTM is a globally applicable, familiar projected system with metre units. GeoPandas' `estimate_utm_crs()` derives the optimal zone from the geometry's geographic bounds — no hard-coded zone table needed.

### Fallback projections

For geometries near the poles or with unusual source CRS, the engine falls back to:

- **Polygon / area** → Local Equal-Area Azimuthal (`+proj=laea`) centred on the feature
- **Line / length** → Local Azimuthal Equidistant (`+proj=aeqd`) centred on the feature

Both are constructed dynamically from the feature's centroid, guaranteeing a metric result with known distortion characteristics.

---

## Geometry handling

| Geometry type | Measurement | Notes |
|---|---|---|
| `Polygon` | Area | Projected area in m² |
| `MultiPolygon` | Area | Projected area of entire multi-geometry |
| `LineString` | Length | Projected length in m |
| `MultiLineString` | Length | Projected length of entire multi-geometry |
| `Point` | — | `NOT_REQUIRED` status returned |
| `MultiPoint` | — | `NOT_REQUIRED` status returned |
| `GeometryCollection` | — | `UNSUPPORTED` status returned gracefully |
| Other / unknown | — | `UNSUPPORTED` status returned |

### Invalid geometry handling

1. Shapely's `explain_validity()` identifies the issue.
2. `make_valid()` attempts automatic repair.
3. If repair succeeds, measurement proceeds on the repaired geometry.
4. The response includes `geometry_repaired: true` and a description of the original validity issue.
5. If repair fails or produces an empty geometry, measurement is skipped with a clear message.

### Per-feature isolation

A single failing feature never aborts the rest. Each feature's measurement is wrapped in a `try/except`. The overall file transitions to `COMPLETED` even if individual features have `FAILED` or `UNSUPPORTED` measurements.

---

## Secure file handling

| Threat | Mitigation |
|---|---|
| Arbitrary file type upload | Extension allow-list (`.kml`, `.zip`) |
| Large file DoS | Streaming upload with byte counter; configurable `MAX_UPLOAD_SIZE_MB` |
| ZIP bomb | Tracks uncompressed size during validation; configurable `MAX_ZIP_UNCOMPRESSED_MB` |
| ZIP path traversal | Rejects entries with `..` or absolute paths |
| Symlink entries | Checks `external_attr` mode bits; rejects symlinks |
| Encrypted ZIP entries | Checks `flag_bits`; rejects encrypted entries |
| Duplicate entry names | Detects and rejects archives with duplicate names |
| Multiple Shapefiles | Enforces exactly one `.shp` in the archive |
| Missing sidecar files | Validates `.shp`, `.shx`, and `.dbf` all present |
| Stored-path injection | Generated UUIDs used for all storage paths; original filename only used as leaf name |

---

## Local setup

### Option A — Docker Compose (recommended)

**Prerequisite:** Docker Desktop

```bash
# 1. Copy environment config
cp .env.example .env

# 2. Start API + PostgreSQL
docker compose up --build

# API:    http://localhost:8000
# Docs:   http://localhost:8000/docs
# ReDoc:  http://localhost:8000/redoc
```

---

### Option B — Local Python

**Prerequisites:** Python 3.12+, GDAL system libraries

#### 1. Install GDAL system libraries

**Ubuntu/Debian:**
```bash
sudo apt-get update && sudo apt-get install -y gdal-bin libgdal-dev libgeos-dev libproj-dev
```

**macOS (Homebrew):**
```bash
brew install gdal
```

**Windows:**  
Use [OSGeo4W](https://trac.osgeo.org/osgeo4w/) or install via conda:
```powershell
conda install -c conda-forge geopandas pyogrio
```

#### 2. Create a virtual environment

```bash
python -m venv .venv
```

```powershell
# Windows
.venv\Scripts\Activate.ps1
```

```bash
# Linux / macOS
source .venv/bin/activate
```

#### 3. Install dependencies

```bash
pip install -r requirements-dev.txt
```

#### 4. Configure environment

```bash
cp .env.example .env
# Edit .env if needed — defaults use PostgreSQL and local storage
```

#### 5. Start the server

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

---

## Example requests

### Upload a KML file

```bash
curl -X POST "http://localhost:8000/api/files/" \
  -F "file=@sample_data/demo.kml" \
  -H "accept: application/json"
```

### Upload a Shapefile ZIP

```bash
curl -X POST "http://localhost:8000/api/files/" \
  -F "file=@sample_data/demo_shapefile.zip" \
  -H "accept: application/json"
```

### List all files

```bash
curl "http://localhost:8000/api/files/?page=1&page_size=20"
```

### Check processing status

```bash
curl "http://localhost:8000/api/files/<FILE_ID>/"
```

### Get measurements

```bash
curl "http://localhost:8000/api/files/<FILE_ID>/measurements/"
```

### Get features (raw geometry)

```bash
curl "http://localhost:8000/api/files/<FILE_ID>/features/"
```

### Delete a file

```bash
curl -X DELETE "http://localhost:8000/api/files/<FILE_ID>/"
```

---

## Testing

```bash
# Run all tests
pytest

# With coverage report
pytest --cov=app --cov-report=term-missing

# Run a specific test file
pytest tests/test_api.py -v

# Run a specific test
pytest tests/test_geospatial.py::test_polygon_area_uses_projected_crs -v
```

### Test coverage areas

| Module | What is tested |
|---|---|
| `test_api.py` | All HTTP endpoints, pagination, status codes, content validation |
| `test_geospatial.py` | Polygon area, LineString length, Point no-measurement, missing CRS, projected CRS passthrough |
| `test_security.py` | ZIP path traversal, duplicate entries, multiple Shapefiles |
| `test_shapefile.py` | Shapefile ZIP extraction and reading |
| `test_failure_isolation.py` | GeometryCollection graceful handling |

---

## Code quality

```bash
# Lint
ruff check .

# Format check
black --check .

# Auto-fix lint issues
ruff check . --fix

# Auto-format
black .

# Type checking
mypy app
```

---

## Database migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Check current revision
alembic current

# Create a new migration after model changes
alembic revision --autogenerate -m "describe your change"

# Rollback one step
alembic downgrade -1
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `APP_NAME` | `Geospatial File Measurement API` | API title shown in docs |
| `ENVIRONMENT` | `development` | Runtime environment tag |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `DATABASE_URL` | `sqlite:///./geospatial_api.db` | SQLAlchemy database URL |
| `STORAGE_ROOT` | `./storage` | Root directory for uploaded files |
| `MAX_UPLOAD_SIZE_MB` | `50` | Maximum upload file size |
| `MAX_ZIP_ENTRIES` | `1000` | Maximum number of entries in a ZIP |
| `MAX_ZIP_UNCOMPRESSED_MB` | `250` | Maximum total uncompressed ZIP size |
| `CORS_ALLOWED_ORIGINS` | `*` | Comma-separated CORS origins or `*` |
| `AUTO_CREATE_DB` | `true` | Create tables on startup (set `false` for production) |

> **Never commit real `.env` files or credentials.**

---

## Design decisions

### FastAPI over Django REST Framework

FastAPI provides concise routing, first-class async support, auto-generated OpenAPI docs, and strong Pydantic v2 integration — all ideal for an API-first service. Django REST Framework offers more batteries but introduces significant boilerplate for a focused microservice.

### BackgroundTasks over a distributed queue

Geospatial processing is CPU/IO-bound but does not require durability across restarts at this scope. FastAPI's `BackgroundTasks` keeps the upload response fast (202 Accepted) without external infrastructure dependencies. The trade-off — tasks are lost on restart — is acceptable for an assignment submission. For production, the migration path to Celery + Redis is straightforward.

### SQLite default with PostgreSQL ready

SQLite requires zero infrastructure for local development and tests. A single `DATABASE_URL` change switches to PostgreSQL for production. Geospatial calculations are handled entirely in Python (not PostGIS), keeping the schema portable.

### Per-feature fault isolation

The reader failing is a job-level failure. A single feature failing measurement is a feature-level failure. This separation means malformed geometries do not discard valid measurements in the same file.

### GeoJSON geometry storage

Feature geometry is persisted as a GeoJSON-like JSON blob. This keeps the API portable across SQLite and PostgreSQL without requiring PostGIS. A future migration could replace the JSON column with a PostGIS `geometry` column while keeping the HTTP API contract unchanged.

### CRS projection strategy

Rather than maintaining a static EPSG lookup table, `estimate_utm_crs()` from GeoPandas dynamically selects the best UTM zone from the feature's geographic bounds. This covers the vast majority of real-world datasets. The azimuthal fallback handles edge cases (near-polar geometries, small custom CRS datasets) without crashing.

### Units

Polygon area → m² (UTM/LAEA). LineString length → m. For source datasets already in a projected CRS with a different linear unit, the unit is surfaced directly (e.g. `ft`) rather than silently mislabeled as metres.

---

## Learning

Building this project reinforced several important lessons:

- **CRS is not optional.** Treating degrees as distances produces silently wrong results. Proper CRS handling requires checking, projecting, and reporting.
- **Geospatial data is messy.** Files often contain invalid geometries, unknown CRS, mixed geometry types, or empty features. Each must be handled independently without crashing the pipeline.
- **Background task design.** The 202 Accepted pattern with status polling is a clean way to handle CPU-bound work without blocking HTTP threads.
- **ZIP security.** Archive handling is a well-known attack surface. Checking for traversal, bombs, symlinks, and encrypted entries is non-trivial but essential.
- **Per-feature isolation.** Aborting all features because one fails wastes good data. Isolating failures at the feature level is both more robust and more useful to the caller.
- **FastAPI's dependency injection** makes it easy to build testable services without tight coupling between layers.

---

## Future scope

The implementation intentionally stays within the assignment scope. Natural next improvements:

1. **Durable background queue** — Celery + Redis or AWS SQS for crash-resilient processing.
2. **Object storage** — S3/Azure Blob/GCS instead of local disk for horizontal scalability.
3. **PostGIS geometry columns** — spatial indexes, bounding-box queries, spatial filtering.
4. **Streaming / chunked processing** — handle million-feature datasets without loading everything into memory.
5. **Job cancellation and retry** — allow callers to cancel in-progress jobs or retry FAILED files.
6. **Authentication and authorization** — OAuth2/JWT so files are user-scoped.
7. **Observability** — OpenTelemetry traces + Prometheus metrics + structured JSON logging.
8. **Rate limiting** — per-IP or per-user upload throttling.
9. **GeoJSON export** — `GET /api/files/{id}/export.geojson` to download processed features.
10. **MultiGeometry measurement decomposition** — report per-component area/length in addition to totals.
11. **Async database sessions** — replace sync SQLAlchemy with `AsyncSession` for fully non-blocking I/O.
12. **File format expansion** — GeoJSON, GeoPackage, CSV with WKT.

---

## Assignment compliance checklist

- [x] FastAPI backend
- [x] `.kml` upload
- [x] `.zip` Shapefile upload
- [x] Feature ID/index
- [x] Geometry type
- [x] Geometry (GeoJSON)
- [x] CRS
- [x] Properties/attributes
- [x] Graceful unsupported geometry handling
- [x] Polygon area (m²)
- [x] MultiPolygon area (extension)
- [x] LineString length (m)
- [x] MultiLineString length (extension)
- [x] Point — no measurement required
- [x] Geographic CRS reprojection before measurement (UTM + fallbacks)
- [x] `POST /api/files/`
- [x] `GET /api/files/` (listing — extension)
- [x] `GET /api/files/{id}/`
- [x] `DELETE /api/files/{id}/` (extension)
- [x] `GET /api/files/{id}/measurements/`
- [x] `GET /api/files/{id}/features/` (extension)
- [x] `GET /api/files/{id}/features/{feature_id}/` (extension)
- [x] README — setup instructions
- [x] README — API documentation with example requests/responses
- [x] README — application architecture
- [x] README — file-processing flow
- [x] README — measurement calculation flow
- [x] README — CRS handling strategy
- [x] README — design decisions
- [x] README — learning
- [x] README — future scope
- [x] Pytest test suite
- [x] Docker / Docker Compose
- [x] GitHub Actions CI
- [x] Swagger / OpenAPI auto-docs
- [x] Health and readiness checks
- [x] Postman collection
- [x] Sample data files (KML + Shapefile ZIP)
