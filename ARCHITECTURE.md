# Architecture Deep-Dive

## Request lifecycle

### Upload phase (synchronous, < 100 ms)

```
POST /api/files/
  │
  ├─ Extension validation (.kml / .zip allow-list)
  ├─ Filename sanitisation (null-byte check, safe_name extraction)
  ├─ Streaming write to storage/uploads/<uuid>/<filename>
  │    └─ Byte counter guard — rejects if > MAX_UPLOAD_SIZE_MB
  ├─ Database record INSERT (status=UPLOADED)
  └─ HTTP 202 Accepted  ←── response returned here
       │
       └─ BackgroundTask queued (runs in same process, separate thread)
```

### Processing phase (asynchronous, background thread)

```
FileProcessingService.process(file_id)
  │
  ├─ DB: status=PROCESSING, processing_started_at=now()
  │
  ├─ GeospatialFileReader.read()
  │    ├─ KML: gpd.read_file() with pyogrio engine
  │    │        └─ Multi-layer KML: reads first non-empty layer
  │    └─ Shapefile ZIP:
  │         ├─ ZIP signature check
  │         ├─ Security validation (traversal, bombs, symlinks, duplicates)
  │         ├─ Component check (.shp + .shx + .dbf)
  │         ├─ Streaming extraction to <uuid>_extracted/
  │         └─ gpd.read_file(shp_path) with pyogrio engine
  │
  ├─ CRS extraction from GeoDataFrame.crs
  │
  ├─ For each feature (isolated try/except per feature):
  │    ├─ Geometry → GeoJSON-like dict (shapely.geometry.mapping)
  │    ├─ Properties → json_safe() serialisation
  │    ├─ Validity check (shapely.is_valid)
  │    ├─ Feature INSERT
  │    │
  │    ├─ MeasurementEngine.measure(geometry, crs)
  │    │    ├─ Polygon/MultiPolygon → _measure_polygon()
  │    │    │    ├─ _prepare_geometry() → make_valid() repair attempt
  │    │    │    ├─ choose_measurement_crs() → UTM or fallback
  │    │    │    ├─ GeoSeries.to_crs() → project to metric CRS
  │    │    │    └─ .area → round to 6dp
  │    │    ├─ LineString/MultiLineString → _measure_line()
  │    │    │    └─ (same flow, .length instead of .area)
  │    │    ├─ Point/MultiPoint → NOT_REQUIRED (no calculation)
  │    │    └─ Other → UNSUPPORTED (graceful, no crash)
  │    │
  │    └─ Measurement INSERT
  │
  └─ DB: status=COMPLETED | FAILED, processing_completed_at=now()
```

## CRS decision tree

```
source_crs known?
  No  ────────────────────────────────────→ UNAVAILABLE (no value returned)
  Yes
  │
  ├─ is_projected?
  │    Yes ─────────────────────────────→ use source CRS as-is
  │
  ├─ is_geographic? (lat/lon like EPSG:4326)
  │    Yes
  │    │
  │    ├─ estimate_utm_crs() succeeds?
  │    │    Yes ───────────────────────→ project to UTM zone, calculate in m
  │    │    No
  │    │    └─ near poles / edge case
  │    │         └───────────────────→ local LAEA/AEQD from centroid, m
  │
  └─ neither projected nor geographic
       └─────────────────────────────→ local LAEA/AEQD from centroid, m
```

## Failure boundaries

### Job-level failure (whole file FAILED)

Triggered by:
- Corrupt / invalid KML that cannot be parsed
- Corrupt / invalid ZIP archive
- ZIP security violation (traversal, bomb, symlink, etc.)
- Missing Shapefile sidecar components
- GeoDataFrame with zero features
- Any unhandled exception during file reading

Result: `status=FAILED`, `error_message=<description>`

### Feature-level failure (individual feature FAILED/UNSUPPORTED/UNAVAILABLE)

Triggered by:
- Geometry extraction failure
- Unsupported geometry type
- Unknown source CRS
- Measurement calculation exception

Result: Feature stored, measurement stored with descriptive status. **Other features continue unaffected.**

## Database schema

```
uploaded_files
  id (PK, UUID string)
  filename, file_type, file_size
  stored_path
  feature_count, source_crs
  status  [UPLOADED | PROCESSING | COMPLETED | FAILED]
  error_message
  created_at, updated_at, processing_started_at, processing_completed_at

features (N per uploaded_file)
  id (PK, auto int)
  file_id (FK → uploaded_files.id, CASCADE DELETE)
  feature_index
  geometry_type, geometry (JSON GeoJSON)
  properties (JSON)
  source_crs
  is_valid, validity_issue

measurements (1 per feature)
  id (PK, auto int)
  feature_id (FK → features.id, CASCADE DELETE, UNIQUE)
  measurement_type [area | length | null]
  value (float), unit (m² / m / ft / etc.)
  measurement_crs
  status  [COMPLETED | NOT_REQUIRED | UNSUPPORTED | UNAVAILABLE | FAILED]
  message, geometry_repaired
  created_at
```

## Layer structure

```
app/
├── api/           HTTP boundary — routes, schemas, dependency injection
├── core/          Cross-cutting — config, errors, logging
├── db/            Persistence — ORM models, engine, repositories
├── geospatial/    Domain — file readers, CRS policy, measurement engine
├── services/      Application — orchestration (processor, storage)
└── main.py        Application factory
```

Each layer depends only on layers below it:
- `api` → `services`, `db`, `core`
- `services` → `geospatial`, `db`, `core`
- `geospatial` → `core`
- `db` → `core`
- `core` → (nothing internal)

## Persistence strategy

Geometry is stored as GeoJSON-like JSON rather than a PostGIS geometry column. This makes the schema portable between SQLite (local/tests) and PostgreSQL (production) without requiring the PostGIS extension. A future migration can introduce a PostGIS column while keeping the HTTP contract unchanged.

## Concurrency notes

SQLite WAL mode is enabled automatically for all SQLite connections to reduce contention between the API thread (reading) and background processing threads (writing). For production PostgreSQL deployments, WAL is always on and the default pool handles concurrency naturally.
