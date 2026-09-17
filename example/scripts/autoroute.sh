#!/bin/bash
# specs-to-pcb example - automated PCB routing pipeline
#
# Regenerates the KiCad project, runs ERC, exports a Specctra DSN with
# KiCad's bundled Python (pcbnew, no GUI), routes it with FreeRouting and
# runs DRC. Importing the routed .ses back into the board is left to
# pcbnew.ImportSpecctraSES() or KiCad's File > Import > Specctra SES.
#
# Layout expected (copy this file next to the generators):
#   <project>/scripts/autoroute.sh, generate_kicad_project.py, ...
#   <project>/kicad/<PROJECT_NAME>.kicad_pro (written by the generator)
#
# Usage: ./autoroute.sh [-h|--help] [PROJECT_NAME]
#
# Environment overrides (all optional):
#   PROJECT_NAME         basename of the .kicad_pro without extension.
#                        Default: the single *.kicad_pro in ../kicad after
#                        regeneration (fails if there are zero or several).
#   FREEROUTING_VERSION  FreeRouting release to download. Default: 2.4.1.
#   FREEROUTING_JAR      path to an existing FreeRouting jar (skips download).
#   JAVA                 java binary. Default: java on PATH if it runs, then
#                        Homebrew openjdk@21, openjdk@17, openjdk.
#   KICAD_PYTHON         KiCad bundled python3. Default: globbed from
#                        /Applications/KiCad/KiCad.app (concrete version
#                        directory preferred over Current).
#   KICAD_CLI            kicad-cli binary. Default: on PATH, then the app bundle.

set -euo pipefail
shopt -s nullglob

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
KICAD_DIR="$SCRIPT_DIR/../kicad"
KICAD_APP="/Applications/KiCad/KiCad.app"
KICAD_PY_VERSIONS="$KICAD_APP/Contents/Frameworks/Python.framework/Versions"
FREEROUTING_VERSION="${FREEROUTING_VERSION:-2.4.1}"
FREEROUTING_URL="https://github.com/freerouting/freerouting/releases/download/v${FREEROUTING_VERSION}/freerouting-${FREEROUTING_VERSION}.jar"
FREEROUTING_JAR="${FREEROUTING_JAR:-$SCRIPT_DIR/freerouting-${FREEROUTING_VERSION}.jar}"

usage() {
    sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
}

die() {
    echo "ERROR: $*" >&2
    exit 1
}

case "${1:-}" in
    -h|--help) usage; exit 0 ;;
esac
PROJECT_NAME="${1:-${PROJECT_NAME:-}}"

# Explicit overrides must point at something runnable; fail early if not.
[ -z "${KICAD_CLI:-}" ] || [ -x "$KICAD_CLI" ] || die "KICAD_CLI=$KICAD_CLI is not executable"
[ -z "${KICAD_PYTHON:-}" ] || [ -x "$KICAD_PYTHON" ] || die "KICAD_PYTHON=$KICAD_PYTHON is not executable"

# Prints the first java that actually runs. macOS ships a /usr/bin/java stub
# that exists but fails with "Unable to locate a Java Runtime".
find_java() {
    local candidate
    if [ -n "${JAVA:-}" ]; then
        "$JAVA" -version >/dev/null 2>&1 || die "JAVA=$JAVA does not run"
        printf '%s\n' "$JAVA"
        return 0
    fi
    for candidate in "$(command -v java || true)" \
                     /opt/homebrew/opt/openjdk@21/bin/java \
                     /opt/homebrew/opt/openjdk@17/bin/java \
                     /opt/homebrew/opt/openjdk/bin/java; do
        if [ -z "$candidate" ] || [ ! -x "$candidate" ]; then
            continue
        fi
        if "$candidate" -version >/dev/null 2>&1; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

find_kicad_python() {
    local candidate
    if [ -n "${KICAD_PYTHON:-}" ]; then
        printf '%s\n' "$KICAD_PYTHON"
        return 0
    fi
    for candidate in "$KICAD_PY_VERSIONS"/[0-9]*/bin/python3 \
                     "$KICAD_PY_VERSIONS"/Current/bin/python3; do
        if [ -x "$candidate" ]; then
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

resolve_project_name() {
    [ -n "$PROJECT_NAME" ] && return 0
    local projects=("$KICAD_DIR"/*.kicad_pro)
    case "${#projects[@]}" in
        0) die "no .kicad_pro found in $KICAD_DIR; pass PROJECT_NAME or the name as first argument" ;;
        1) PROJECT_NAME="$(basename "${projects[0]}" .kicad_pro)" ;;
        *) die "several .kicad_pro files in $KICAD_DIR (${projects[*]##*/}); pass PROJECT_NAME or the name as first argument" ;;
    esac
}

download_freerouting() {
    [ -f "$FREEROUTING_JAR" ] && return 0
    echo "Downloading FreeRouting $FREEROUTING_VERSION..."
    if ! curl -fsSL -o "$FREEROUTING_JAR" "$FREEROUTING_URL"; then
        rm -f "$FREEROUTING_JAR"
        echo "ERROR: Failed to download $FREEROUTING_URL" >&2
        echo "Download manually from https://github.com/freerouting/freerouting/releases" >&2
        echo "and save as: $FREEROUTING_JAR (or set FREEROUTING_JAR)" >&2
        exit 1
    fi
}

export_dsn() {
    local kicad_py="$1" pcb="$2" dsn="$3"
    "$kicad_py" - "$pcb" "$dsn" <<'PY'
import sys
import pcbnew

board = pcbnew.LoadBoard(sys.argv[1])
if not pcbnew.ExportSpecctraDSN(board, sys.argv[2]):
    raise SystemExit("pcbnew.ExportSpecctraDSN returned False")
PY
}

KICAD_CLI_BIN="$(find_kicad_cli)" || die "kicad-cli not found; install KiCad 10 or set KICAD_CLI"

echo "=== specs-to-pcb - Automated Routing Pipeline ==="
echo ""

# Step 1: Regenerate KiCad project from specs
echo "[1/5] Regenerating KiCad project from specs..."
python3 "$SCRIPT_DIR/generate_kicad_project.py" "$KICAD_DIR"

# Step 2: Generate custom footprints
echo "[2/5] Generating custom footprints..."
if [ -f "$SCRIPT_DIR/generate_footprints.py" ]; then
    python3 "$SCRIPT_DIR/generate_footprints.py"
fi

resolve_project_name
PCB_FILE="$KICAD_DIR/$PROJECT_NAME.kicad_pcb"
SCH_FILE="$KICAD_DIR/$PROJECT_NAME.kicad_sch"
DSN_FILE="$KICAD_DIR/$PROJECT_NAME.dsn"
SES_FILE="$KICAD_DIR/$PROJECT_NAME.ses"
[ -f "$PCB_FILE" ] || die "$PCB_FILE not found; check PROJECT_NAME"
echo "  Project: $PROJECT_NAME"

# Step 3: Run ERC
echo "[3/5] Running Electrical Rules Check..."
"$KICAD_CLI_BIN" sch erc "$SCH_FILE" \
    --output "$KICAD_DIR/erc-report.json" --format json 2>&1
echo ""

# Step 4: Export DSN and run FreeRouting
echo "[4/5] Exporting DSN and running FreeRouting autorouter..."
if [ ! -f "$DSN_FILE" ]; then
    if KICAD_PY_BIN="$(find_kicad_python)"; then
        echo "  Exporting DSN with pcbnew ($KICAD_PY_BIN)..."
        export_dsn "$KICAD_PY_BIN" "$PCB_FILE" "$DSN_FILE" || echo "  DSN export failed."
    else
        echo "  KiCad bundled Python not found (set KICAD_PYTHON to enable headless DSN export)."
    fi
fi

if [ -f "$DSN_FILE" ]; then
    if JAVA_BIN="$(find_java)"; then
        download_freerouting
        echo "  Running FreeRouting on $DSN_FILE..."
        "$JAVA_BIN" -jar "$FREEROUTING_JAR" \
            -de "$DSN_FILE" \
            -do "$SES_FILE" \
            -mp 10 \
            -mt 4 \
            --gui.enabled=false 2>&1 || echo "  FreeRouting completed (check for errors above)"

        if [ -f "$SES_FILE" ]; then
            echo "  Routing complete! Import $SES_FILE into KiCad:"
            echo "    File > Import > Specctra SES"
            echo "    (or pcbnew.ImportSpecctraSES(board, path) in KiCad's Python)"
        fi
    else
        echo "  Java not found (brew install openjdk@21, or set JAVA). Skipping FreeRouting."
    fi
else
    echo "  No DSN file found. To autoroute:"
    echo "    1. Open $PCB_FILE in KiCad"
    echo "    2. File > Export > Specctra DSN"
    echo "    3. Re-run this script"
fi

# Step 5: Run DRC
echo ""
echo "[5/5] Running Design Rules Check..."
"$KICAD_CLI_BIN" pcb drc "$PCB_FILE" \
    --output "$KICAD_DIR/drc-report.json" --format json 2>&1

echo ""
echo "=== Pipeline Complete ==="
echo ""
echo "Reports:"
echo "  ERC: $KICAD_DIR/erc-report.json"
echo "  DRC: $KICAD_DIR/drc-report.json"
echo ""
echo "Open project: open $KICAD_DIR/$PROJECT_NAME.kicad_pro"
