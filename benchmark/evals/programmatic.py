"""Programmatic evaluators — manifest-based scoring."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from benchmark.schemas.agents import FixerOutput, ScoutOutput

MANIFEST_PATH = Path(__file__).parent.parent.parent / "bugs_manifest.json"
TARGET_PROJECT_PATH = Path(__file__).parent.parent.parent / "target_project"


def load_manifest() -> list[dict]:
    """Load the bug manifest (ground truth)."""
    return json.loads(MANIFEST_PATH.read_text())


def eval_scout(output: ScoutOutput) -> dict:
    """Score scout findings against the bug manifest."""
    manifest = load_manifest()
    detected: set[str] = set()
    false_positives = 0

    for finding in output.findings:
        matched = _match_finding_to_manifest(finding, manifest)
        if matched:
            detected.add(matched)
        else:
            false_positives += 1

    total_bugs = len(manifest)
    return {
        "bugs_detected": len(detected),
        "detection_recall": len(detected) / total_bugs if total_bugs else 0,
        "false_positives": false_positives,
        "detected_ids": sorted(detected),
        "missed_ids": sorted(set(b["bug_id"] for b in manifest) - detected),
        "gate_pass": len(detected) >= 3,
    }


def eval_fixer(output: FixerOutput) -> dict:
    """Score fixer output by running manifest tests against the fixed code."""
    manifest = load_manifest()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Copy the target project structure
        _copy_target_project(tmpdir_path)

        # Overwrite with fixed files
        for fixed_file in output.fixed_files:
            dest = tmpdir_path / fixed_file.path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(fixed_file.content)

        # Run manifest tests (one per bug)
        results: dict[str, dict] = {}
        for bug in manifest:
            test_result = _run_manifest_test(tmpdir_path, bug)
            results[bug["bug_id"]] = test_result

        # Run existing tests (regression check)
        existing = _run_existing_tests(tmpdir_path)

        fixed_count = sum(1 for r in results.values() if r["fixed"])
        total_bugs = len(manifest)

        return {
            "bugs_fixed_correctly": fixed_count,
            "fix_rate": fixed_count / total_bugs if total_bugs else 0,
            "existing_tests_still_pass": existing["all_passed"],
            "regressions": existing["failed_count"],
            "per_bug": results,
            "gate_pass": fixed_count >= 2 and existing["all_passed"],
        }


def _match_finding_to_manifest(finding, manifest: list[dict]) -> str | None:
    """Fuzzy-match a scout finding to a manifest bug. Returns bug_id or None."""
    for bug in manifest:
        file_match = bug["file"] in finding.file or finding.file in bug["file"]
        line_close = abs(finding.line - bug["line"]) <= 5
        category_match = finding.category.lower() == bug["category"].lower()
        keyword_match = any(
            kw.lower() in finding.description.lower() for kw in bug.get("keywords", [])
        )

        if file_match and (line_close or category_match or keyword_match):
            return bug["bug_id"]
    return None


def _copy_target_project(dest: Path) -> None:
    """Copy the target project to a temp directory."""
    import shutil

    src = TARGET_PROJECT_PATH
    for item in src.rglob("*"):
        if item.is_file() and "__pycache__" not in str(item):
            rel = item.relative_to(src)
            target = dest / "target_project" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _run_manifest_test(project_dir: Path, bug: dict) -> dict:
    """Run a single manifest test for one bug."""
    test_file = Path(__file__).parent.parent.parent / "bugs_manifest_tests" / bug["test_file"]
    if not test_file.exists():
        return {"fixed": False, "error": f"Test file not found: {bug['test_file']}"}

    result = subprocess.run(
        ["python", "-m", "pytest", str(test_file), "-v", "--tb=short", "-x"],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(project_dir),
    )
    return {
        "fixed": result.returncode == 0,
        "error": result.stderr[:500] if result.returncode != 0 else None,
    }


def _run_existing_tests(project_dir: Path) -> dict:
    """Run the existing test suite to check for regressions."""
    test_dir = project_dir / "target_project" / "tests"
    if not test_dir.exists():
        return {"all_passed": True, "failed_count": 0, "total": 0}

    result = subprocess.run(
        ["python", "-m", "pytest", str(test_dir), "-v", "--tb=short"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(project_dir),
    )

    # Parse pytest output for counts
    failed = result.stdout.count(" FAILED")
    passed = result.stdout.count(" PASSED")

    return {
        "all_passed": result.returncode == 0,
        "failed_count": failed,
        "passed_count": passed,
        "total": failed + passed,
    }
