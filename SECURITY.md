# Security Notes

## This submission vs. a production service

This repository is an assignment submission demonstrating geospatial backend
engineering. It implements several defensive controls that would also be
required in production, and explicitly documents the additional controls that
a real multi-tenant deployment would need.

---

## Implemented defensive controls

### File upload

| Threat | Control |
|---|---|
| Arbitrary file type upload | Extension allow-list: only `.kml` and `.zip` accepted |
| Large file DoS | Streaming byte counter; configurable `MAX_UPLOAD_SIZE_MB` |
| Content type spoofing | Extension check is applied to the actual filename, not `Content-Type` |
| Filename injection | UUID-generated storage paths; original filename used only as leaf |
| Null-byte filename tricks | Filename sanitisation strips null bytes |

### ZIP archives

| Threat | Control |
|---|---|
| Path traversal (`../`) | `PurePosixPath` checks every entry name for `..` and absolute paths |
| ZIP bomb | Tracks total uncompressed bytes; rejects when > `MAX_ZIP_UNCOMPRESSED_MB` |
| Too many entries | Rejects when entry count > `MAX_ZIP_ENTRIES` |
| Symlink entries | Checks `external_attr` Unix mode bits; rejects symlinks |
| Encrypted entries | Checks `flag_bits`; rejects encrypted entries |
| Duplicate entry names | Detects and rejects archives with duplicate names |
| Multiple Shapefiles | Enforces exactly one `.shp` in the archive |
| Missing sidecar files | Validates `.shp`, `.shx`, and `.dbf` all present |

### Runtime

| Threat | Control |
|---|---|
| Secret leakage | Configuration through environment variables; `.env` excluded from `.gitignore` |
| Code injection | Uploaded files are parsed by GeoPandas; never executed |
| Database injection | All DB access through SQLAlchemy parameterised queries (ORM) |
| Non-root container | Docker image runs as `appuser`, not root |
| Dependency pinning | `requirements.txt` contains exact pinned versions |

---

## Additional controls required for production

Before deploying this as a public multi-tenant service, add:

| Area | Controls needed |
|---|---|
| Authentication | OAuth2/JWT; scope-based endpoint access |
| Authorisation | Per-user file ownership; cannot access another user's files |
| Rate limiting | Per-IP and per-user upload throttle |
| Object storage isolation | Files in S3/Azure with per-user prefixes and signed URLs |
| Malware scanning | ClamAV or cloud AV on upload before processing |
| Network controls | VPC, WAF, DDoS protection |
| Secrets management | Vault or AWS Secrets Manager; no env-var secrets in production |
| Audit logging | Who uploaded what, when, with what IP |
| CORS tightening | Replace `*` with an explicit allow-list of frontend origins |
| HTTPS enforcement | TLS termination at load balancer level |
