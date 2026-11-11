#!/usr/bin/env python3
"""IncidentLens Realistic Log and Incident Generator.

Generates deterministic synthetic log datasets for 8 incident scenarios
(with 4 variants each: low/high noise x single/multi-service) plus 2 control
datasets (healthy steady-state and benign traffic spike) = 34 total scenarios.

Outputs:
  - simulator/scenarios/<scenario_id>.log
  - simulator/ground_truth.json
"""

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Stack Trace Templates
# ---------------------------------------------------------------------------

STACK_TRACE_DB_POOL = """Traceback (most recent call last):
  File "/app/services/checkout.py", line 142, in process_checkout
    async with db.begin():
  File "/app/db/session.py", line 55, in begin
    conn = await pool.connect()
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/pool/impl.py", line 403, in connect
    return await self._connection_record()
sqlalchemy.exc.TimeoutError: QueuePool limit of size 20 overflow 10 reached, connection timed out, timeout 30.00"""

STACK_TRACE_REDIS_OOM = """Traceback (most recent call last):
  File "/app/services/session.py", line 88, in store_session
    await redis_client.setex(session_key, 3600, session_data)
  File "/usr/local/lib/python3.12/site-packages/redis/asyncio/client.py", line 534, in execute_command
    return await self.parse_response(conn, command_name, **options)
redis.exceptions.ResponseError: OOM command not allowed when used memory > 'maxmemory'"""

STACK_TRACE_BAD_DEPLOY = """Traceback (most recent call last):
  File "/app/main.py", line 24, in <module>
    settings = Settings()
  File "/usr/local/lib/python3.12/site-packages/pydantic_settings/main.py", line 102, in __init__
    super().__init__(**values)
pydantic_core._pydantic_core.ValidationError: 1 validation error for Settings
STRIPE_API_KEY
  Field required [type=missing, input_value={}, input_type=dict]"""

STACK_TRACE_CASCADING_TIMEOUT = """Traceback (most recent call last):
  File "/app/clients/inventory.py", line 63, in reserve_stock
    response = await client.post("/api/v1/stock/reserve", json=payload, timeout=5.0)
  File "/usr/local/lib/python3.12/site-packages/httpx/_client.py", line 1802, in post
    return await self.send(request, timeout=timeout)
httpx.ReadTimeout: The read operation timed out after 5.0 seconds"""

STACK_TRACE_DISK_FULL = """Traceback (most recent call last):
  File "/app/workers/reports.py", line 77, in generate_invoice_pdf
    with open(temp_path, "wb") as f:
      f.write(rendered_pdf)
OSError: [Errno 28] No space left on device"""

STACK_TRACE_PAYMENT_GATEWAY_503 = """Traceback (most recent call last):
  File "/app/services/stripe_adapter.py", line 95, in charge
    charge = stripe.Charge.create(amount=amount, currency="usd", source=token)
  File "/usr/local/lib/python3.12/site-packages/stripe/api_resources/charge.py", line 32, in create
    return super(Charge, cls).create(*args, **kwargs)
stripe.error.APIConnectionError: Service Unavailable (HTTP 503): Cloudflare 503 Service Temporarily Unavailable"""

STACK_TRACE_CERTIFICATE_EXPIRY = """Traceback (most recent call last):
  File "/usr/local/lib/python3.12/site-packages/urllib3/connectionpool.py", line 790, in urlopen
    response = self._make_request(conn, method, url)
  File "/usr/local/lib/python3.12/site-packages/urllib3/connection.py", line 501, in connect
    self.sock = ssl_wrap_socket(sock=conn)
urllib3.exceptions.SSLError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired (_ssl.c:1129)"""


# ---------------------------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------------------------

def format_log_line(
    ts: datetime,
    level: str,
    service: str,
    message: str,
    as_json: bool = False,
    extra: dict[str, Any] | None = None,
) -> str:
    """Format a log event as either standard text or JSON string."""
    ts_str = ts.strftime("%Y-%m-%d %H:%M:%S")
    if as_json:
        data: dict[str, Any] = {
            "timestamp": ts.isoformat() + "Z",
            "level": level.upper(),
            "service": service,
            "message": message,
        }
        if extra:
            data.update(extra)
        return json.dumps(data)
    else:
        prefix = f"{ts_str} [{level.upper()}] [{service}] "
        if "\n" in message:
            # Multi-line message: prefix first line, keep subsequent lines intact
            lines = message.split("\n")
            return prefix + lines[0] + "\n" + "\n".join(lines[1:])
        return prefix + message


# ---------------------------------------------------------------------------
# Scenario Definitions
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, dict[str, Any]] = {
    "db_pool_exhaustion": {
        "title": "Database Connection Pool Exhaustion",
        "category": "db_pool_exhaustion",
        "origin_service": "checkout-service",
        "summary": "Database connection pool in checkout-service saturated under query hold-up, causing cascading 504 timeouts across api-gateway.",
        "expected_key_patterns": [
            "QueuePool limit of size 20 overflow 10 reached",
            "connection timed out, timeout 30.00",
            "HTTP 504 Gateway Timeout",
        ],
        "cascade_services": ["api-gateway", "frontend-service"],
    },
    "redis_oom": {
        "title": "Redis Out-of-Memory (OOM) Eviction Failure",
        "category": "redis_oom",
        "origin_service": "auth-service",
        "summary": "Redis cluster maxmemory reached with noeviction policy, rejecting session tokens and causing 401/500 session validation errors.",
        "expected_key_patterns": [
            "OOM command not allowed when used memory > 'maxmemory'",
            "Session lookup failed for user token",
            "Failed to persist user session",
        ],
        "cascade_services": ["api-gateway", "user-profile-service"],
    },
    "bad_deploy": {
        "title": "Bad Deploy / Missing Environment Variable",
        "category": "bad_deploy",
        "origin_service": "payment-service",
        "summary": "payment-service v2.4.1 deployed without mandatory STRIPE_API_KEY environment variable, crashing on initialization in crash loop.",
        "expected_key_patterns": [
            "1 validation error for Settings",
            "STRIPE_API_KEY",
            "Field required",
            "Deployment v2.4.1 failed to initialize",
        ],
        "cascade_services": ["checkout-service", "api-gateway"],
    },
    "cascading_timeout": {
        "title": "Cascading Downstream Timeout",
        "category": "cascading_timeout",
        "origin_service": "inventory-service",
        "summary": "inventory-service table lock bottleneck leads to 5s client timeouts, propagating thread pool starvation to order-service and api-gateway.",
        "expected_key_patterns": [
            "Deadlock detected waiting for table lock 'inventory_locks'",
            "httpx.ReadTimeout: The read operation timed out after 5.0 seconds",
            "Cascading timeout: downstream service 'inventory-service' did not respond",
        ],
        "cascade_services": ["order-service", "api-gateway"],
    },
    "disk_full": {
        "title": "Disk Full on Worker / Storage Volume",
        "category": "disk_full",
        "origin_service": "worker-service",
        "summary": "Worker root volume ran out of space during PDF invoice generation, failing background Celery tasks.",
        "expected_key_patterns": [
            "OSError: [Errno 28] No space left on device",
            "Task generate_invoice_pdf failed",
            "Failed to write temporary buffer to /var/tmp",
        ],
        "cascade_services": ["notification-service"],
    },
    "upstream_payment_gateway_503": {
        "title": "Upstream Payment Gateway 503 Outage",
        "category": "upstream_payment_gateway_503",
        "origin_service": "payment-service",
        "summary": "External payment gateway returned 503 Service Unavailable, tripping circuit breaker to OPEN state.",
        "expected_key_patterns": [
            "stripe.error.APIConnectionError: Service Unavailable (HTTP 503)",
            "Circuit breaker tripped to OPEN state for gateway 'stripe'",
            "Upstream payment processor returned 503",
        ],
        "cascade_services": ["checkout-service", "api-gateway"],
    },
    "memory_leak": {
        "title": "Memory Leak Leading to Kubernetes OOMKill",
        "category": "memory_leak",
        "origin_service": "recommendation-service",
        "summary": "Unbounded cache in recommendation-service exhausted container cgroup memory, triggering Linux OOM killer with exit code 137.",
        "expected_key_patterns": [
            "Memory usage exceeded threshold: 3840MB / 4096MB",
            "Out of memory: Kill process",
            "Container recommendation-engine terminated with exit code 137 (OOMKilled)",
        ],
        "cascade_services": ["api-gateway"],
    },
    "certificate_expiry": {
        "title": "TLS/SSL Internal Certificate Expiry",
        "category": "certificate_expiry",
        "origin_service": "auth-service",
        "summary": "Internal mTLS certificate for auth-service expired, breaking HTTPS communication from all upstream internal microservices.",
        "expected_key_patterns": [
            "urllib3.exceptions.SSLError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired",
            "SSL certificate verification failed for https://auth.internal.corp",
            "Internal RPC failed: CERTIFICATE_VERIFY_FAILED",
        ],
        "cascade_services": ["api-gateway", "checkout-service", "user-profile-service"],
    },
}


# ---------------------------------------------------------------------------
# Background Noise Generators
# ---------------------------------------------------------------------------

ROUTINE_PATHS = [
    "/healthz",
    "/ready",
    "/api/v1/catalog/items",
    "/api/v1/users/me",
    "/api/v1/cart/items",
    "/static/css/main.css",
    "/metrics",
    "/api/v1/promotions/active",
]

SERVICES = [
    "api-gateway",
    "auth-service",
    "checkout-service",
    "payment-service",
    "inventory-service",
    "worker-service",
    "recommendation-service",
]


def generate_routine_log(
    rng: random.Random,
    ts: datetime,
    service: str,
    as_json: bool = False,
) -> str:
    """Generate a single benign background log line."""
    action_type = rng.random()
    if action_type < 0.45:
        # HTTP access log
        path = rng.choice(ROUTINE_PATHS)
        duration = round(rng.uniform(4.5, 45.0), 2)
        status_code = 200 if rng.random() > 0.05 else 304
        msg = f"HTTP GET {path} returned {status_code} in {duration}ms"
        return format_log_line(ts, "INFO", service, msg, as_json=as_json)
    elif action_type < 0.70:
        # Health / Metric check
        msg = f"Periodic health check passed. Memory usage: {rng.randint(22, 58)}%, CPU: {rng.randint(5, 35)}%"
        return format_log_line(ts, "INFO", service, msg, as_json=as_json)
    elif action_type < 0.88:
        # Cache / Queue metric
        msg = f"Processed {rng.randint(10, 50)} background tasks from queue in {rng.randint(120, 450)}ms"
        return format_log_line(ts, "DEBUG", service, msg, as_json=as_json)
    else:
        # Minor warning (non-fatal)
        warns = [
            "Slow response from CDN node edge-us-east-1 (112ms)",
            "User session cookie refresh token close to expiration",
            "Rate limiter token bucket usage reached 65% for client ip 198.51.100.4",
        ]
        msg = rng.choice(warns)
        return format_log_line(ts, "WARN", service, msg, as_json=as_json)


# ---------------------------------------------------------------------------
# Incident Incident Log Sequences
# ---------------------------------------------------------------------------

def generate_incident_events(
    scenario_key: str,
    base_ts: datetime,
    origin_service: str,
    cascade_services: list[str],
    service_scope: str,
    as_json: bool,
) -> tuple[list[str], datetime, datetime]:
    """Generate sequential incident events reflecting cause -> cascade -> failure."""
    events: list[str] = []
    t = base_ts
    inc_start = t

    is_multi = service_scope == "multi_service"
    gw = "api-gateway" if is_multi else origin_service

    if scenario_key == "db_pool_exhaustion":
        # Phase 1: Warning signs
        events.append(format_log_line(t, "WARN", origin_service, "Database connection pool utilization high: 18/20 active connections", as_json=as_json))
        t += timedelta(seconds=12)
        events.append(format_log_line(t, "WARN", origin_service, "QueuePool checkout wait time exceeded 5000ms for thread 0x7fa9", as_json=as_json))
        t += timedelta(seconds=15)
        # Phase 2: Failure
        events.append(format_log_line(t, "ERROR", origin_service, f"Failed to acquire connection from pool.\n{STACK_TRACE_DB_POOL}", as_json=as_json))
        t += timedelta(seconds=8)
        events.append(format_log_line(t, "ERROR", origin_service, "QueuePool limit of size 20 overflow 10 reached, connection timed out, timeout 30.00", as_json=as_json))
        if is_multi:
            t += timedelta(seconds=5)
            events.append(format_log_line(t, "ERROR", gw, "HTTP POST /api/v1/checkout/complete failed: HTTP 504 Gateway Timeout from upstream checkout-service", as_json=as_json))
            t += timedelta(seconds=10)
            events.append(format_log_line(t, "ERROR", "frontend-service", "User checkout transaction failed with status 504: Order could not be placed", as_json=as_json))

    elif scenario_key == "redis_oom":
        events.append(format_log_line(t, "WARN", origin_service, "Redis memory warning: 94.2% of 4096MB used. Eviction policy: noeviction", as_json=as_json))
        t += timedelta(seconds=10)
        events.append(format_log_line(t, "ERROR", origin_service, f"Session cache write failed.\n{STACK_TRACE_REDIS_OOM}", as_json=as_json))
        t += timedelta(seconds=6)
        events.append(format_log_line(t, "ERROR", origin_service, "OOM command not allowed when used memory > 'maxmemory'", as_json=as_json))
        t += timedelta(seconds=8)
        events.append(format_log_line(t, "ERROR", origin_service, "Failed to persist user session token in cache: redis OOM", as_json=as_json))
        if is_multi:
            t += timedelta(seconds=5)
            events.append(format_log_line(t, "ERROR", gw, "Session lookup failed for user token: invalid or missing session data", as_json=as_json))
            t += timedelta(seconds=7)
            events.append(format_log_line(t, "WARN", gw, "Rejected request to /api/v1/orders with 401 Unauthorized: session validation error", as_json=as_json))

    elif scenario_key == "bad_deploy":
        events.append(format_log_line(t, "INFO", origin_service, "Rolling update deployment started: pulling image registry.corp/payment-service:v2.4.1", as_json=as_json))
        t += timedelta(seconds=8)
        events.append(format_log_line(t, "ERROR", origin_service, f"Fatal configuration error during application startup:\n{STACK_TRACE_BAD_DEPLOY}", as_json=as_json))
        t += timedelta(seconds=5)
        events.append(format_log_line(t, "FATAL", origin_service, "Deployment v2.4.1 failed to initialize: missing required configuration 'STRIPE_API_KEY'", as_json=as_json))
        t += timedelta(seconds=12)
        events.append(format_log_line(t, "ERROR", origin_service, "Container failed health check: CrashLoopBackOff (exit code 1)", as_json=as_json))
        if is_multi:
            t += timedelta(seconds=6)
            events.append(format_log_line(t, "ERROR", "checkout-service", "RPC to payment-service failed: connection refused on port 8000", as_json=as_json))
            t += timedelta(seconds=8)
            events.append(format_log_line(t, "ERROR", gw, "HTTP 502 Bad Gateway: payment-service unavailable during payment processing", as_json=as_json))

    elif scenario_key == "cascading_timeout":
        events.append(format_log_line(t, "WARN", origin_service, "Deadlock detected waiting for table lock 'inventory_locks' on row item_sku_9042", as_json=as_json))
        t += timedelta(seconds=10)
        events.append(format_log_line(t, "WARN", origin_service, "Transaction rollback executed due to deadlock timeout", as_json=as_json))
        t += timedelta(seconds=15)
        if is_multi:
            events.append(format_log_line(t, "ERROR", "order-service", f"Inventory reservation request failed:\n{STACK_TRACE_CASCADING_TIMEOUT}", as_json=as_json))
            t += timedelta(seconds=5)
            events.append(format_log_line(t, "ERROR", "order-service", "httpx.ReadTimeout: The read operation timed out after 5.0 seconds", as_json=as_json))
            t += timedelta(seconds=8)
            events.append(format_log_line(t, "ERROR", gw, "Cascading timeout: downstream service 'inventory-service' did not respond in 5000ms", as_json=as_json))
        else:
            events.append(format_log_line(t, "ERROR", origin_service, f"Reservation queue timed out waiting for lock:\n{STACK_TRACE_CASCADING_TIMEOUT}", as_json=as_json))

    elif scenario_key == "disk_full":
        events.append(format_log_line(t, "WARN", origin_service, "Disk usage on /var/tmp reached 98.9% (threshold 90%)", as_json=as_json))
        t += timedelta(seconds=12)
        events.append(format_log_line(t, "ERROR", origin_service, f"Task generate_invoice_pdf failed: [Errno 28] No space left on device\n{STACK_TRACE_DISK_FULL}", as_json=as_json))
        t += timedelta(seconds=7)
        events.append(format_log_line(t, "ERROR", origin_service, "OSError: [Errno 28] No space left on device", as_json=as_json))
        t += timedelta(seconds=8)
        events.append(format_log_line(t, "ERROR", origin_service, "Failed to write temporary buffer to /var/tmp/reports/batch_9410.pdf", as_json=as_json))
        if is_multi:
            t += timedelta(seconds=10)
            events.append(format_log_line(t, "ERROR", "notification-service", "Cannot attach PDF invoice to customer email: file does not exist", as_json=as_json))

    elif scenario_key == "upstream_payment_gateway_503":
        events.append(format_log_line(t, "WARN", origin_service, "Payment attempt failed with status 503 from Stripe API. Retrying in 1000ms (attempt 1/3)", as_json=as_json))
        t += timedelta(seconds=5)
        events.append(format_log_line(t, "ERROR", origin_service, f"Payment charge failed after 3 retries:\n{STACK_TRACE_PAYMENT_GATEWAY_503}", as_json=as_json))
        t += timedelta(seconds=8)
        events.append(format_log_line(t, "ERROR", origin_service, "stripe.error.APIConnectionError: Service Unavailable (HTTP 503)", as_json=as_json))
        t += timedelta(seconds=5)
        events.append(format_log_line(t, "WARN", origin_service, "Circuit breaker tripped to OPEN state for gateway 'stripe' due to 10 consecutive 503 errors", as_json=as_json))
        t += timedelta(seconds=6)
        events.append(format_log_line(t, "ERROR", origin_service, "Upstream payment processor returned 503: Service Unavailable", as_json=as_json))
        if is_multi:
            t += timedelta(seconds=8)
            events.append(format_log_line(t, "ERROR", "checkout-service", "Payment authorization rejected: circuit breaker OPEN", as_json=as_json))
            t += timedelta(seconds=6)
            events.append(format_log_line(t, "ERROR", gw, "HTTP 503 Service Unavailable: upstream payment processor down", as_json=as_json))

    elif scenario_key == "memory_leak":
        events.append(format_log_line(t, "WARN", origin_service, "Memory usage exceeded threshold: 3840MB / 4096MB (93.7%)", as_json=as_json))
        t += timedelta(seconds=15)
        events.append(format_log_line(t, "WARN", origin_service, "Garbage collector paused for 1420ms; freed only 12MB. Cache retention ratio 0.998", as_json=as_json))
        t += timedelta(seconds=10)
        events.append(format_log_line(t, "FATAL", origin_service, "kernel: [129481.102] Out of memory: Kill process 18491 (python) score 950 or sacrifice child", as_json=as_json))
        t += timedelta(seconds=3)
        events.append(format_log_line(t, "FATAL", origin_service, "Killed process 18491 (python) total-vm:4194304kB, anon-rss:3981312kB", as_json=as_json))
        t += timedelta(seconds=5)
        events.append(format_log_line(t, "FATAL", "orchestrator", "Container recommendation-engine terminated with exit code 137 (OOMKilled)", as_json=as_json))
        if is_multi:
            t += timedelta(seconds=8)
            events.append(format_log_line(t, "ERROR", gw, "Upstream recommendation-service connection reset by peer during feed fetch", as_json=as_json))

    elif scenario_key == "certificate_expiry":
        events.append(format_log_line(t, "WARN", origin_service, "TLS cert validation notice: internal mTLS cert expires in 0 days (subject /CN=auth.internal.corp)", as_json=as_json))
        t += timedelta(seconds=10)
        events.append(format_log_line(t, "ERROR", "checkout-service", f"Failed to authenticate inter-service request:\n{STACK_TRACE_CERTIFICATE_EXPIRY}", as_json=as_json))
        t += timedelta(seconds=5)
        events.append(format_log_line(t, "ERROR", "checkout-service", "urllib3.exceptions.SSLError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired (_ssl.c:1129)", as_json=as_json))
        t += timedelta(seconds=8)
        events.append(format_log_line(t, "ERROR", gw, "SSL certificate verification failed for https://auth.internal.corp:8443", as_json=as_json))
        t += timedelta(seconds=6)
        events.append(format_log_line(t, "ERROR", gw, "Internal RPC failed: CERTIFICATE_VERIFY_FAILED", as_json=as_json))

    inc_end = t
    return events, inc_start, inc_end


# ---------------------------------------------------------------------------
# Full Scenario File Generator
# ---------------------------------------------------------------------------

def generate_scenario_dataset(
    rng: random.Random,
    scenario_id: str,
    scenario_meta: dict[str, Any],
    noise_level: str,
    service_scope: str,
    as_json: bool,
) -> tuple[str, dict[str, Any]]:
    """Build log lines for an incident scenario variant, returning logs text and ground truth."""
    base_ts = datetime(2026, 11, 10, 14, 0, 0, tzinfo=timezone.utc)
    origin_service = scenario_meta["origin_service"]
    cascade_services = scenario_meta.get("cascade_services", [])
    active_services = (
        [origin_service] + cascade_services
        if service_scope == "multi_service"
        else [origin_service]
    )

    # Determine line counts
    if noise_level == "low":
        pre_noise_count = rng.randint(40, 70)
        post_noise_count = rng.randint(40, 70)
    else:
        pre_noise_count = rng.randint(450, 750)
        post_noise_count = rng.randint(450, 750)

    all_lines: list[tuple[datetime, str]] = []

    # 1. Pre-incident healthy logs
    curr_ts = base_ts
    for _ in range(pre_noise_count):
        curr_ts += timedelta(milliseconds=rng.randint(200, 1500))
        srv = rng.choice(active_services)
        line = generate_routine_log(rng, curr_ts, srv, as_json=as_json)
        all_lines.append((curr_ts, line))

    # 2. Incident logs
    curr_ts += timedelta(seconds=5)
    incident_events, inc_start, inc_end = generate_incident_events(
        scenario_meta["category"],
        curr_ts,
        origin_service,
        cascade_services,
        service_scope,
        as_json,
    )
    for evt in incident_events:
        curr_ts += timedelta(seconds=rng.randint(3, 8))
        all_lines.append((curr_ts, evt))

    # 3. Post-incident logs (mix of errors continuing and routine logs)
    for _ in range(post_noise_count):
        curr_ts += timedelta(milliseconds=rng.randint(200, 1500))
        srv = rng.choice(active_services)
        if rng.random() < 0.25:
            # Recurring intermittent error log
            msg = f"HTTP 500 / request dropped while {origin_service} is degraded"
            line = format_log_line(curr_ts, "ERROR", srv, msg, as_json=as_json)
        else:
            line = generate_routine_log(rng, curr_ts, srv, as_json=as_json)
        all_lines.append((curr_ts, line))

    # Format into complete file content
    content = "\n".join(line for _, line in all_lines) + "\n"
    total_lines = len(content.strip().split("\n"))

    ground_truth = {
        "scenario_id": scenario_id,
        "has_incident": True,
        "root_cause_category": scenario_meta["category"],
        "origin_service": origin_service,
        "start_time": inc_start.isoformat(),
        "end_time": inc_end.isoformat(),
        "expected_key_patterns": scenario_meta["expected_key_patterns"],
        "noise_level": noise_level,
        "service_scope": service_scope,
        "total_lines": total_lines,
        "summary": scenario_meta["summary"],
    }
    return content, ground_truth


# ---------------------------------------------------------------------------
# Control Datasets
# ---------------------------------------------------------------------------

def generate_control_steady_state(rng: random.Random) -> tuple[str, dict[str, Any]]:
    """Build healthy steady-state control dataset with zero incidents."""
    base_ts = datetime(2026, 11, 10, 14, 0, 0, tzinfo=timezone.utc)
    curr_ts = base_ts
    all_lines: list[str] = []

    for _ in range(450):
        curr_ts += timedelta(milliseconds=rng.randint(150, 950))
        srv = rng.choice(SERVICES)
        all_lines.append(generate_routine_log(rng, curr_ts, srv, as_json=False))

    content = "\n".join(all_lines) + "\n"
    total_lines = len(content.strip().split("\n"))
    ground_truth = {
        "scenario_id": "control_steady_state",
        "has_incident": False,
        "root_cause_category": "none",
        "origin_service": "none",
        "start_time": base_ts.isoformat(),
        "end_time": curr_ts.isoformat(),
        "expected_key_patterns": [],
        "noise_level": "low",
        "service_scope": "multi_service",
        "total_lines": total_lines,
        "summary": "Healthy steady-state production traffic with normal periodic health checks.",
    }
    return content, ground_truth


def generate_control_benign_traffic_spike(rng: random.Random) -> tuple[str, dict[str, Any]]:
    """Build benign traffic spike control dataset with scaling but zero errors."""
    base_ts = datetime(2026, 11, 10, 14, 0, 0, tzinfo=timezone.utc)
    curr_ts = base_ts
    all_lines: list[str] = []

    # Baseline traffic
    for _ in range(150):
        curr_ts += timedelta(milliseconds=rng.randint(100, 500))
        srv = rng.choice(SERVICES)
        all_lines.append(generate_routine_log(rng, curr_ts, srv, as_json=True))

    # Traffic surge & Autoscaler response
    spike_start = curr_ts
    all_lines.append(format_log_line(curr_ts, "INFO", "api-gateway", "Inbound request rate spiked by 650% (Flash sale campaign active)", as_json=True))
    for _ in range(300):
        curr_ts += timedelta(milliseconds=rng.randint(20, 120))
        srv = rng.choice(SERVICES)
        all_lines.append(generate_routine_log(rng, curr_ts, srv, as_json=True))

    all_lines.append(format_log_line(curr_ts, "INFO", "orchestrator", "HorizontalPodAutoscaler triggered: scaling checkout-service replicas from 4 to 16", as_json=True))
    all_lines.append(format_log_line(curr_ts, "INFO", "orchestrator", "Successfully scheduled and launched 12 new worker pods", as_json=True))

    # Post-surge stabilization
    for _ in range(150):
        curr_ts += timedelta(milliseconds=rng.randint(100, 400))
        srv = rng.choice(SERVICES)
        all_lines.append(generate_routine_log(rng, curr_ts, srv, as_json=True))

    content = "\n".join(all_lines) + "\n"
    total_lines = len(content.strip().split("\n"))
    ground_truth = {
        "scenario_id": "control_benign_traffic_spike",
        "has_incident": False,
        "root_cause_category": "none",
        "origin_service": "none",
        "start_time": spike_start.isoformat(),
        "end_time": curr_ts.isoformat(),
        "expected_key_patterns": [],
        "noise_level": "high",
        "service_scope": "multi_service",
        "total_lines": total_lines,
        "summary": "Benign 650% traffic spike managed cleanly by horizontal autoscaler without dropped requests or failures.",
    }
    return content, ground_truth


# ---------------------------------------------------------------------------
# CLI and Orchestration
# ---------------------------------------------------------------------------

def generate_all(seed: int = 42, output_dir: str = "simulator/scenarios", gt_path: str = "simulator/ground_truth.json") -> dict[str, dict[str, Any]]:
    """Generate all 34 scenario datasets and write ground truth."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    gt_file = Path(gt_path)
    gt_file.parent.mkdir(parents=True, exist_ok=True)

    master_rng = random.Random(seed)
    all_ground_truth: dict[str, dict[str, Any]] = {}

    variants = [
        ("low", "single_service"),
        ("low", "multi_service"),
        ("high", "single_service"),
        ("high", "multi_service"),
    ]

    scenario_count = 0

    # 1. Generate 8 scenarios * 4 variants = 32 incident files
    for sc_idx, (sc_key, sc_meta) in enumerate(SCENARIOS.items()):
        for var_idx, (noise, scope) in enumerate(variants):
            scenario_id = f"{sc_key}_{noise}_noise_{scope}"
            # Alternate format: even index standard text, odd index JSON Lines
            as_json = (sc_idx + var_idx) % 2 == 1

            # Seed per scenario for reproducibility
            sc_seed = master_rng.randint(1, 10_000_000)
            sc_rng = random.Random(sc_seed)

            content, gt = generate_scenario_dataset(
                sc_rng, scenario_id, sc_meta, noise, scope, as_json
            )

            file_path = out_path / f"{scenario_id}.log"
            file_path.write_text(content, encoding="utf-8")
            all_ground_truth[scenario_id] = gt
            scenario_count += 1

    # 2. Control 1: Healthy steady state
    ctrl1_rng = random.Random(master_rng.randint(1, 10_000_000))
    ctrl1_content, ctrl1_gt = generate_control_steady_state(ctrl1_rng)
    (out_path / "control_steady_state.log").write_text(ctrl1_content, encoding="utf-8")
    all_ground_truth["control_steady_state"] = ctrl1_gt
    scenario_count += 1

    # 3. Control 2: Benign traffic spike
    ctrl2_rng = random.Random(master_rng.randint(1, 10_000_000))
    ctrl2_content, ctrl2_gt = generate_control_benign_traffic_spike(ctrl2_rng)
    (out_path / "control_benign_traffic_spike.log").write_text(ctrl2_content, encoding="utf-8")
    all_ground_truth["control_benign_traffic_spike"] = ctrl2_gt
    scenario_count += 1

    # Write ground truth JSON
    gt_file.write_text(json.dumps(all_ground_truth, indent=2), encoding="utf-8")
    print(f"Generated {scenario_count} scenarios in {output_dir}")
    print(f"Saved ground truth metadata to {gt_path}")
    return all_ground_truth


def main():
    parser = argparse.ArgumentParser(description="IncidentLens Realistic Log and Incident Generator")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for deterministic generation")
    parser.add_argument("--output-dir", type=str, default="simulator/scenarios", help="Output directory for log files")
    parser.add_argument("--ground-truth", type=str, default="simulator/ground_truth.json", help="Path to ground truth JSON output")
    args = parser.parse_args()

    generate_all(seed=args.seed, output_dir=args.output_dir, gt_path=args.ground_truth)


if __name__ == "__main__":
    main()
