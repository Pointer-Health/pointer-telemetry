# pointer_telemetry
# pointer_telemetry

Structured application telemetry for Python and Flask services.

This package provides:
- **Error logging to your database** with deduplicated fingerprints
- **Structured log fields** (e.g., `vet_id`, `dog_id`, `clinic_id`, `request_id`)
- **Automatic capture of stack traces & request context**
- **Latency tracking** with **slow-call warnings** + **sampled metrics rows**
- Works in **Flask apps**, **background workers**, **Celery tasks**, and **standalone scripts**

It is **lightweight**, **database-driven**, and **intentionally framework-neutral** except for minimal Flask request-context awareness.

---

## Features

| Capability | Description |
|-----------|-------------|
| Error Log Handler | A `logging.Handler` that writes structured logs to a DB table. |
| Functional Error Logger | `make_error_logger` for quick manual error writes (e.g., Celery tasks). |
| Latency Tracker | `track_latency` context manager that emits slow warnings & sampled metrics. |
| Fingerprinting | Automatic grouping of repeating errors using stable SHA-1 fingerprints. |
| Request Context Awareness | Captures route, HTTP method, request_id when Flask request context is active. |
| Safe by Default | Failures in logging **never break your app**. |

---

## Installation

### Install directly from GitHub

```bash
pip install git+https://github.com/Pointer-Health/pointer_telemetry.git
```

### Or add to requirements.txt

```bash
git+https://github.com/Pointer-Health/pointer_telemetry.git@main
```

## Database Requirements

You must define a model/table that logs will be written into.

### Example SQLAlchemy model (PostgreSQL JSONB recommended):

```python
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class ErrorLog(Base):
    __tablename__ = "error_logs"

    id               = Column(Integer, primary_key=True)
    created_at       = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    level            = Column(String(16), index=True)
    message          = Column(Text)
    message_template = Column(Text)
    stack_trace      = Column(Text)
    fingerprint      = Column(String(40), index=True)

    service          = Column(String(64), index=True)
    environment      = Column(String(32), index=True)
    release_version  = Column(String(64))
    build_sha        = Column(String(64))

    route            = Column(String(256), index=True)
    function_name    = Column(String(256), index=True)
    http_method      = Column(String(16))
    http_status      = Column(Integer)
    latency_ms       = Column(Integer)

    request_id       = Column(String(64), index=True)
    session_id       = Column(String(64), index=True)
    clinic_id        = Column(Integer, index=True)
    vet_id           = Column(Integer, index=True)
    dog_id           = Column(Integer, index=True)

    tags             = Column(JSON, default=dict)
```

Run migrations as usual (Alembic, Flask-Migrate, or manual DDL).

## Usage in a Flask Application
### 1) Create a SQLAlchemy engine (used for logging sessions)

```python
from sqlalchemy import create_engine
engine = create_engine("postgresql+psycopg2://...", pool_pre_ping=True, future=True)
```

### 2) Attach the database log handler to the root logger
```python
import logging
from pointer_telemetry.db_log_handler import DBLogHandler
from yourapp.models import ErrorLog

handler = DBLogHandler(
    engine=engine,
    ErrorLogModel=ErrorLog,
    service="api",           # name of this runtime (api/worker/cron/etc.)
    environment="prod",      # prod/staging/local
    release_version="v1.4.3",
    build_sha="abcdef1234",
)

logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)
```

### 3) Log as you normally do
```python
import logging
logger = logging.getLogger(__name__)

@app.route("/dogs/<int:dog_id>")
def get_dog(dog_id):
    try:
        raise ValueError("Example failure")
    except Exception:
        logger.error(
            "Failed to fetch dog %s", dog_id,
            exc_info=True,
            extra={"dog_id": dog_id, "service_component": "router"}
        )
        return "error", 500
```

## Usage in Workers / Scripts / Celery
For non-Flask environments, use the functional logger:

```python
from pointer_telemetry.errorlog import make_error_logger
from yourapp.extensions import db
from yourapp.models import ErrorLog
import traceback

log_error = make_error_logger(
    db.session,
    ErrorLog,
    service="worker",
    environment="prod",
    release_version="v1.4.3",
    build_sha="abcdef1234",
)

try:
    do_processing()
except Exception as e:
    log_error(
        message=str(e),
        stack_trace=traceback.format_exc(),
        function_name="process_patient",
        dog_id=dog_id,
        tags={"queue": "high"},
    )
```

## Tracking Latency & Slow Operations
```python
from pointer_telemetry.context import track_latency

def write_http_metric(row):
    db.session.execute(HttpCalls.__table__.insert().values(**row))

with track_latency(
    db,
    service="api",
    peer="gcp-vm",
    route="/predict",
    method="POST",
    clinic_id=clinic_id,
    slow_ms=2000,
    write_http_row=write_http_metric,
    log_warning=log_error,   # reuse functional logger
) as ctx:
    call_remote_service(request_id=ctx["request_id"])
```

This writes:
- sampled full-fidelity metrics to http_calls
- AND logs a WARNING if latency ≥ slow_ms

### Fingerprints & De-Duplication
Errors with:
- Same exception type
- Same message template (large numbers masked)
- Same top stack frames
- Same service + release

→ produce the same fingerprint hash
You can group incidents by fingerprint to reduce alert noise.

### Dashboards: Useful SQL
Top recurring incidents in last 24 hours:

```sql
SELECT fingerprint, COUNT(*) AS count, MAX(created_at) AS last_seen,
       ANY_VALUE(message_template) AS example_message,
       ANY_VALUE(service) AS service
FROM error_logs
WHERE created_at >= NOW() - INTERVAL '24 hours'
GROUP BY fingerprint
ORDER BY count DESC;
```


