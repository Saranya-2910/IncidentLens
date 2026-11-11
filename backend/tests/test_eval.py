"""Tests for Phase 10: End-to-End Evaluation Benchmark Runner."""

from pathlib import Path

from eval.run_eval import run_evaluation


def test_end_to_end_evaluation_offline(tmp_path: Path):
    """Run full 34-scenario evaluation end-to-end offline and assert quality gates."""
    out_md = tmp_path / "results.md"
    summary = run_evaluation(
        mode="offline",
        naive_tail=100,
        output_path=str(out_md),
    )

    assert out_md.exists()
    content = out_md.read_text(encoding="utf-8")
    assert "Headline Comparison Table" in content

    il = summary["incidentlens"]
    nb = summary["naive_baseline"]

    assert summary["total_scenarios"] == 34
    assert il["incident_recall"] == 100.0
    assert il["control_false_alarms"] == "0/2"
    assert il["origin_top3_accuracy"] == 100.0
    assert il["root_cause_accuracy"] >= 95.0
    assert il["citation_validity_rate"] == 100.0
    assert il["log_reduction_ratio"] >= 95.0

    # Verify IncidentLens substantially outperforms Naive Tail Baseline
    assert il["root_cause_accuracy"] > nb["root_cause_accuracy"]
    assert il["avg_tokens_per_report"] < nb["avg_tokens_per_report"]
