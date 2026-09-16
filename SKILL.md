---
name: specs-to-pcb
description: Turn hardware specs (BOM, connectivity diagrams, component dimensions) into a complete KiCad PCB project with schematic, autorouted layout, review images, and ID export files - zero manual intervention.
version: "1.0.0"
user-invocable: true
allowed-tools: "Read, Write, Edit, Bash, Glob, Grep, Agent, WebFetch, WebSearch"
---

# Specs-to-PCB: Hardware Spec to Production PCB

Generate a complete KiCad PCB project from hardware specification documents. Takes BOM lists, connectivity diagrams, and component dimension specs as input and produces a ready-to-review PCB design with autorouted traces and full export packages.

## When to Use

Trigger this skill when the user:
- Has hardware specification documents (BOM, connectivity reference, component dimensions)
- Wants to generate a KiCad PCB project from specs
- Needs to go from "paper design" to "reviewable PCB" without manual KiCad work
- Asks to turn a schematic/block diagram into a PCB

## What This Skill Produces

### KiCad Project
- `.kicad_sch` - Schematic with all nets wired via global labels + wire stubs
- `.kicad_pcb` - PCB with board outline, layer stackup, component placement
- `.kicad_pro` - Project file with net classes (Default, Power, RF)
- `libs/custom.kicad_sym` - Custom symbol library
- `libs/custom.pretty/` - Custom footprint library (.kicad_mod files)

### Autorouted PCB
- Specctra DSN export via `pcbnew` Python API (no GUI)
- FreeRouting CLI headless autorouting
- Specctra SES import back into PCB

### Review Package
- 16+ PNG images at multiple zoom levels (schematic + PCB views)
- Schematic PDF (vector)
- ERC/DRC reports (JSON)
- Review summary document with pin map, power architecture, open items

### ID Export Package
- STEP files (board-only + assembly)
- GLB (3D preview for web/AR)
- DXF files (outline, courtyards, fab layer, flex zones)
- Gerbers (all layers)
- Component position CSV
- Mechanical interface specification

## Prerequisites

### Required (auto-installed by skill)
- Python 3.10+
- `kiutils` Python package
- `kicad-sch-api` Python package

### Required (must be installed)
- KiCad 8+ (`brew install --cask kicad` or download from kicad.org)
- Java 17+ (`brew install openjdk@21`) - for FreeRouting autorouter

### Auto-downloaded
- FreeRouting JAR (downloaded on first run)

## Input Requirements

The skill needs **at minimum** these inputs from the user:

### 1. Component List (Required)
Any of: BOM spreadsheet, component list PDF, or structured description including:
- Part numbers / component names
- Package types (QFN, WSON, LGA, 0402, etc.)
- Physical dimensions

### 2. Connectivity Information (Required)
Any of: block diagram, connectivity table, or description including:
- Which components connect to which
- Bus types (I2C, SPI, QSPI, PDM, UART, GPIO, etc.)
- Signal names and pin assignments

### 3. Board Constraints (Optional but recommended)
- Board dimensions and shape
- Layer count and stackup
- Rigid-flex requirements
- Special routing constraints (impedance, length matching)

## Pipeline Stages

### Stage 1: Parse & Extract
Read user-provided documents (PDF, CSV, images, text) and extract:
- Component list with packages and dimensions
- Interface/connectivity table
- Pin assignments (look up datasheets if not provided)
- Power architecture

Save structured data as `netlist.json` and `pin_map.json`.

### Stage 2: Component Libraries
For each component:
1. Check KiCad standard libraries
2. Check community libraries (Nordic, TI, etc.)
3. Generate custom `.kicad_sym` symbols (simplified to used pins only)
4. Generate custom `.kicad_mod` footprints with real pads

### Stage 3: Schematic Generation
Generate `.kicad_sch` with:
- Component instances placed in logical groups
- Wire stubs from every pin endpoint to global labels
- Net names matching the connectivity reference
- Decoupling caps and pull-up resistors

**Key technique:** Calculate absolute pin endpoints from symbol definitions + component placement, draw wire from pin tip outward, place global label at wire end. This ensures KiCad ERC sees proper connections.

### Stage 4: PCB Generation
Generate `.kicad_pcb` with:
- Board outline on Edge.Cuts (including flex zones if rigid-flex)
- Layer stackup (2/4/6 layer)
- Component placement in approximate positions
- Net definitions
- Design rules and net classes
- GND copper pour zones

### Stage 5: Real Footprints + Autoroute
Using KiCad's bundled Python (`pcbnew` module):
1. Load the generated PCB
2. Add real footprints from `.kicad_mod` libraries
3. Assign nets to pads based on netlist
4. Export Specctra DSN via `pcbnew.ExportSpecctraDSN()`
5. Run FreeRouting CLI headless: `java -jar freerouting.jar -de board.dsn -do board.ses --gui.enabled=false`
6. Import routes via `pcbnew.ImportSpecctraSES()`

**Critical:** Do all pcbnew operations in a single Python session - pcbnew saves in a newer format that it can't always re-read.

### Stage 6: Verification
Run `kicad-cli` automated checks:
```bash
kicad-cli sch erc design.kicad_sch --output erc.json --format json
kicad-cli pcb drc design.kicad_pcb --output drc.json --format json
```

### Stage 7: Review Package
Export visual review materials:
```bash
# Schematic SVG + PDF
kicad-cli sch export svg design.kicad_sch -o review/ -e --no-background-color
kicad-cli sch export pdf design.kicad_sch -o review/schematic.pdf

# PCB layer views
kicad-cli pcb export svg design.kicad_pcb -o review/ -l "F.Cu" --cl "Edge.Cuts,F.SilkS" --page-size-mode 2 --mode-single

# Convert SVG to PNG at multiple resolutions
rsvg-convert -w 4000 review/schematic.svg -o review/01-schematic-full.png
# Crop for zoomed views using sips
```

For routed board views, use `pcbnew` PLOT_CONTROLLER in the same session.

### Stage 8: ID Export
```bash
kicad-cli pcb export step design.kicad_pcb -o export/board.step --board-only --include-tracks --force
kicad-cli pcb export step design.kicad_pcb -o export/assembly.step --include-tracks --force
kicad-cli pcb export glb design.kicad_pcb -o export/preview.glb --force
kicad-cli pcb export dxf design.kicad_pcb -o export/ -l "Edge.Cuts" --output-units mm --mode-single --use-contours
kicad-cli pcb export gerbers design.kicad_pcb -o export/gerbers/
kicad-cli pcb export pos design.kicad_pcb -o export/positions.csv --format csv --units mm --side both
```

## KiCad 10 Format Notes

These format requirements were discovered through testing with KiCad 10.0.0:

### Schematic (.kicad_sch)
- Version: `20250114`
- Sub-symbol names must NOT include library prefix: use `R_0_1` not `vantage:R_0_1`
- Property hide: `(hide yes)` not just `hide`
- `(exclude_from_sim no)` before `(in_bom yes)`
- Wire stroke: `(type solid)` (not `default`)
- All coordinates must be on 2.54mm grid for pin connections to work

### PCB (.kicad_pcb)
- Version: `20241229`
- NO semicolon comments (`;`) - causes parse failure
- Layer numbering: F.Cu=0, F.Mask=1, B.Cu=2, B.Mask=3, In1.Cu=4, In2.Cu=6, Edge.Cuts=25
- Avoid complex `(stackup ...)` section - causes parse failure in some cases

### Symbol Library (.kicad_sym)
- Version: `20251024`

### Footprints (.kicad_mod)
- Version: `20260206` (or `version 6` for compatibility)
- `kicad-cli fp upgrade` validates format

### pcbnew Python API
- Use KiCad's bundled Python: `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9`
- `board.FindNet(name)` for net lookup (NOT `board.GetNetInfo().GetNetItem()`)
- Don't Remove/Delete footprints from board (SWIG segfaults) - add new ones alongside
- Do all operations in one session - pcbnew writes newer format than kicad-cli reads
- `pcbnew.ExportSpecctraDSN(board, path)` and `pcbnew.ImportSpecctraSES(board, path)` work headlessly

## Conventions

### Net Naming
Use uppercase with underscores: `VDD_1V8`, `QSPI_IO0`, `I2C_SCL`, `PDM_CLK`

### Reference Designators
Standard: U (ICs), R (resistors), C (caps), L (inductors), D (diodes/LEDs), Y (crystals), M (mics), H (actuators), J (connectors), SW (switches), ANT (antennas), BT (batteries)

### File Organization
```
project/
  kicad/
    design.kicad_pro
    design.kicad_sch
    design.kicad_pcb
    libs/
      custom.kicad_sym
      custom.pretty/
    review/           (generated)
    id-export/        (generated)
  scripts/
    generate_kicad_project.py
    generate_footprints.py
    pcb_build_and_route.py
    autoroute.sh
    pin_map.json
    netlist.json
```

## Error Handling

- If KiCad not installed: prompt user to `brew install --cask kicad`
- If Java not installed: prompt user to `brew install openjdk@21`
- If FreeRouting fails: skip routing, leave PCB with ratsnest
- If ERC has errors: report them but don't block pipeline
- If pcbnew crashes: fall back to kicad-cli for non-pcbnew steps
