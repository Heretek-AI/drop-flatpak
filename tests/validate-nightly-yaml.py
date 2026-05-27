#!/usr/bin/env python3
"""Validate .github/workflows/nightly.yml is a valid GitHub Actions workflow document.

Checks YAML correctness and top-level schema: the document must be a dict
with required keys (name, on, jobs) in the expected shapes.
"""

import sys
import yaml
from pathlib import Path

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "nightly.yml"


def load_workflow():
    assert WORKFLOW_PATH.exists(), f"Workflow file not found: {WORKFLOW_PATH}"
    with open(WORKFLOW_PATH) as f:
        return yaml.safe_load(f)


def main():
    print(f"Validating YAML correctness: {WORKFLOW_PATH}")

    # 1. Load YAML
    wf = load_workflow()

    # 2. Top-level must be a dict (not None, not a list)
    assert isinstance(wf, dict), (
        f"Top-level document must be a dict, got: {type(wf).__name__}"
    )

    # 3. name: non-empty string
    name = wf.get("name")
    assert isinstance(name, str) and len(name) > 0, (
        f"'name' must be a non-empty string, got: {name!r}"
    )

    # 4. on: dict with at least one trigger key
    # PyYAML 5.x parses 'on' as boolean True (YAML 1.1), so try both.
    on_block = wf.get(True) or wf.get("on") or {}
    assert isinstance(on_block, dict), (
        f"'on' must be a dict, got: {type(on_block).__name__}"
    )
    assert len(on_block) >= 1, (
        f"'on' must define at least one trigger, got {len(on_block)} key(s)"
    )

    # 5. jobs: dict with at least one job
    jobs = wf.get("jobs", {})
    assert isinstance(jobs, dict), (
        f"'jobs' must be a dict, got: {type(jobs).__name__}"
    )
    assert len(jobs) >= 1, (
        f"'jobs' must contain at least one job, got {len(jobs)} job(s)"
    )

    # 6. Each job: runs-on (string) + steps (non-empty list) + timeout-minutes
    for job_id, job in jobs.items():
        runs_on = job.get("runs-on")
        assert isinstance(runs_on, str) and len(runs_on) > 0, (
            f"job '{job_id}': 'runs-on' must be a non-empty string, got: {runs_on!r}"
        )

        timeout = job.get("timeout-minutes")
        assert timeout is not None, (
            f"job '{job_id}': 'timeout-minutes' is required but missing"
        )

        steps = job.get("steps", [])
        assert isinstance(steps, list) and len(steps) > 0, (
            f"job '{job_id}': 'steps' must be a non-empty list, "
            f"got {len(steps)} step(s)"
        )

        # 7. Every step must have either uses or run key
        for i, step in enumerate(steps):
            has_uses = "uses" in step
            has_run = "run" in step
            assert has_uses or has_run, (
                f"job '{job_id}', step {i}: must have 'uses' or 'run' key; "
                f"found keys: {list(step.keys())}"
            )

        print(f"  Job '{job_id}': runs-on={runs_on}, "
              f"timeout={timeout}min, steps={len(steps)}")

    print("\nOK: valid GitHub Actions workflow YAML")
    return 0


if __name__ == "__main__":
    sys.exit(main())
