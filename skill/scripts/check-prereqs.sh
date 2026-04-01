#!/bin/bash
# Check all prerequisites for specs-to-pcb skill
set -euo pipefail

OK=0
WARN=0
FAIL=0

check() {
    local name="$1" cmd="$2" install="$3"
    if eval "$cmd" >/dev/null 2>&1; then
        echo "  [OK] $name"
        OK=$((OK+1))
    else
        echo "  [!!] $name - install with: $install"
        FAIL=$((FAIL+1))
    fi
}

check_warn() {
    local name="$1" cmd="$2" note="$3"
    if eval "$cmd" >/dev/null 2>&1; then
        echo "  [OK] $name"
        OK=$((OK+1))
    else
        echo "  [--] $name - $note"
        WARN=$((WARN+1))
    fi
}

echo "=== specs-to-pcb Prerequisites ==="
echo ""

check "Python 3.10+" "python3 -c 'import sys; assert sys.version_info >= (3,10)'" "Install Python 3.10+"
check "KiCad CLI" "which kicad-cli" "brew install --cask kicad"
check "kiutils" "python3 -c 'import kiutils'" "pip3 install kiutils"
check "kicad-sch-api" "python3 -c 'import kicad_sch_api'" "pip3 install kicad-sch-api"
check_warn "Java 21" "/opt/homebrew/opt/openjdk@21/bin/java -version" "brew install openjdk@21 (needed for FreeRouting autorouter)"
check_warn "rsvg-convert" "which rsvg-convert" "brew install librsvg (needed for PNG review images)"

KICAD_PY="/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9"
check_warn "pcbnew (KiCad Python)" "$KICAD_PY -c 'import pcbnew'" "Comes with KiCad - needed for DSN export/autoroute"

echo ""
echo "Results: $OK ok, $WARN optional missing, $FAIL required missing"

if [ "$FAIL" -gt 0 ]; then
    echo "Fix required items before running the skill."
    exit 1
fi
echo "Ready to generate PCBs!"
