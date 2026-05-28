#!/usr/bin/env bash
set -eu

# verify-manifest-guards.sh — standalone check for T02 fixes
# Checks: set -eu in each module, $PWD/cargo/vendor for absolute paths,
#         no --manifest-path flag present.
# Exits 0 on all checks passing, 1 with descriptive message on failure.

MANIFEST="${1:-org.droposs.client.yml}"

if [[ ! -f "$MANIFEST" ]]; then
    echo "FAIL: manifest file '$MANIFEST' not found"
    exit 1
fi

FAILURES=0
CHECKS=0

check() {
    local desc="$1"
    local condition="$2"
    CHECKS=$((CHECKS + 1))
    if eval "$condition"; then
        echo "  PASS: $desc"
    else
        echo "  FAIL: $desc"
        FAILURES=$((FAILURES + 1))
    fi
}

echo "=== verify-manifest-guards.sh ==="
echo "Manifest: $MANIFEST"
echo ""

# Extract module blocks using awk state machine
# We need to detect module boundaries and check each one

# --- Check 1: set -eu present in each module ---
echo "--- Check: set -eu in each module ---"

# Count how many modules have 'set -eu' in their build-commands
module_count=$(python3 -c "
import yaml, sys
with open('$MANIFEST') as f:
    data = yaml.safe_load(f)
named_modules = [m for m in data['modules'] if isinstance(m, dict) and 'name' in m]
print(len(named_modules))
")
check "Manifest has 3 modules" "[ \"$module_count\" -eq 3 ]"

python3 -c "
import yaml, sys
with open('$MANIFEST') as f:
    data = yaml.safe_load(f)
for mod in data['modules']:
    if not isinstance(mod, dict):
        continue
    cmds = mod.get('build-commands', [])
    has_set_eu = any(c.strip() == 'set -eu' for c in cmds)
    print(f\"{mod['name']}: set-eu={'yes' if has_set_eu else 'NO'}\")
" | while IFS= read -r line; do
    module_name=$(echo "$line" | cut -d: -f1)
    result=$(echo "$line" | cut -d= -f2)
    if [ "$result" = "yes" ]; then
        echo "  PASS: $module_name has set -eu"
    else
        echo "  FAIL: $module_name missing set -eu"
        FAILURES=$((FAILURES + 1))
    fi
done

echo ""

# --- Check 2: $PWD/cargo/vendor used for absolute paths ---
echo "--- Check: \$PWD/cargo/vendor for absolute paths ---"

# directory line
check "cargo config directory uses \$PWD/cargo/vendor" \
    "grep -q 'directory = .*\$PWD/cargo/vendor' '$MANIFEST'"

# droplet-rs patch path
check "droplet-rs patch path uses \$PWD/cargo/vendor" \
    "grep -q 'droplet-rs.*=.*path.*\$PWD/cargo/vendor/droplet-rs' '$MANIFEST'"

# native_model patch path
check "native_model patch path uses \$PWD/cargo/vendor" \
    "grep -q 'native_model.*=.*path.*\$PWD/cargo/vendor/native_model' '$MANIFEST'"

echo ""

# --- Check 3: No --manifest-path flag ---
echo "--- Check: no --manifest-path flag ---"
check "No --manifest-path flag in manifest" \
    "! grep -q '\-\-manifest-path' '$MANIFEST'"

echo ""

# --- Check 4: cd src-tauri before cargo build ---
echo "--- Check: cd src-tauri before cargo build ---"
check "Rust module uses cd src-tauri && cargo build" \
    "grep -q 'cd src-tauri && cargo build --release' '$MANIFEST'"

echo ""

# --- Check 5: Nuxt build verification ---
echo "--- Check: Nuxt build verification ---"
check "Nuxt module verifies main/.output/public/index.html exists" \
    "grep -q 'test -f main/.output/public/index.html' '$MANIFEST'"

echo ""

# --- Check 6: Bootstrap toolchain verification ---
echo "--- Check: Bootstrap toolchain verification ---"
check "Bootstrap verifies rustc --version" \
    "grep -q 'rustc --version' '$MANIFEST'"
check "Bootstrap verifies pnpm --version" \
    "grep -q 'pnpm --version' '$MANIFEST'"

echo ""
echo "=== Results: $CHECKS checks, $FAILURES failures ==="

if [ "$FAILURES" -eq 0 ]; then
    echo "All checks passed."
    exit 0
else
    echo "Some checks failed. See above for details."
    exit 1
fi
