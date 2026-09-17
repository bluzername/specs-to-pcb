# specs-to-pcb

[![CI](https://github.com/bluzername/specs-to-pcb/actions/workflows/ci.yml/badge.svg)](https://github.com/bluzername/specs-to-pcb/actions/workflows/ci.yml)

A Claude Code skill that turns hardware specification documents into complete KiCad 10 PCB projects - with zero manual GUI interaction.

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
[6] Export Specctra DSN (pcbnew.ExportSpecctraDSN via KiCad's Python - no GUI)
    |
    v
[7] FreeRouting CLI autoroute (headless)
    |
    v
[8] Import routes (pcbnew.ImportSpecctraSES)
    |
    v
[9] kicad-cli: ERC + DRC verification
    |
    v
[10] Generate review package (16+ PNGs at multiple zoom levels)
    |
    v
[11] Generate ID exports (STEP, GLB, DXF, Gerbers, position CSV)
```

Steps 1-5 are what Claude does with the skill's instructions, using the generators in `example/scripts/` as the template. Steps 6, 7 and 9 are `example/scripts/autoroute.sh`. Step 8 is a one-off `pcbnew` session (or File > Import > Specctra SES). Steps 10-11 are `kicad-cli` commands listed in `SKILL.md`.

## Repository layout

```
SKILL.md                      # The Claude Code skill (frontmatter + instructions)
scripts/check-prereqs.sh      # Verifies KiCad, Java, Python packages, pcbnew
templates/netlist-template.json
requirements.txt              # Pinned Python helper packages
example/scripts/
  generate_kicad_project.py   # Writes symbols, schematic, PCB, project file
  generate_footprints.py      # Writes .kicad_mod footprints, validates with kicad-cli
  autoroute.sh                # Regen, ERC, DSN export, FreeRouting, DRC
  netlist.json                # Structured connectivity for the example
  pin_map.json                # MCU pin assignments for the example
```

## Installation

### 1. Install the Claude Code skill

`SKILL.md` is at the repo root, so the clone itself is the skill directory:

```bash
git clone https://github.com/bluzername/specs-to-pcb.git ~/.claude/skills/specs-to-pcb
```

### 2. Install prerequisites

```bash
# KiCad 10 (free, open source)
brew install --cask kicad

# Python packages (kiutils, kicad-sch-api)
pip3 install -r ~/.claude/skills/specs-to-pcb/requirements.txt

# Java (for FreeRouting autorouter)
brew install openjdk@21

# SVG to PNG conversion (for review images)
brew install librsvg

# Verify
bash ~/.claude/skills/specs-to-pcb/scripts/check-prereqs.sh
```

`check-prereqs.sh` exits non-zero when a required item is missing. Java, rsvg-convert and pcbnew only warn. Pass `--report-only` to always exit 0 (used by CI). It finds Java via `PATH`, then Homebrew `openjdk@21`, `openjdk@17` and `openjdk`, and validates that the binary actually runs (macOS ships a `/usr/bin/java` stub that does not). KiCad's bundled Python is found by globbing `/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/*/bin/python3`. Override any of these with `JAVA`, `KICAD_PYTHON` or `KICAD_CLI`.

About the Python packages: `requirements.txt` pins `kiutils==1.4.8` and `kicad-sch-api==0.5.6`. kiutils has had no release since 2024-02 (1.4.8) and predates the KiCad 10 file formats, so treat it as a parser for older files rather than a KiCad 10 writer. The example generators write KiCad 10 files directly and import neither package.

### 3. FreeRouting (auto-downloaded on first run)

`autoroute.sh` downloads `freerouting-<version>.jar` next to itself on first run (default version 2.4.1). To download manually:

```bash
curl -fL -o freerouting-2.4.1.jar https://github.com/freerouting/freerouting/releases/download/v2.4.1/freerouting-2.4.1.jar
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

### Running the routing pipeline

Copy `example/scripts/autoroute.sh` into your project's `scripts/` directory next to the generators and run it:

```bash
./scripts/autoroute.sh              # project name from the single kicad/*.kicad_pro
./scripts/autoroute.sh my-board     # explicit project name
```

It regenerates the project, runs ERC, exports a Specctra DSN with KiCad's bundled Python, runs FreeRouting headlessly and runs DRC. If it cannot find KiCad's Python it prints the manual File > Export > Specctra DSN steps instead. If it cannot find Java it skips routing. Importing the routed `.ses` back into the board is a separate step (`pcbnew.ImportSpecctraSES` or File > Import > Specctra SES).

Environment overrides:

| Variable | Default | Purpose |
|----------|---------|---------|
| `PROJECT_NAME` | single `*.kicad_pro` in `../kicad` | Basename of the project files (first argument also works) |
| `FREEROUTING_VERSION` | `2.4.1` | FreeRouting release to download |
| `FREEROUTING_JAR` | `scripts/freerouting-<version>.jar` | Use an existing jar, skip the download |
| `JAVA` | `java` on PATH, then Homebrew openjdk@21/@17/openjdk | Java binary |
| `KICAD_PYTHON` | globbed from `KiCad.app` | KiCad bundled Python (for `pcbnew`) |
| `KICAD_CLI` | `kicad-cli` on PATH, then `KiCad.app/Contents/MacOS/kicad-cli` | kicad-cli binary |

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
  autoroute.sh                  # Regen, ERC, DSN export, FreeRouting, DRC
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

This example was generated from three PDF specification documents in a single Claude Code session. To regenerate it:

```bash
cd example/scripts
python3 generate_kicad_project.py ../kicad
python3 generate_footprints.py
```

## Key Technical Discoveries

These format details were discovered through extensive testing with KiCad 10.0.0 and are documented in the skill to save others the debugging:

- **Sub-symbol naming**: KiCad 10 requires `R_0_1` not `vantage:R_0_1` (no library prefix in sub-symbols)
- **PCB comments**: Semicolon comments (`;`) cause parse failure in `.kicad_pcb` files
- **Layer IDs**: KiCad 10 uses different layer numbering than KiCad 8 (F.Cu=0, B.Cu=2, In1.Cu=4, Edge.Cuts=25)
- **Grid alignment**: Pin connections only work when all coordinates are on the 2.54mm grid
- **pcbnew headless**: `ExportSpecctraDSN()` and `ImportSpecctraSES()` work without GUI via KiCad's bundled Python
- **pcbnew session**: Do all pcbnew operations that save the board in one Python invocation - it writes a format version it can't always re-read

## Development

CI (`.github/workflows/ci.yml`) runs on every push and pull request: `py_compile` on the example generators, JSON validation, `shellcheck -S style` and `bash -n` on every shell script, a SKILL.md frontmatter check, `pip install -r requirements.txt` plus an import smoke test on Python 3.12, and `check-prereqs.sh --report-only`. Dependabot watches pip and GitHub Actions weekly.

To run the same checks locally:

```bash
python3 -m py_compile example/scripts/*.py
for f in example/scripts/*.json templates/*.json; do python3 -m json.tool "$f" >/dev/null; done
shellcheck -S style scripts/*.sh example/scripts/*.sh && bash -n scripts/*.sh example/scripts/*.sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python -c "import kiutils, kicad_sch_api"
```

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
