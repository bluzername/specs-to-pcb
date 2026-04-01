#!/bin/bash
# Vantage V1 Lite - Automated PCB Routing Pipeline
#
# Prerequisites:
#   - KiCad 10 installed (kicad-cli available)
#   - Java 21+ installed (for FreeRouting)
#   - FreeRouting JAR downloaded to this directory
#
# Usage: ./autoroute.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
KICAD_DIR="$SCRIPT_DIR/../kicad"
PCB_FILE="$KICAD_DIR/vantage-v1-lite.kicad_pcb"
DSN_FILE="$KICAD_DIR/vantage-v1-lite.dsn"
SES_FILE="$KICAD_DIR/vantage-v1-lite.ses"

# Find Java
JAVA_BIN="java"
if [ -f /opt/homebrew/opt/openjdk@21/bin/java ]; then
    JAVA_BIN="/opt/homebrew/opt/openjdk@21/bin/java"
elif [ -f /opt/homebrew/opt/openjdk/bin/java ]; then
    JAVA_BIN="/opt/homebrew/opt/openjdk/bin/java"
fi

# Find or download FreeRouting
FREEROUTING_JAR="$SCRIPT_DIR/freerouting.jar"
if [ ! -f "$FREEROUTING_JAR" ]; then
    echo "Downloading FreeRouting..."
    curl -L -o "$FREEROUTING_JAR" \
        "https://github.com/freerouting/freerouting/releases/download/v2.0.1/freerouting-2.0.1.jar" \
        2>/dev/null || {
        echo "ERROR: Failed to download FreeRouting."
        echo "Please download manually from: https://github.com/freerouting/freerouting/releases"
        echo "Save as: $FREEROUTING_JAR"
        exit 1
    }
fi

echo "=== Vantage V1 Lite - Automated Routing Pipeline ==="
echo ""

# Step 1: Regenerate KiCad project from specs
echo "[1/5] Regenerating KiCad project from specs..."
python3 "$SCRIPT_DIR/generate_kicad_project.py" "$KICAD_DIR"

# Step 2: Generate custom footprints
echo "[2/5] Generating custom footprints..."
if [ -f "$SCRIPT_DIR/generate_footprints.py" ]; then
    python3 "$SCRIPT_DIR/generate_footprints.py"
fi

# Step 3: Run ERC
echo "[3/5] Running Electrical Rules Check..."
kicad-cli sch erc "$KICAD_DIR/vantage-v1-lite.kicad_sch" \
    --output "$KICAD_DIR/erc-report.json" --format json 2>&1
echo ""

# Step 4: Export DSN for FreeRouting
echo "[4/5] Exporting DSN and running FreeRouting autorouter..."
# Note: kicad-cli doesn't support DSN export directly.
# The PCB needs to be opened in KiCad GUI to export DSN.
# As a workaround, if DSN exists (manually exported), route it.
if [ -f "$DSN_FILE" ]; then
    echo "  Found existing DSN file. Running FreeRouting..."
    "$JAVA_BIN" -jar "$FREEROUTING_JAR" \
        -de "$DSN_FILE" \
        -do "$SES_FILE" \
        -mp 10 \
        -mt 4 \
        --gui.enabled=false 2>&1 || echo "  FreeRouting completed (check for errors above)"

    if [ -f "$SES_FILE" ]; then
        echo "  Routing complete! Import $SES_FILE into KiCad:"
        echo "    File > Import > Specctra SES"
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
kicad-cli pcb drc "$PCB_FILE" \
    --output "$KICAD_DIR/drc-report.json" --format json 2>&1

echo ""
echo "=== Pipeline Complete ==="
echo ""
echo "Reports:"
echo "  ERC: $KICAD_DIR/erc-report.json"
echo "  DRC: $KICAD_DIR/drc-report.json"
echo ""
echo "Open project: open $KICAD_DIR/vantage-v1-lite.kicad_pro"
