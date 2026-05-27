#!/usr/bin/env python3
"""Validate the nightly workflow YAML structure and completeness.

Asserts all required triggers, steps, and artifact settings
are present in .github/workflows/nightly.yml.
"""

import sys
import yaml
from pathlib import Path

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "nightly.yml"

def load_workflow():
    assert WORKFLOW_PATH.exists(), f"Workflow file not found: {WORKFLOW_PATH}"
    with open(WORKFLOW_PATH) as f:
        return yaml.safe_load(f)


def test_triggers(wf):
    """Verify schedule cron and workflow_dispatch trigger."""
    # PyYAML 5.x parses 'on' as boolean True (YAML 1.1 spec).
    # Access the triggers block via the True key.
    on_block = wf.get(True, {})
    if not on_block and "on" in wf:
        on_block = wf.get("on", {})
    assert on_block, "Missing 'on' triggers block in workflow"

    # Schedule trigger with cron
    schedule = on_block.get("schedule", [])
    assert isinstance(schedule, list) and len(schedule) > 0, "Missing on.schedule trigger"
    cron = schedule[0].get("cron", "")
    assert "0 3 *" in cron, f"Expected cron containing '0 3 *', got: {cron}"

    # Manual trigger
    assert "workflow_dispatch" in on_block, "Missing on.workflow_dispatch trigger"


def test_job_config(wf):
    """Verify job-level configuration."""
    jobs = wf.get("jobs", {})
    assert "nightly" in jobs, "Missing 'nightly' job in jobs"
    job = jobs["nightly"]

    assert job.get("runs-on") == "ubuntu-latest", \
        f"Expected runs-on 'ubuntu-latest', got: {job.get('runs-on')}"
    assert job.get("timeout-minutes") == 120, \
        f"Expected timeout-minutes 120, got: {job.get('timeout-minutes')}"


def test_steps(wf):
    """Verify all required workflow steps are present."""
    job = wf["jobs"]["nightly"]
    steps = job.get("steps", [])
    assert isinstance(steps, list) and len(steps) > 0, "No steps defined"

    # Collect all step `run` strings and `uses` strings for inspection
    run_texts = []
    uses_entries = []
    step_names = []

    for step in steps:
        name = step.get("name", "")
        run = step.get("run", "")
        uses = step.get("uses", "")
        step_names.append(name)
        if run:
            run_texts.append(run)
        if uses:
            uses_entries.append(uses)

    # Checkout step
    assert "actions/checkout@v4" in uses_entries, \
        "Missing actions/checkout@v4 step"

    # apt install flatpak / flatpak-builder
    apt_found = any(
        "apt-get install" in run and "flatpak" in run
        for run in run_texts
    )
    assert apt_found, "Missing apt-get install step for flatpak"

    # Flathub runtime install (GNOME Platform/SDK)
    flathub_found = any(
        "flatpak install" in run
        and "org.gnome.Platform" in run
        and "org.gnome.Sdk" in run
        for run in run_texts
    )
    assert flathub_found, "Missing flatpak install step for GNOME Platform/SDK"

    # Cache restore
    assert "actions/cache/restore@v4" in uses_entries, \
        "Missing actions/cache/restore@v4 step"

    # flatpak-builder --force-clean
    builder_found = any(
        "flatpak-builder" in run and "--force-clean" in run
        for run in run_texts
    )
    assert builder_found, "Missing flatpak-builder --force-clean step"

    # Verify build step
    verify_found = any(
        "verify" in name.lower() for name in step_names
    )
    assert verify_found, "Missing verify build step"

    # flatpak build-bundle
    bundle_found = any(
        "flatpak build-bundle" in run for run in run_texts
    )
    assert bundle_found, "Missing flatpak build-bundle step"

    # Cache save
    assert "actions/cache/save@v4" in uses_entries, \
        "Missing actions/cache/save@v4 step"

    # Upload artifact
    upload_uses = any("actions/upload-artifact@v4" in uses for uses in uses_entries)
    assert upload_uses, "Missing actions/upload-artifact@v4 step"

    # Upload artifact retention-days: 90
    upload_step = None
    for step in steps:
        if "actions/upload-artifact@" in step.get("uses", ""):
            upload_step = step
            break
    assert upload_step is not None, "Could not locate upload-artifact step for retention check"
    assert upload_step.get("with", {}).get("retention-days") == 90, \
        f"Expected retention-days 90, got: {upload_step.get('with', {}).get('retention-days')}"

    return len(steps)


def main():
    print(f"Validating workflow: {WORKFLOW_PATH}")

    wf = load_workflow()
    failures = []
    step_count = 0

    tests = {
        "triggers (cron + workflow_dispatch)": test_triggers,
        "job config (runs-on, timeout)": test_job_config,
        "steps (flatpak-builder, build-bundle, upload, etc.)": test_steps,
    }

    for label, test_fn in tests.items():
        try:
            if test_fn is test_steps:
                step_count = test_fn(wf)
            else:
                test_fn(wf)
            print(f"  PASS: {label}")
        except AssertionError as e:
            print(f"  FAIL: {label} — {e}")
            failures.append((label, str(e)))

    print(f"\nStep count: {step_count}")
    print(f"Tests passed: {len(tests) - len(failures)} / {len(tests)}")

    if failures:
        print(f"\n{len(failures)} failure(s):")
        for label, msg in failures:
            print(f"  - {label}: {msg}")
        sys.exit(1)

    print("\nAll assertions passed!")
    sys.exit(0)


if __name__ == "__main__":
    main()
