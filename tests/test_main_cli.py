"""
End-to-end smoke test: runs the actual CLI entry point as a subprocess,
exactly the way a user would (`python main.py --demo --run-all`), and
checks the whole pipeline -- argument parsing, registry population,
concurrent execution, CSV logging, and the post-run session cleanup --
completes without error and produces the documented output files.
"""
import csv
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_cli(args, cwd):
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "main.py"), *args],
        cwd=cwd, capture_output=True, text=True, timeout=60,
    )


def test_demo_run_all_produces_csv_output(tmp_path):
    result = run_cli(["--demo", "--run-all", "--output-dir", str(tmp_path)], cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "Backend: mock" in result.stdout

    results_csv = tmp_path / "DQ_RESULTS.csv"
    run_log_csv = tmp_path / "DQ_RUN_LOG.csv"
    assert results_csv.exists()
    assert run_log_csv.exists()

    with open(results_csv, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) > 0
    assert {"check_id", "check_type", "status", "pass_fail_flag"} <= set(rows[0].keys())


def test_demo_sequential_matches_concurrent_check_count(tmp_path):
    seq_dir = tmp_path / "seq"
    conc_dir = tmp_path / "conc"
    seq_dir.mkdir()
    conc_dir.mkdir()

    seq_result = run_cli(["--demo", "--run-all", "--sequential", "--output-dir", str(seq_dir)], cwd=seq_dir)
    conc_result = run_cli(["--demo", "--run-all", "--output-dir", str(conc_dir)], cwd=conc_dir)

    assert seq_result.returncode == 0, seq_result.stderr
    assert conc_result.returncode == 0, conc_result.stderr

    def attempted(stdout):
        line = next(l for l in stdout.splitlines() if "attempted=" in l)
        return line.split("attempted=")[1].split()[0]

    assert attempted(seq_result.stdout) == attempted(conc_result.stdout)


def test_no_scope_flag_exits_with_usage_error(tmp_path):
    result = run_cli(["--demo"], cwd=tmp_path)
    assert result.returncode == 1
    assert "Specify one of" in result.stderr


def test_demo_table_filter_scopes_to_matching_checks(tmp_path):
    result = run_cli(["--demo", "--table", "CUSTOMERS", "--output-dir", str(tmp_path)], cwd=tmp_path)
    assert result.returncode == 0, result.stderr

    with open(tmp_path / "DQ_RESULTS.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    # Sample config: only CHECK_ID 204 (TYPE check) targets CUSTOMERS.
    assert len(rows) == 1
    assert rows[0]["check_type"] == "TYPE"
