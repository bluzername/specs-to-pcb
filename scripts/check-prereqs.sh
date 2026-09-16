#!/bin/bash
# Check all prerequisites for the specs-to-pcb skill.
#
# Usage: check-prereqs.sh [-h|--help] [--report-only]
#   --report-only  print the same report but always exit 0 (for CI)
#
# Environment overrides (same names as example/scripts/autoroute.sh):
#   KICAD_CLI     kicad-cli binary
#   KICAD_PYTHON  KiCad bundled python3 (for pcbnew)
#   JAVA          java binary (for FreeRouting)

set -euo pipefail

KICAD_APP="/Applications/KiCad/KiCad.app"
KICAD_PY_VERSIONS="$KICAD_APP/Contents/Frameworks/Python.framework/Versions"
REPORT_ONLY=0
OK=0
WARN=0
FAIL=0

usage() {
    sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
}

for arg in "$@"; do
    case "$arg" in
        --report-only) REPORT_ONLY=1 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

pass() {
    echo "  [OK] $1"
    OK=$((OK + 1))
}

fail() {
    echo "  [!!] $1 - install with: $2"
    FAIL=$((FAIL + 1))
}

warn() {
    echo "  [--] $1 - $2"
    WARN=$((WARN + 1))
}

# require NAME INSTALL_HINT CMD [ARGS...]: required item, counts as failure
require() {
    local name="$1" install="$2"
    shift 2
    if "$@" >/dev/null 2>&1; then
        pass "$name"
    else
        fail "$name" "$install"
    fi
}

# optional NAME NOTE CMD [ARGS...]: optional item, counts as warning
optional() {
    local name="$1" note="$2"
    shift 2
    if "$@" >/dev/null 2>&1; then
        pass "$name"
    else
        warn "$name" "$note"
    fi
}

# Prints the first java that actually runs. macOS ships a /usr/bin/java stub
# that exists but fails with "Unable to locate a Java Runtime".
find_java() {
    local candidate
    for candidate in "${JAVA:-}" \
                     "$(command -v java || true)" \
                     /opt/homebrew/opt/openjdk@21/bin/java \
                     /opt/homebrew/opt/openjdk@17/bin/java \
                     /opt/homebrew/opt/openjdk/bin/java; do
        [ -n "$candidate" ] && [ -x "$candidate" ] || continue
        if "$candidate" -version >/dev/null 2>&1; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

find_kicad_python() {
    local candidate
    for candidate in "${KICAD_PYTHON:-}" \
                     "$KICAD_PY_VERSIONS"/[0-9]*/bin/python3 \
                     "$KICAD_PY_VERSIONS"/Current/bin/python3; do
        if [ -n "$candidate" ] && [ -x "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

find_kicad_cli() {
    if [ -n "${KICAD_CLI:-}" ]; then
        printf '%s\n' "$KICAD_CLI"
        return 0
    fi
    if command -v kicad-cli >/dev/null 2>&1; then
        command -v kicad-cli
        return 0
    fi
    if [ -x "$KICAD_APP/Contents/MacOS/kicad-cli" ]; then
        printf '%s\n' "$KICAD_APP/Contents/MacOS/kicad-cli"
        return 0
    fi
    return 1
}

echo "=== specs-to-pcb Prerequisites ==="
echo ""

require "Python 3.10+" "Install Python 3.10+" \
    python3 -c 'import sys; assert sys.version_info >= (3, 10)'

if KICAD_CLI_BIN="$(find_kicad_cli)"; then
    require "KiCad CLI ($KICAD_CLI_BIN)" "brew install --cask kicad" "$KICAD_CLI_BIN" version
else
    fail "KiCad CLI" "brew install --cask kicad (or set KICAD_CLI)"
fi

require "kiutils" "pip3 install -r requirements.txt" python3 -c 'import kiutils'
require "kicad-sch-api" "pip3 install -r requirements.txt" python3 -c 'import kicad_sch_api'

if JAVA_BIN="$(find_java)"; then
    pass "Java ($JAVA_BIN)"
else
    warn "Java" "brew install openjdk@21 (needed for FreeRouting autorouter; or set JAVA)"
fi

optional "rsvg-convert" "brew install librsvg (needed for PNG review images)" \
    command -v rsvg-convert

if KICAD_PY_BIN="$(find_kicad_python)"; then
    optional "pcbnew (KiCad Python: $KICAD_PY_BIN)" \
        "Comes with KiCad - needed for headless DSN export" \
        "$KICAD_PY_BIN" -c 'import pcbnew'
else
    warn "pcbnew (KiCad Python)" "Comes with KiCad - needed for headless DSN export (or set KICAD_PYTHON)"
fi

echo ""
echo "Results: $OK ok, $WARN optional missing, $FAIL required missing"

if [ "$REPORT_ONLY" -eq 1 ]; then
    exit 0
fi
if [ "$FAIL" -gt 0 ]; then
    echo "Fix required items before running the skill."
    exit 1
fi
echo "Ready to generate PCBs!"
