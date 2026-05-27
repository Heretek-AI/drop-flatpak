# drop-flatpak

Flatpak packaging for [Drop Desktop Client](https://github.com/Drop-OSS/drop-app) — a Tauri + Nuxt game launcher/management platform.

[![Nightly Flatpak Build](https://github.com/Heretek-AI/drop-flatpak/actions/workflows/nightly.yml/badge.svg)](https://github.com/Heretek-AI/drop-flatpak/actions/workflows/nightly.yml)

## What's here

A Flatpak manifest (`org.droposs.client.yml`) targeting GNOME 48 that builds `drop-app` from source with all dependencies vendored for fully offline builds. The manifest splits the build into three modules (bootstrap, Nuxt, Rust) so flatpak-builder resumes from the last successful module on failure instead of restarting from scratch.

## Quickstart

### Build locally

```bash
# Install runtimes and SDK
flatpak install --user flathub \
  org.gnome.Platform//48 \
  org.gnome.Sdk//48 \
  org.freedesktop.Sdk.Extension.node22//24.08

# Build
flatpak-builder --force-clean --user --install-deps-from=flathub build-dir org.droposs.client.yml

# Run
flatpak-builder --run build-dir org.droposs.client.yml drop-app
```

### Install from CI nightly

```bash
flatpak install --user drop-app.flatpak
flatpak run org.droposs.client
```

Download the latest `drop-app-nightly.zip` artifact from the [nightly CI](https://github.com/Heretek-AI/drop-flatpak/actions/workflows/nightly.yml), unzip to get `drop-app.flatpak`, then install.

## CI

Nightly GitHub Actions build at 03:00 UTC. Verifies:

1. flatpak-builder succeeds
2. Binary installed to `/app/bin/drop-app`
3. Runtime is `org.gnome.Platform`
4. Smoke test (`drop-app --help`)
5. AppStream metadata validation
6. Desktop file validation
7. Sandbox permission audit

A `.flatpak` bundle is uploaded as the build artifact.

## Known notes

- **No system tray**: The `tray-icon` Tauri feature is disabled at build time because the GNOME 48 runtime doesn't ship `libayatana-appindicator3`. The manifest strips this feature before `cargo build` to prevent a runtime panic. System tray support can be restored by adding a Flatpak module to build `libayatana-appindicator3` from source.

- **GNOME 48 is EOL** (since 2026-03-24). Migration to GNOME 49+ is needed before Flathub submission. The build currently targets runtime 48.

- **Rust nightly toolchain** — downloaded at build time from `static.rust-lang.org`. SHA256s are pinned in the manifest.

- **Vendored dependencies** — all Rust crates and npm packages are vendored as Flatpak sources for offline-capable builds, as required by Flathub.

## Structure

```
├── org.droposs.client.yml       # Flatpak manifest (3 modules)
├── org.droposs.client.desktop   # Desktop entry file
├── org.droposs.client.metainfo.xml  # AppStream metadata
├── scripts/
│   └── verify-s01-build.sh      # 7-check build verification
├── tests/
│   └── validate-nightly-*.py    # Workflow validation tests
├── drop-app/                    # Upstream submodule (drop-app)
└── .github/workflows/
    └── nightly.yml              # Nightly CI pipeline
```
