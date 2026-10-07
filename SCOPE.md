# Scope Statement

## Minimum requirements — all implemented

| Requirement | Status | Location |
|---|---|---|
| FastAPI backend | ✅ | `app/main.py` |
| KML upload | ✅ | `POST /api/files/` |
| Shapefile ZIP upload | ✅ | `POST /api/files/` |
| Feature ID/index | ✅ | `app/db/models.py` — `Feature.feature_index` |
| Geometry type | ✅ | `Feature.geometry_type` |
| Geometry (GeoJSON) | ✅ | `Feature.geometry` |
| CRS | ✅ | `UploadedFile.source_crs` |
| Properties/attributes | ✅ | `Feature.properties` |
| Graceful unsupported geometry | ✅ | `MeasurementEngine` → status=UNSUPPORTED |
| Polygon area (m²) | ✅ | `MeasurementEngine._measure_polygon()` |
| LineString length (m) | ✅ | `MeasurementEngine._measure_line()` |
| Point — no measurement | ✅ | `MeasurementEngine.measure()` → NOT_REQUIRED |
| Geographic CRS reprojection | ✅ | `crs.choose_measurement_crs()` → UTM |
| `POST /api/files/` | ✅ | `app/api/routes/files.py` |
| `GET /api/files/{id}/` | ✅ | same |
| `GET /api/files/{id}/measurements/` | ✅ | same |
| README with setup | ✅ | `README.md` |
| README with API docs | ✅ | `README.md` |
| README with architecture | ✅ | `README.md` + `ARCHITECTURE.md` |
| README with CRS strategy | ✅ | `README.md` |
| README with design decisions | ✅ | `README.md` |
| README with learning | ✅ | `README.md` |
| README with future scope | ✅ | `README.md` |

## Deliberate enhancements (beyond requirements)

These additions demonstrate practical production backend engineering without
changing the required API contract:

| Enhancement | Justification |
|---|---|
| `GET /api/files/` — listing | Usability; shows all uploads with status |
| `DELETE /api/files/{id}/` | Complete CRUD; demonstrates cascade delete |
| `GET /api/files/{id}/features/` | Allows inspection of raw extracted geometry |
| `GET /api/files/{id}/features/{fid}/` | Single-feature retrieval |
| Async processing (BackgroundTasks) | Keeps HTTP threads responsive for large files |
| Paginated responses | Handles files with thousands of features |
| `status` filter on file listing | Operational convenience |
| MultiPolygon area | Natural extension of Polygon handling |
| MultiLineString length | Natural extension of LineString handling |
| Invalid geometry auto-repair | Robustness; uses `make_valid()` |
| `geometry_repaired` flag | Transparency for callers |
| Persistent upload records | Status polling, audit trail |
| `UNAVAILABLE` measurement status | Honest reporting when CRS is unknown |
| SQLite WAL mode | Concurrency between API and background threads |
| ZIP bomb / traversal protection | Security hardening |
| Upload size guard | Prevents resource exhaustion |
| Health + readiness endpoints | Container orchestration support |
| Alembic migrations | Production-grade schema management |
| Docker + Docker Compose | Reproducible one-command startup |
| GitHub Actions CI | Automated testing on every push |
| Pytest test suite (40+ tests) | Confidence and regression prevention |
| Postman collection | Easy manual exploration |
| Sample KML + Shapefile | Ready-to-use demo data |

## Explicitly out of scope

The following are documented as future production extensions and are
intentionally not included in this submission:

- Frontend / map viewer
- Authentication / authorisation
- Distributed worker queue (Celery/RQ)
- Object storage (S3/Azure Blob)
- PostGIS spatial indexing
- Rate limiting
- OpenTelemetry observability
- GeoJSON export endpoint
