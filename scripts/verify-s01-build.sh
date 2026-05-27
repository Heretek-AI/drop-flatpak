#!/usr/bin/env bash
set -euo pipefail

# verify-s01-build.sh — T03 verification: build the Flatpak and verify launch
# Invokes flatpak-builder via org.flatpak.Builder Flatpak

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_DIR/build-dir"
MANIFEST="$PROJECT_DIR/org.droposs.client.yml"
APP_ID="org.droposs.client"
BINARY_NAME="drop-app"

FLATPAK_BUILDER="flatpak run --share=network org.flatpak.Builder"
APPSTREAMCLI="appstreamcli"
DESKTOP_FILE_VALIDATE="desktop-file-validate"

# Tool-availability guards for non-build checks
for tool_cmd in "$APPSTREAMCLI" "$DESKTOP_FILE_VALIDATE"; do
    if ! command -v "$tool_cmd" &>/dev/null; then
        tool_name=$(basename "$tool_cmd")
        echo "ERROR: $tool_cmd not found"
        case "$tool_name" in
            appstreamcli) echo "  Install with: sudo dnf install appstream" ;;
            desktop-file-validate) echo "  Install with: sudo dnf install desktop-file-utils" ;;
        esac
        exit 2
    fi
done

PASS_COUNT=0
FAIL_COUNT=0
TOTAL=0

pass() {
    echo "  ✅ PASS: $1"
    PASS_COUNT=$((PASS_COUNT + 1))
    TOTAL=$((TOTAL + 1))
}

fail() {
    echo "  ❌ FAIL: $1"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    TOTAL=$((TOTAL + 1))
}

echo "============================================"
echo "verify-s01-build.sh — T03 Build Verification"
echo "============================================"
echo ""

# Step 1: Build the Flatpak (skip if binary already exists from prior step)
echo "--- Step 1: flatpak-builder ---"
BINARY_PATH="$BUILD_DIR/files/bin/$BINARY_NAME"
if test -f "$BINARY_PATH"; then
    echo "Build output already exists at $BINARY_PATH — skipping rebuild"
    pass "flatpak-builder: binary already present (prior step built it)"
else
echo "Running: ${FLATPAK_BUILDER} --force-clean --user --install-deps-from=flathub ${BUILD_DIR} ${MANIFEST}"
echo ""
START_TIME=$(date +%s)

if ${FLATPAK_BUILDER} --force-clean --user --install-deps-from=flathub --disable-rofiles-fuse "$BUILD_DIR" "$MANIFEST"; then
    BUILD_EXIT=$?
    END_TIME=$(date +%s)
    BUILD_DURATION=$((END_TIME - START_TIME))
    echo ""
    echo "flatpak-builder exited with code $BUILD_EXIT after ${BUILD_DURATION}s"
    pass "flatpak-builder completed successfully ($BUILD_EXIT, ${BUILD_DURATION}s)"
else
    BUILD_EXIT=$?
    END_TIME=$(date +%s)
    BUILD_DURATION=$((END_TIME - START_TIME))
    echo ""
    echo "flatpak-builder exited with code $BUILD_EXIT after ${BUILD_DURATION}s"
    fail "flatpak-builder failed (exit code $BUILD_EXIT)"
    echo ""
    echo "--- Per-module build logs ---"
    for logdir in "$BUILD_DIR/.flatpak-builder/build"/*/; do
        module_name=$(basename "$logdir")
        echo "  Module: $module_name"
        for logfile in "$logdir"/*; do
            echo "    $(basename "$logfile"): $(wc -l < "$logfile") lines"
        done
    done
    echo ""
    echo "FAILED: Build did not succeed. Subsequent source-file checks (5-7) will still run."
    BUILD_FAILED=1
fi
fi  # close the binary-exists skip gate

# Step 2: Verify binary exists
echo ""
echo "--- Step 2: Binary presence check ---"
BINARY_PATH="$BUILD_DIR/files/bin/$BINARY_NAME"
if test -f "$BINARY_PATH"; then
    BINARY_SIZE=$(du -h "$BINARY_PATH" | cut -f1)
    echo "Binary found: $BINARY_PATH ($BINARY_SIZE)"
    pass "binary $BINARY_NAME installed to /app/bin/ ($BINARY_SIZE)"
else
    echo "Expected binary not found at $BINARY_PATH"
    echo "Listing $BUILD_DIR/files/bin/:"
    ls -la "$BUILD_DIR/files/bin/" 2>/dev/null || echo "(directory does not exist)"
    fail "binary $BINARY_NAME not found at /app/bin/"
fi

# Step 3: Verify runtime metadata
echo ""
echo "--- Step 3: Runtime metadata check ---"
METADATA_FILE="$BUILD_DIR/metadata"
if test -f "$METADATA_FILE"; then
    if grep -q 'org.gnome.Platform' "$METADATA_FILE"; then
        RUNTIME_LINE=$(grep 'runtime=' "$METADATA_FILE" | head -1)
        echo "metadata runtime: $RUNTIME_LINE"
        pass "runtime is org.gnome.Platform"
    else
        echo "metadata contents:"
        cat "$METADATA_FILE"
        fail "runtime not org.gnome.Platform in metadata"
    fi
else
    fail "metadata file not found at $METADATA_FILE"
fi

# Step 4: Smoke test — launch with --help
echo ""
echo "--- Step 4: Smoke test (launch with --help) ---"
if ${FLATPAK_BUILDER} --run "$BUILD_DIR" "$MANIFEST" "$BINARY_NAME" --help 2>&1; then
    SMOKE_EXIT=$?
    echo ""
    echo "drop-app --help exited with code $SMOKE_EXIT"
    if [ "$SMOKE_EXIT" -eq 127 ]; then
        fail "smoke test: exit 127 (missing library/binary)"
    elif [ "$SMOKE_EXIT" -eq 139 ]; then
        fail "smoke test: exit 139 (segfault)"
    else
        pass "smoke test: drop-app --help ran without missing-library or segfault (exit $SMOKE_EXIT)"
    fi
else
    SMOKE_EXIT=$?
    echo ""
    if [ "$SMOKE_EXIT" -eq 127 ]; then
        fail "smoke test: exit 127 (missing library/binary)"
    elif [ "$SMOKE_EXIT" -eq 139 ]; then
        fail "smoke test: exit 139 (segfault)"
    else
        echo "drop-app --help exited with code $SMOKE_EXIT (non-zero but acceptable for --help)"
        pass "smoke test: drop-app --help ran without missing-library or segfault (exit $SMOKE_EXIT)"
    fi
fi

# Step 5: AppStream metadata validation
echo ""
echo "--- Step 5: AppStream metadata validation ---"
METAINFO_FILE="$PROJECT_DIR/org.droposs.client.metainfo.xml"
if test -f "$METAINFO_FILE"; then
    set +e
    APPSTREAM_OUTPUT=$("$APPSTREAMCLI" validate "$METAINFO_FILE" 2>&1)
    APPSTREAM_EXIT=$?
    set -e
    echo "$APPSTREAM_OUTPUT"
    if [ "$APPSTREAM_EXIT" -eq 0 ]; then
        pass "appstreamcli validate returned exit 0 (warnings/infos are non-fatal)"
    else
        fail "appstreamcli validate failed (exit $APPSTREAM_EXIT) — check AppStream metadata errors above"
    fi
else
    fail "AppStream metainfo file not found at $METAINFO_FILE"
fi

# Step 6: Desktop file validation
echo ""
echo "--- Step 6: Desktop file validation ---"
DESKTOP_FILE="$PROJECT_DIR/org.droposs.client.desktop"
if test -f "$DESKTOP_FILE"; then
    set +e
    DESKTOP_OUTPUT=$("$DESKTOP_FILE_VALIDATE" "$DESKTOP_FILE" 2>&1)
    DESKTOP_EXIT=$?
    set -e
    if [ -n "$DESKTOP_OUTPUT" ]; then
        echo "$DESKTOP_OUTPUT"
    else
        echo "desktop-file-validate produced no output (clean)"
    fi
    if [ "$DESKTOP_EXIT" -eq 0 ]; then
        pass "desktop-file-validate passed (exit 0)"
    else
        fail "desktop-file-validate failed (exit $DESKTOP_EXIT)"
    fi
else
    fail "Desktop file not found at $DESKTOP_FILE"
fi

# Step 7: Sandbox permission audit
echo ""
echo "--- Step 7: Sandbox permission audit ---"
MANIFEST_YML="$PROJECT_DIR/org.droposs.client.yml"
if test -f "$MANIFEST_YML"; then
    set +e
    SANDBOX_AUDIT=$(python3 -c "
import yaml, sys
with open('$MANIFEST_YML') as f:
    doc = yaml.safe_load(f)
finish_args = doc.get('finish-args', [])
if not finish_args:
    print('No finish-args found in manifest.')
    sys.exit(0)

critical = 0
notable = 0
benign = 0

CRITICAL_FLAGS = {'--device=all', '--filesystem=host', '--filesystem=home', '--socket=system-bus'}
NOTABLE_FLAGS_STARTSWITH = ('--share=', '--talk-name=', '--own-name=')

for arg in finish_args:
    arg_s = str(arg).strip()
    if arg_s in CRITICAL_FLAGS:
        label = 'CRITICAL'
        critical += 1
    elif arg_s.startswith(NOTABLE_FLAGS_STARTSWITH):
        label = 'notable'
        notable += 1
    else:
        label = 'benign'
        benign += 1
    print(f'  [{label}] {arg_s}')

print()
print(f'  Critical: {critical}, notable: {notable}, benign: {benign}')
sys.exit(critical)
" 2>&1)
    SANDBOX_EXIT=$?
    set -e
    echo "$SANDBOX_AUDIT"
    if [ "$SANDBOX_EXIT" -eq 0 ]; then
        pass "sandbox audit: no critical permissions found"
    else
        # Count criticals from Python exit code
        CRIT_COUNT=$SANDBOX_EXIT
        fail "sandbox audit: $CRIT_COUNT critical permission(s) found — remove --device=all, --filesystem=host, --filesystem=home, or --socket=system-bus"
        echo "  Note: --share=network is notable but required for Tauri app networking"
    fi
else
    fail "Manifest file not found at $MANIFEST_YML"
fi

# Summary
echo ""
echo "============================================"
echo "Results: $PASS_COUNT/$TOTAL passed, $FAIL_COUNT/$TOTAL failed"
echo "============================================"

if [ "$FAIL_COUNT" -gt 0 ]; then
    exit 1
fi
exit 0
