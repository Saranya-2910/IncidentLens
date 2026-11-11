"""Unit tests for log message normalisation, token masking, and stack trace fingerprinting."""

from app.pipeline.normaliser.normaliser import Normaliser


def test_token_masking_uuids_and_numbers():
    """Verify UUIDs and numeric values are collapsed to standard tokens."""
    msg1 = "User 550e8400-e29b-41d4-a716-446655440000 performed action 42 in 150ms"
    msg2 = "User 7c9e6679-7425-40de-944b-e07fc1f90ae7 performed action 999 in 2500ms"

    norm1 = Normaliser.process(msg1, level="INFO")
    norm2 = Normaliser.process(msg2, level="INFO")

    expected_template = "User <UUID> performed action <NUM> in <NUM>ms"
    assert norm1.template == expected_template
    assert norm2.template == expected_template
    assert norm1.fingerprint == norm2.fingerprint


def test_token_masking_ips_hosts_and_paths():
    """Verify IP addresses, URLs, hosts, and file paths are masked."""
    msg = (
        "Failed connecting to 192.168.1.105:8080 from auth.internal.corp: "
        "cannot open /var/log/app/output.log after 5.0 seconds"
    )
    norm = Normaliser.process(msg, level="ERROR")

    assert "<HOST>" in norm.template or "<IP>" in norm.template
    assert "<PATH>" in norm.template
    assert "<NUM>ms" in norm.template
    assert "192.168.1.105" not in norm.template
    assert "/var/log/app/output.log" not in norm.template


def test_token_masking_quoted_strings_and_memory_ptrs():
    """Verify quoted parameters and hex pointers are masked."""
    msg1 = "Lock timeout waiting for table lock 'inventory_locks' held by thread 0x7fa9"
    msg2 = "Lock timeout waiting for table lock 'orders_locks' held by thread 0x4bc2"

    norm1 = Normaliser.process(msg1, level="WARN")
    norm2 = Normaliser.process(msg2, level="WARN")

    expected_template = "Lock timeout waiting for table lock '<STR>' held by thread <HEX>"
    assert norm1.template == expected_template
    assert norm2.template == expected_template
    assert norm1.fingerprint == norm2.fingerprint


def test_distinct_messages_produce_distinct_fingerprints():
    """Verify lines with different semantic meaning map to distinct fingerprints."""
    msg_a = "Database connection pool utilization high: 18/20 active connections"
    msg_b = "QueuePool limit of size 20 overflow 10 reached, connection timed out"
    msg_c = "Session lookup failed for user token"

    norm_a = Normaliser.process(msg_a, level="WARN")
    norm_b = Normaliser.process(msg_b, level="ERROR")
    norm_c = Normaliser.process(msg_c, level="ERROR")

    assert norm_a.fingerprint != norm_b.fingerprint
    assert norm_b.fingerprint != norm_c.fingerprint
    assert norm_a.fingerprint != norm_c.fingerprint


def test_python_stack_trace_fingerprinting_resilience():
    """Verify stack traces with different line numbers map to the same fingerprint."""
    tb1 = """Traceback (most recent call last):
  File "/app/services/checkout.py", line 142, in process_checkout
    async with db.begin():
  File "/app/db/session.py", line 55, in begin
    conn = await pool.connect()
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/pool/impl.py", line 403, in connect
    return await self._connection_record()
sqlalchemy.exc.TimeoutError: QueuePool limit of size 20 overflow 10 reached, connection timed out, timeout 30.00"""

    tb2 = """Traceback (most recent call last):
  File "/app/services/checkout.py", line 290, in process_checkout
    async with db.begin():
  File "/app/db/session.py", line 112, in begin
    conn = await pool.connect()
  File "/usr/local/lib/python3.12/site-packages/sqlalchemy/pool/impl.py", line 450, in connect
    return await self._connection_record()
sqlalchemy.exc.TimeoutError: QueuePool limit of size 20 overflow 10 reached, connection timed out, timeout 30.00"""

    res1 = Normaliser.process(tb1, level="ERROR")
    res2 = Normaliser.process(tb2, level="ERROR")

    assert res1.is_stack_trace is True
    assert res2.is_stack_trace is True
    assert "checkout.py:process_checkout" in res1.template
    assert "impl.py:connect" in res1.template
    assert res1.template == res2.template
    assert res1.fingerprint == res2.fingerprint


def test_fingerprint_stability():
    """Verify fingerprint is strictly deterministic across repeated calls."""
    msg = "Payment charge failed: stripe.error.APIConnectionError: Service Unavailable"
    fp1 = Normaliser.process(msg, level="ERROR").fingerprint
    fp2 = Normaliser.process(msg, level="ERROR").fingerprint

    assert fp1 == fp2
    assert len(fp1) == 64
