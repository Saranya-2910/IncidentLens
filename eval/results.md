# IncidentLens Evaluation & Benchmark Results

Evaluated across **34 simulated scenarios** (32 incident variants across 8 failure categories + 2 negative control datasets, totaling **22,416 raw log lines**) comparing the deterministic **IncidentLens Pipeline** against a **Naive Tail Baseline** (sending the last 100 raw lines directly to the LLM without grouping, anomaly detection, or evidence IDs).

> **Evaluation Mode**: `offline` (deterministic reproducible runner)

## Headline Comparison Table

| Metric | IncidentLens Pipeline | Naive Tail Baseline (Last 100 Lines) |
| :--- | :--- | :--- |
| **Incident Detection Recall** | **100.0%** (32/32) | N/A (no detector) |
| **Control Dataset False Alarms** | **0/2** (0% false positives) | 2/2 |
| **Origin Pattern Top-1 Accuracy** | **100.0%** | N/A |
| **Origin Pattern Top-3 Accuracy** | **100.0%** | N/A |
| **Root-Cause Category Accuracy** | **100.0%** | 46.9% |
| **Origin Service Accuracy** | **93.8%** | 62.5% |
| **Citation Validity Rate** | **100.0%** (DB-verified IDs) | 0.0% (no verification) |
| **Unsupported Claim Rate** | **0.0%** | 100.0 (unverified) |
| **Log Reduction Ratio** | **98.42%** (354 / 22,416 lines) | 84.85% (3,395 / 22,416 lines) |
| **Avg Tokens per Report** | **1003.1 tokens** | 3838.1 tokens |
| **Avg End-to-End Latency** | **108.6 ms** | 0.5 ms |

## Honest Discussion of Failures, Edge Cases, and Limitations

1. **Caller vs. Upstream `WARN` Origin Misses (Origin Service 30/32)**:
   - In `cascading_timeout_low_noise_multi_service` and `cascading_timeout_high_noise_multi_service` (`inventory-service` -> `order-service`), the true origin service (`inventory-service`) emitted `WARN` precursor deadlock notices before the caller (`order-service`) emitted the first `ERROR`-level exception (`httpx.ReadTimeout`). Because `IncidentDetector` buckets strictly on `ERROR`/`FATAL` levels to eliminate baseline warning noise, the Top-1 error candidate identified `order-service` as the error emitter, even though `EvidenceSelector` included the precursor warnings and enabled 100% Top-1/Top-3 origin-pattern and root-cause category accuracy.
2. **Why Naive Tail Baseline Drops on High-Noise Scenarios**:
   - In high-noise logs (1,100–2,000+ lines), the triggering root-cause stack trace occurs near the onset of the outage and is followed by hundreds of routine health checks and generic `HTTP 500 / request dropped` messages. Sending only the trailing `N=100` raw lines causes the Naive baseline to miss the root cause completely, while also incurring higher prompt token usage and lacking any backend citation verification or PII redaction.
3. **Offline vs. Live LLM Caveat**:
   - CI runs execute in deterministic `--mode offline` (using `FakeLLMClient` heuristic extraction and `FakeEmbeddingClient` token hashing) so automated builds remain reproducible without external API keys. Running `--mode gemini` uses live `gemini-2.0-flash` subject to external API latency and network availability.

## Per-Scenario Breakdown

| Scenario ID | Noise | Raw Lines | IncidentLens Sent | IL Root Cause | Naive Root Cause | Notes |
| :--- | :--- | ---: | ---: | :---: | :---: | :--- |
| `db_pool_exhaustion_low_noise_single_service` | low | 125 | 13 | PASS | PASS | - |
| `db_pool_exhaustion_low_noise_multi_service` | low | 116 | 11 | PASS | PASS | - |
| `db_pool_exhaustion_high_noise_single_service` | high | 1259 | 13 | PASS | MISS | - |
| `db_pool_exhaustion_high_noise_multi_service` | high | 1207 | 15 | PASS | MISS | - |
| `redis_oom_low_noise_single_service` | low | 131 | 10 | PASS | PASS | - |
| `redis_oom_low_noise_multi_service` | low | 135 | 11 | PASS | PASS | - |
| `redis_oom_high_noise_single_service` | high | 1093 | 10 | PASS | MISS | - |
| `redis_oom_high_noise_multi_service` | high | 1223 | 11 | PASS | MISS | - |
| `bad_deploy_low_noise_single_service` | low | 134 | 10 | PASS | PASS | - |
| `bad_deploy_low_noise_multi_service` | low | 95 | 12 | PASS | PASS | - |
| `bad_deploy_high_noise_single_service` | high | 1035 | 10 | PASS | MISS | - |
| `bad_deploy_high_noise_multi_service` | high | 1423 | 12 | PASS | MISS | - |
| `cascading_timeout_low_noise_single_service` | low | 118 | 12 | PASS | PASS | - |
| `cascading_timeout_low_noise_multi_service` | low | 114 | 10 | PASS | PASS | - |
| `cascading_timeout_high_noise_single_service` | high | 1173 | 12 | PASS | MISS | - |
| `cascading_timeout_high_noise_multi_service` | high | 1203 | 10 | PASS | MISS | - |
| `disk_full_low_noise_single_service` | low | 144 | 10 | PASS | PASS | - |
| `disk_full_low_noise_multi_service` | low | 108 | 11 | PASS | PASS | - |
| `disk_full_high_noise_single_service` | high | 1235 | 10 | PASS | MISS | - |
| `disk_full_high_noise_multi_service` | high | 1334 | 11 | PASS | MISS | - |
| `upstream_payment_gateway_503_low_noise_single_service` | low | 101 | 10 | PASS | PASS | - |
| `upstream_payment_gateway_503_low_noise_multi_service` | low | 136 | 12 | PASS | PASS | - |
| `upstream_payment_gateway_503_high_noise_single_service` | high | 1269 | 10 | PASS | MISS | - |
| `upstream_payment_gateway_503_high_noise_multi_service` | high | 1102 | 12 | PASS | MISS | - |
| `memory_leak_low_noise_single_service` | low | 136 | 10 | PASS | PASS | - |
| `memory_leak_low_noise_multi_service` | low | 117 | 11 | PASS | MISS | - |
| `memory_leak_high_noise_single_service` | high | 1102 | 10 | PASS | MISS | - |
| `memory_leak_high_noise_multi_service` | high | 1326 | 11 | PASS | MISS | - |
| `certificate_expiry_low_noise_single_service` | low | 116 | 11 | PASS | PASS | - |
| `certificate_expiry_low_noise_multi_service` | low | 141 | 11 | PASS | PASS | - |
| `certificate_expiry_high_noise_single_service` | high | 1305 | 11 | PASS | MISS | - |
| `certificate_expiry_high_noise_multi_service` | high | 1107 | 11 | PASS | MISS | - |
| `control_steady_state` | low | 450 | 0 | PASS | MISS | Control (0 alerts) |
| `control_benign_traffic_spike` | high | 603 | 0 | PASS | MISS | Control (0 alerts) |
