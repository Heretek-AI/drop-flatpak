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

# Step 1: Build the Flatpak
echo "--- Step 1: flatpak-builder ---"
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
    echo "FAILED: Build did not succeed. Check logs above."
    exit 1
fi

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

# Summary
echo ""
echo "============================================"
echo "Results: $PASS_COUNT/$TOTAL passed, $FAIL_COUNT/$TOTAL failed"
echo "============================================"

if [ "$FAIL_COUNT" -gt 0 ]; then
    exit 1
fi
exit 0
