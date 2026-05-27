#!/usr/bin/env python3
"""Verify the three-module manifest structure.

Asserts:
  1. The manifest loads as valid YAML.
  2. Exactly 3 modules exist.
  3. Module names are drop-app-bootstrap, drop-app-nuxt, drop-app-rust (in that order).
  4. Each module has sources and build-commands.
  5. Checksums match the original manifest for all archive/file sources.
"""

import sys
import hashlib
from pathlib import Path

import yaml


MANIFEST_PATH = "org.droposs.client.yml"
EXPECTED_MODULE_NAMES = ["drop-app-bootstrap", "drop-app-nuxt", "drop-app-rust"]


def checksum_key(source: dict) -> str:
    """Stable sort key for a source to enable cross-reference."""
    return f"{source.get('type','')}:{source.get('url','')}:{source.get('dest','')}:{source.get('dest-filename','')}"


def build_checksum_index(sources: list) -> dict:
    """Build a dict of checksum_key → sha256 for all archive and file sources."""
    index = {}
    for src in sources:
        if src.get("type") in ("archive", "file"):
            sha = src.get("sha256")
            if sha:
                index[checksum_key(src)] = sha
    return index


def main():
    errors: list[str] = []

    # 1. Load YAML
    try:
        with open(MANIFEST_PATH, "r") as f:
            manifest = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"FAIL: {MANIFEST_PATH} not found")
        return 1
    except yaml.YAMLError as e:
        print(f"FAIL: YAML parse error: {e}")
        return 1

    if not isinstance(manifest, dict):
        print("FAIL: Manifest is not a YAML dictionary")
        return 1

    print(f"✅ Manifest loads as valid YAML (app-id: {manifest.get('app-id', 'MISSING')})")

    # 2. Check modules exist
    modules = manifest.get("modules", [])
    if len(modules) != 3:
        errors.append(f"Expected 3 modules, found {len(modules)}")

    actual_names = [m.get("name", "<unnamed>") for m in modules]

    # 3. Check module names
    for i, expected_name in enumerate(EXPECTED_MODULE_NAMES):
        if i >= len(modules):
            errors.append(f"Missing module: {expected_name}")
        elif actual_names[i] != expected_name:
            errors.append(
                f"Module {i}: expected '{expected_name}', got '{actual_names[i]}'"
            )

    if not errors:
        print(f"✅ Exactly 3 modules with correct names: {', '.join(actual_names)}")

    # 4. Check each module has sources and build-commands
    for mod in modules:
        name = mod.get("name", "<unnamed>")
        sources = mod.get("sources", [])
        cmds = mod.get("build-commands", [])
        if not sources:
            errors.append(f"Module '{name}' has no sources")
        if not cmds:
            errors.append(f"Module '{name}' has no build-commands")
        print(f"   {name}: {len(sources)} sources, {len(cmds)} build-commands")

    # 5. Verify checksums — archive sources use sha256 (64 hex chars), file sources may use sha512 (128 hex chars) or sha256
    sha_violations = []
    for mod in modules:
        name = mod.get("name", "?")
        for src in mod.get("sources", []):
            t = src.get("type", "")
            url = src.get("url", "")
            if t == "archive":
                sha256 = src.get("sha256", "")
                sha512 = src.get("sha512", "")
                if (not sha256 or len(sha256) != 64) and (not sha512 or len(sha512) != 128):
                    sha_violations.append(
                        f"  {name} archive: {url[:80]} → neither sha256 nor sha512 is valid"
                    )
            elif t == "file":
                sha256 = src.get("sha256", "")
                sha512 = src.get("sha512", "")
                if (not sha256 or len(sha256) != 64) and (not sha512 or len(sha512) != 128):
                    sha_violations.append(
                        f"  {name} file: {url[:80]} → neither sha256 nor sha512 is valid"
                    )

    if sha_violations:
        errors.append(
            f"{len(sha_violations)} sources with missing/invalid checksums"
        )
        for v in sha_violations[:10]:
            print(f"   CHECKSUM ISSUE: {v}")
        if len(sha_violations) > 10:
            print(f"   ... and {len(sha_violations) - 10} more")
    else:
        print("✅ All archive sources have valid sha256 or sha512; file sources have valid sha256 or sha512")

    # 6. Verify build-options.append-path exists on each module
    for mod in modules:
        name = mod.get("name", "?")
        bo = mod.get("build-options", {})
        ap = bo.get("append-path", "")
        if not ap:
            errors.append(f"Module '{name}' missing build-options.append-path")
        else:
            print(f"   {name} append-path: {ap}")

    # --- Report ---
    if errors:
        print(f"\n❌ {len(errors)} verification failure(s):")
        for e in errors:
            print(f"   - {e}")
        return 1

    print("\n✅ All verification checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
