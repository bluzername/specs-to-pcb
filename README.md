# specs-to-pcb

A Claude Code skill that turns hardware specification documents into complete, production-ready KiCad PCB projects - with zero manual GUI interaction.

**Input:** BOM + connectivity diagram + component dimensions
**Output:** KiCad project + autorouted PCB + review images + ID firm export package

## What makes this different

| Feature | specs-to-pcb | KiCad MCP Servers | Atopile | Circuit-Synth | SKiDL |
|---------|-------------|-------------------|---------|---------------|-------|
| Input: hardware specs/PDFs | Yes | No | No | No | No |
| Generates schematic with real nets | Yes | Edit only | Yes | Yes | Yes |
| Generates PCB with placement | Yes | Edit only | Manual | No | No |
| Headless autorouting (FreeRouting) | Yes | No | No | No | No |
| Review image package (16+ PNGs) | Yes | No | No | No | No |
| ID firm exports (STEP/DXF/Gerber) | Yes | No | No | No | No |
| Zero GUI clicks required | Yes | No | No | No | N/A |
| Claude Code skill | Yes | MCP server | CLI | Yes | Library |

## Pipeline

```
Hardware Specs (PDF/CSV/text)
    |
    v
[1] Parse & extract structured data (netlist.json + pin_map.json)
    |
    v
[2] Generate KiCad symbol library (.kicad_sym)
    |
    v
[3] Generate custom footprints (.kicad_mod) with real pads
    |
    v
[4] Generate schematic (.kicad_sch) with wire-connected nets
    |
    v
[5] Generate PCB (.kicad_pcb) with outline + placement
    |
    v
[6] Load real footprints + assign nets via pcbnew Python API
    |
    v
[7] Export Specctra DSN (pcbnew.ExportSpecctraDSN - no GUI)
    |
    v
[8] FreeRouting CLI autoroute (headless)
    |
    v
[9] Import routes (pcbnew.ImportSpecctraSES)
    |
    v
[10] kicad-cli: ERC + DRC verification
    |
    v
[11] Generate review package (16+ PNGs at multiple zoom levels)
    |
    v
[12] Generate ID exports (STEP, GLB, DXF, Gerbers, position CSV)
```

## Installation

### 1. Install the Claude Code skill

```bash
# Clone to your Claude Code skills directory
git clone https://github.com/bluzername/specs-to-pcb.git ~/.claude/skills/specs-to-pcb
```

Or manually copy the `skill/` directory contents to `~/.claude/skills/specs-to-pcb/`.

### 2. Install prerequisites

```bash
# KiCad 10 (free, open source)
brew install --cask kicad

# Python packages
pip3 install kiutils kicad-sch-api

# Java (for FreeRouting autorouter)
brew install openjdk@21

# SVG to PNG conversion (for review images)
brew install librsvg

# Verify
bash ~/.claude/skills/specs-to-pcb/scripts/check-prereqs.sh
```

### 3. FreeRouting (auto-downloaded on first run)

The autoroute script downloads FreeRouting automatically. Or manually:

```bash
curl -L -o freerouting.jar https://github.com/freerouting/freerouting/releases/download/v2.0.1/freerouting-2.0.1.jar
```

## Usage

### In Claude Code

```
/specs-to-pcb
```

Then provide your hardware specs:
- BOM spreadsheet or component list
- Connectivity diagram or interface table
- Component dimensions (optional)
- Board constraints (optional)

### Example prompt

> Here are my hardware specs:
> - BOM: [paste or file path]
> - Connectivity: [paste or file path]
> - Board: 4-layer, 50x30mm, rigid
>
> Generate a complete KiCad PCB project.

## Output

The skill generates these files in your project directory:

```
kicad/
  design.kicad_pro              # KiCad project (open this)
  design.kicad_sch              # Schematic with all nets wired
  design.kicad_pcb              # PCB with routed traces
  libs/
    custom.kicad_sym            # Component symbols
    custom.pretty/              # Component footprints
  review/
    01-schematic-full.png       # Full schematic
    02-schematic-*-zoom.png     # Zoomed schematic sections
    04-pcb-overview.png         # PCB all layers
    05-pcb-routed-front.png     # Front copper + traces
    08-pcb-outline.png          # Board outline
    schematic.pdf               # Vector schematic
    REVIEW-PACKAGE.md           # Review summary
  id-export/
    board.step                  # 3D model (board only)
    assembly.step               # 3D model (with components)
    preview.glb                 # 3D preview for web/AR
    dxf-outline/                # Board outline DXF
    dxf-courtyards/             # Component zones DXF
    gerbers/                    # Manufacturing Gerbers
    positions.csv               # Component XY positions
    MECHANICAL-INTERFACE.md     # ID firm spec document
scripts/
  generate_kicad_project.py     # Regenerate anytime
  generate_footprints.py        # Regenerate footprints
  autoroute.sh                  # Full pipeline script
  netlist.json                  # Structured connectivity data
  pin_map.json                  # MCU pin assignments
```

## Example: nRF5340 BLE Wearable

The `example/` directory contains a complete working example - an nRF5340-based wearable device with:

- nRF5340 SoC (aQFN94)
- 16MB QSPI flash (W25Q128JV)
- PMIC (nPM1300) with charger + buck + LDO
- Haptic driver (DRV2605L) + LRA actuator
- 2x PDM MEMS microphones (IM72D128V)
- BLE 5.3 antenna (PCB trace)
- 4-layer rigid-flex PCB (~50x19mm)
- 24 interfaces, 37 signal traces

This example was generated from three PDF specification documents in a single Claude Code session.

## Key Technical Discoveries

These format details were discovered through extensive testing with KiCad 10.0.0 and are documented in the skill to save others the debugging:

- **Sub-symbol naming**: KiCad 10 requires `R_0_1` not `vantage:R_0_1` (no library prefix in sub-symbols)
- **PCB comments**: Semicolon comments (`;`) cause parse failure in `.kicad_pcb` files
- **Layer IDs**: KiCad 10 uses different layer numbering than KiCad 8 (F.Cu=0, B.Cu=2, In1.Cu=4, Edge.Cuts=25)
- **Grid alignment**: Pin connections only work when all coordinates are on the 2.54mm grid
- **pcbnew headless**: `ExportSpecctraDSN()` and `ImportSpecctraSES()` work without GUI via KiCad's bundled Python
- **pcbnew session**: Do all pcbnew operations in one Python invocation - it writes a format version it can't always re-read

## How it compares

### vs. Atopile
Atopile is a design *language* - you write `.ato` code to describe circuits. specs-to-pcb takes *existing specifications* (PDFs, BOMs, connectivity tables) and generates the PCB. Different input paradigm: code-first vs spec-driven.

### vs. KiCad MCP Servers
MCP servers (mixelpixx, Seeed-Studio, lamaalrajih) let Claude *inspect and edit* existing KiCad files. specs-to-pcb *generates* the entire project from scratch, including autorouting.

### vs. Circuit-Synth
Circuit-Synth is a Claude Code skill for Python-coded circuits. specs-to-pcb takes hardware specs as input instead of Python circuit definitions, and includes the full pipeline through routing and export.

### vs. pcb-designer-ai-agent
Similar pipeline concept but still in early scaffold stage. specs-to-pcb has a working implementation with real footprints, autorouting, and export packages.

## License

MIT

## Credits

Built with:
- [KiCad](https://www.kicad.org/) - Open source EDA
- [FreeRouting](https://github.com/freerouting/freerouting) - Open source autorouter
- [kiutils](https://github.com/mvnmgrx/kiutils) - KiCad file manipulation
- [kicad-sch-api](https://pypi.org/project/kicad-sch-api/) - Schematic API
- [Claude Code](https://claude.ai/code) - AI coding assistant
