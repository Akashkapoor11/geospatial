# Verification Record

This document records the verification performed before submission.

## Static analysis

| Check | Tool | Result |
|---|---|---|
| Python syntax | `ast.parse()` on all `.py` files | ✅ PASS |
| Import resolution | Python import dry-run | ✅ PASS |
| Line length ≤ 100 | Manual audit | ✅ PASS |
| No `.env`, `.sqlite3`, or `storage/uploads/*` committed | `.gitignore` + manual check | ✅ PASS |

## Code quality (run with `make check`)

| Tool | Check |
|---|---|
| `ruff check .` | Lint — PEP8, unused imports, common bugs |
| `black --check .` | Format consistency |
| `mypy app` | Type correctness |

## Test suite

Run with: `pytest --cov=app --cov-report=term-missing`

### Test files

| File | What is covered |
|---|---|
| `tests/test_api.py` | All 7 REST endpoints, pagination, status codes, KML + Shapefile workflows |
| `tests/test_geospatial.py` | MeasurementEngine — all geometry types, repair, rounding, CRS scenarios |
| `tests/test_crs.py` | CRS selection logic, crs_label, CRSDecision immutability |
| `tests/test_security.py` | ZIP security, extension allow-list, upload size limit |
| `tests/test_security.py` | Path traversal, absolute paths, duplicate entries, missing sidecars |
| `tests/test_failure_isolation.py` | Per-feature isolation, message presence, no-crash guarantees |
| `tests/test_shapefile.py` | Shapefile ZIP extraction and GeoDataFrame loading |

### Expected result

> All tests passing. Coverage ≥ 85%.

## API smoke test (Docker)

| Scenario | Expected result |
|---|---|
| `docker compose up --build` | Both containers healthy |
| `GET /health` | `{"status":"ok"}` |
| `GET /ready` | `{"status":"ready","database":"ok"}` |
| `POST /api/files/` with `demo.kml` | `202 Accepted`, `status=UPLOADED` |
| `GET /api/files/{id}/` after delay | `status=COMPLETED`, `crs=EPSG:4326`, `feature_count=4` |
| `GET /api/files/{id}/measurements/` | 2 polygon areas, 1 line length, 1 NOT_REQUIRED |
| `measurement_crs` on polygon | UTM zone — not `EPSG:4326` |
| `POST /api/files/` with `demo_shapefile.zip` | `202 Accepted`, processes successfully |
| `GET /api/files/` | lists both uploads |
| `DELETE /api/files/{id}/` | `204 No Content`; follow-up GET returns 404 |
| Swagger UI at `/docs` | All endpoints documented with descriptions |
| ReDoc at `/redoc` | Alternative documentation rendered |

## Migration

```bash
alembic upgrade head   # ← should apply 0001_initial without errors
```

## Notes

- Docker is required for the full PostgreSQL stack test. SQLite is also supported for zero-configuration local development via .env.
- The shapefile sample ZIP must be regenerated if running on a machine without GeoPandas:
  ```bash
  python scripts/generate_sample_shapefile.py
  ```
