#!/usr/bin/env python3
"""
Generate a three-module Flatpak manifest from the monolithic org.droposs.client.yml.

Produces modules:
  drop-app-bootstrap — Rust toolchains + pnpm extraction, installs to /app
  drop-app-nuxt      — pnpm store population + Nuxt build
  drop-app-rust       — cargo config + cargo build + install

Preserves all SHA256 checksums and source metadata unchanged.
"""

import sys
import copy
from pathlib import Path

import yaml


MANIFEST_PATH = "org.droposs.client.yml.bak"
OUTPUT_PATH = "org.droposs.client.yml"


def _source_dest_prefix(source: dict) -> str:
    """Return the first path component of a source's dest, or empty string."""
    dest = source.get("dest", "")
    if dest and "/" in str(dest):
        return str(dest).split("/")[0]
    return str(dest) if dest else ""


def classify_source(source: dict) -> str:
    """
    Classify a source entry.
    Returns: 'bootstrap', 'nuxt', 'rust', or 'all' (git clone needed by every module).
    """
    t = source.get("type", "")
    dest = source.get("dest", "")
    dest_prefix = _source_dest_prefix(source)

    # --- git sources ---
    if t == "git":
        url = source.get("url", "")
        if "drop-app" in url:
            return "all"  # main repo — every module needs the source tree
        # droplet-rs, native_model → Rust-only cargo git deps
        return "rust"

    # --- shell sources (ad-hoc commands) ---
    if t == "shell":
        commands = source.get("commands", [])
        if commands:
            cmd0 = commands[0]
            if "submodule" in cmd0:
                return "bootstrap"
            if "flatpak-cargo" in cmd0:
                return "rust"
            if "flatpak-node-main" in cmd0:
                return "nuxt"
            if "flatpak-node" in cmd0 and "populate" in cmd0:
                return "nuxt"
            if "esbuild" in cmd0 or "esbuild" in source.get("dest", ""):
                return "nuxt"
        # Fallback: check dest
        if "flatpak-node-main" in dest:
            return "nuxt"
        if "flatpak-node" in dest:
            return "nuxt"
        # Unknown shell — default to bootstrap (conservative)
        return "bootstrap"

    # --- script sources (inline scripts written to dest-filename) ---
    if t == "script":
        # Both scripts are setup_sdk_node_headers.sh for Node headers
        return "nuxt"

    # --- file type checks (before dest-prefix, because pnpm tarball goes to flatpak-node/) ---
    if t == "file":
        if "pnpm" in dest and "pnpm-vendor" in dest:
            return "bootstrap"  # pnpm binary tarball in flatpak-node/pnpm-vendor

    # --- classify by dest prefix ---
    if dest_prefix in ("rust-nightly",):
        return "bootstrap"
    if dest_prefix in ("flatpak-node", "flatpak-node-main"):
        return "nuxt"
    if dest_prefix in ("cargo", "flatpak-cargo"):
        return "rust"

    # --- inline sources follow their paired archive ---
    # (inline .cargo-checksum.json files have dest=cargo/vendor/*)
    if t == "inline":
        if "cargo" in dest_prefix:
            return "rust"

    # Conservative fallback
    print(f"⚠️  Unclassified source (type={t}, dest={dest}), defaulting to bootstrap",
          file=sys.stderr)
    return "bootstrap"


def classify_build_command(cmd: str) -> str:
    """Map a single build-command string to its module."""
    c = cmd.strip()

    # Bootstrap: directory creation, Rust toolchain copying, pnpm extraction
    if any(kw in c for kw in [
        "mkdir -p /run/build/drop-app/",
        "cp -r rust-nightly/rustc/",
        "cp -r rust-nightly/cargo/",
        "cp -r rust-nightly/rust-std/",
        "tar xzf flatpak-node/pnpm-vendor/",
    ]):
        return "bootstrap"

    # Nuxt: npmrc, pnpm store, pnpm install, Nuxt build
    if any(kw in c for kw in [
        ".npmrc",
        "pnpm-manifest.json",
        "populate_pnpm_store",
        "pnpm-workspace",
        "pnpm install",
        "store-dir",
        "setup_sdk_node_headers",
        "build.mjs",
        "sed -i",
    ]):
        return "nuxt"

    # Rust: cargo config, cargo build, install
    if any(kw in c for kw in [
        ".cargo",
        "source.crates",
        "replace-with",
        "vendored-sources",
        "cargo build",
        "install -D",
        "for size in",
        "src-tauri/",
    ]):
        return "rust"

    print(f"⚠️  Unclassified build command, defaulting to bootstrap: {c[:100]}",
          file=sys.stderr)
    return "bootstrap"


def adapt_bootstrap_commands() -> list:
    """Return the bootstrap module build commands — adapted to install into /app."""
    return [
        "mkdir -p /app/lib/rust-nightly/{bin,lib} /app/bin",
        "cp -r rust-nightly/rustc/rustc/bin/* /app/lib/rust-nightly/bin/",
        "cp -r rust-nightly/rustc/rustc/lib/* /app/lib/rust-nightly/lib/",
        "cp -r rust-nightly/cargo/cargo/bin/* /app/lib/rust-nightly/bin/",
        "cp -r rust-nightly/cargo/cargo/share /app/lib/rust-nightly/share/",
        "cp -r rust-nightly/rust-std/rust-std-x86_64-unknown-linux-gnu/lib/rustlib/. "
        "/app/lib/rust-nightly/lib/rustlib/",
        "tar xzf flatpak-node/pnpm-vendor/pnpm-linux-x64.tar.gz -C /app/bin/ "
        "&& chmod +x /app/bin/pnpm",
        # Verification guards
        "LD_LIBRARY_PATH=/app/lib/rust-nightly/lib /app/lib/rust-nightly/bin/rustc --version",
        "/app/bin/pnpm --version",
    ]


def adapt_nuxt_commands(original_cmds: list) -> list:
    """Adapt Nuxt build commands to use /app/bin/pnpm instead of $PNPM_HOME."""
    import re
    adapted = []
    for cmd in original_cmds:
        c = cmd
        # Replace $PNPM_HOME/bin/pnpm → /app/bin/pnpm
        c = c.replace("$PNPM_HOME/bin/pnpm", "/app/bin/pnpm")
        # Strip PATH assignments (pnpm is now on PATH via append-path).
        # Order matters: most specific patterns first.
        # A: `export CI=true PATH="..." && ` → ""  (CI=true is in build-options env)
        c = re.sub(r'export\s+CI=true\s+PATH="[^"]*"\s*&&\s*', "", c)
        # B: `export PATH="$PNPM_HOME/bin:$PATH" && ` → ""
        c = re.sub(r'export\s+PATH="\$PNPM_HOME/bin:\$PATH"\s*&&\s*', "", c)
        # C: bare `PATH="$PNPM_HOME/bin:$PATH" && ` → ""
        c = re.sub(r'PATH="\$PNPM_HOME/bin:\$PATH"\s*&&\s*', "", c)
        adapted.append(c)
    return adapted


def adapt_rust_commands(original_cmds: list) -> list:
    """Adapt Rust build commands — fix mkdir to use module-local path, keep rest as-is."""
    adapted = []
    for cmd in original_cmds:
        c = cmd
        # Fix the mkdir command: use module-specific cargo-home
        c = c.replace(
            "mkdir -p /run/build/drop-app/cargo-home",
            "mkdir -p /run/build/drop-app-rust/cargo-home",
        )
        adapted.append(c)
    return adapted


def main():
    # --- Load ---
    with open(MANIFEST_PATH, "r") as f:
        manifest = yaml.safe_load(f)

    original_module = manifest["modules"][0]
    all_sources = original_module.get("sources", [])
    all_commands = original_module.get("build-commands", [])

    # --- Classify sources ---
    bootstrap_sources: list = []
    nuxt_sources: list = []
    rust_sources: list = []

    for src in all_sources:
        classification = classify_source(src)
        if classification == "all":
            bootstrap_sources.append(copy.deepcopy(src))
            nuxt_sources.append(copy.deepcopy(src))
            rust_sources.append(copy.deepcopy(src))
        elif classification == "bootstrap":
            bootstrap_sources.append(copy.deepcopy(src))
        elif classification == "nuxt":
            nuxt_sources.append(copy.deepcopy(src))
        elif classification == "rust":
            rust_sources.append(copy.deepcopy(src))

    # --- Classify and adapt build commands ---
    raw_bootstrap_cmds = []
    raw_nuxt_cmds = []
    raw_rust_cmds = []

    for cmd in all_commands:
        classification = classify_build_command(cmd)
        if classification == "bootstrap":
            raw_bootstrap_cmds.append(cmd)
        elif classification == "nuxt":
            raw_nuxt_cmds.append(cmd)
        elif classification == "rust":
            raw_rust_cmds.append(cmd)

    # Use the carefully-adapted bootstrap commands
    bootstrap_cmds = adapt_bootstrap_commands()
    nuxt_cmds = adapt_nuxt_commands(raw_nuxt_cmds)
    rust_cmds = adapt_rust_commands(raw_rust_cmds)

    # --- Assemble new modules ---
    new_modules = [
        {
            "name": "drop-app-bootstrap",
            "buildsystem": "simple",
            "build-options": {
                "append-path": "/usr/lib/sdk/node22/bin",
                "env": {
                    "LD_LIBRARY_PATH": "/app/lib/rust-nightly/lib",
                },
            },
            "sources": bootstrap_sources,
            "build-commands": bootstrap_cmds,
        },
        {
            "name": "drop-app-nuxt",
            "buildsystem": "simple",
            "build-options": {
                "append-path": "/usr/lib/sdk/node22/bin:/app/bin",
                "env": {
                    "CI": "true",
                },
            },
            "sources": nuxt_sources,
            "build-commands": nuxt_cmds,
        },
        {
            "name": "drop-app-rust",
            "buildsystem": "simple",
            "build-options": {
                "append-path": "/app/lib/rust-nightly/bin:/app/bin",
                "env": {
                    "CARGO_HOME": "/run/build/drop-app-rust/cargo-home",
                    "RUSTFLAGS": "-C link-arg=-Wl,-z,relro,-z,now",
                    "LD_LIBRARY_PATH": "/app/lib/rust-nightly/lib",
                },
            },
            "sources": rust_sources,
            "build-commands": rust_cmds,
        },
    ]

    # --- Preserve top-level keys, replace modules ---
    new_manifest = {}
    for k, v in manifest.items():
        if k == "modules":
            new_manifest[k] = new_modules
        elif k == "sdk-extensions":
            new_manifest[k] = copy.deepcopy(v)
        else:
            new_manifest[k] = copy.deepcopy(v)

    # --- Write ---
    with open(OUTPUT_PATH, "w") as f:
        yaml.dump(
            new_manifest,
            f,
            default_flow_style=False,
            sort_keys=False,
            width=140,
            allow_unicode=True,
        )

    # --- Summary ---
    print(f"✅ Wrote {OUTPUT_PATH}")
    print(f"   Modules: {len(new_modules)}")
    print(f"   drop-app-bootstrap: {len(bootstrap_sources)} sources, {len(bootstrap_cmds)} commands")
    print(f"   drop-app-nuxt:      {len(nuxt_sources)} sources, {len(nuxt_cmds)} commands")
    print(f"   drop-app-rust:      {len(rust_sources)} sources, {len(rust_cmds)} commands")
    total_sources = len(bootstrap_sources) + len(nuxt_sources) + len(rust_sources)
    total_cmds = len(bootstrap_cmds) + len(nuxt_cmds) + len(rust_cmds)
    print(f"   Total sources (incl. shared git clones): {total_sources}")
    print(f"   Total commands: {total_cmds}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
