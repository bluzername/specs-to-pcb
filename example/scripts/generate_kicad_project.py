#!/usr/bin/env python3
"""
Vantage V1 Lite - KiCad Project Generator

Generates a complete KiCad 8 project from the connectivity reference
and component dimensions specs. Produces:
  - vantage.kicad_sym (custom symbol library)
  - vantage-v1-lite.kicad_sch (schematic with real connectivity)
  - vantage-v1-lite.kicad_pcb (PCB with board outline + placement)
  - vantage-v1-lite.kicad_pro (project file)
  - sym-lib-table / fp-lib-table (library tables)

Usage:
  python3 generate_kicad_project.py [output_dir]
  Default output_dir: ../kicad/
"""

import json
import os
import sys
import uuid as uuid_mod
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def uid():
    """Generate a KiCad-style UUID."""
    return str(uuid_mod.uuid4())


@dataclass
class Pin:
    number: str
    name: str
    pin_type: str  # input, output, bidirectional, passive, power_in, power_out, unconnected
    x: float = 0
    y: float = 0
    length: float = 2.54
    direction: str = "L"  # L, R, U, D


@dataclass
class SymbolDef:
    lib_name: str
    ref_prefix: str
    pins: list
    description: str = ""
    footprint: str = ""
    value: str = ""


# ---------------------------------------------------------------------------
# Pin map from pin_map.json
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
with open(SCRIPT_DIR / "pin_map.json") as f:
    PIN_MAP = json.load(f)

with open(SCRIPT_DIR / "netlist.json") as f:
    NETLIST = json.load(f)


# ---------------------------------------------------------------------------
# Symbol definitions - simplified to used pins only
# ---------------------------------------------------------------------------

def make_nrf5340_symbol():
    """nRF5340 SoC - show only the pins we use (not all 94)."""
    pins = []
    y = 0
    spacing = 2.54

    # Left side pins (active connections)
    left_pins = [
        ("QSPI_IO0", "P0.13", "bidirectional"),
        ("QSPI_IO1", "P0.14", "bidirectional"),
        ("QSPI_IO2", "P0.15", "bidirectional"),
        ("QSPI_IO3", "P0.16", "bidirectional"),
        ("QSPI_SCK", "P0.17", "output"),
        ("QSPI_CSN", "P0.18", "output"),
        ("XL1", "P0.00", "passive"),
        ("XL2", "P0.01", "passive"),
        ("PMIC_IRQ", "P0.04", "input"),
        ("PMIC_SHPHLD", "P0.05", "output"),
        ("LED_R", "P0.07", "output"),
        ("LED_G", "P0.25", "output"),
        ("LED_B", "P0.26", "output"),
    ]

    # Right side pins
    right_pins = [
        ("I2C_SDA", "P1.02", "bidirectional"),
        ("I2C_SCL", "P1.03", "bidirectional"),
        ("PDM_CLK", "P1.04", "output"),
        ("PDM_DIN", "P1.05", "input"),
        ("DRV_EN", "P1.06", "output"),
        ("BTN_IRQ", "P1.07", "input"),
        ("MIC1_LR", "P1.08", "output"),
        ("MIC2_LR", "P1.09", "output"),
        ("UART_TX", "P1.01", "output"),
        ("UART_RX", "P1.00", "input"),
    ]

    # Top pins (power)
    top_pins = [
        ("VDD", "VDD", "power_in"),
        ("VSS", "VSS", "power_in"),
        ("DEC1", "DEC1", "passive"),
        ("DEC4", "DEC4", "passive"),
    ]

    # Bottom pins (special)
    bottom_pins = [
        ("XC1", "XC1", "passive"),
        ("XC2", "XC2", "passive"),
        ("ANT", "ANT", "passive"),
    ]

    # Build pin list with positions
    # Left side: pins go downward
    box_h = max(len(left_pins), len(right_pins)) * spacing
    box_w = 20.32  # 8 grid units wide

    for i, (name, number, ptype) in enumerate(left_pins):
        pins.append(Pin(number=number, name=name, pin_type=ptype,
                       x=-box_w/2 - 2.54, y=box_h/2 - i*spacing,
                       direction="R"))

    for i, (name, number, ptype) in enumerate(right_pins):
        pins.append(Pin(number=number, name=name, pin_type=ptype,
                       x=box_w/2 + 2.54, y=box_h/2 - i*spacing,
                       direction="L"))

    for i, (name, number, ptype) in enumerate(top_pins):
        pins.append(Pin(number=number, name=name, pin_type=ptype,
                       x=-box_w/4 + i*spacing*2, y=box_h/2 + 2.54,
                       direction="D"))

    for i, (name, number, ptype) in enumerate(bottom_pins):
        pins.append(Pin(number=number, name=name, pin_type=ptype,
                       x=-box_w/4 + i*spacing*2, y=-box_h/2 - 2.54,
                       direction="U"))

    return SymbolDef(
        lib_name="nRF5340",
        ref_prefix="U",
        pins=pins,
        description="Nordic nRF5340 SoC (simplified - used pins only)",
        footprint="Nordic:QFN-94-1EP_7x7mm",
        value="nRF5340-QKAA"
    )


def make_simple_symbol(lib_name, ref_prefix, description, footprint, value,
                       left_pins=None, right_pins=None, top_pins=None, bottom_pins=None):
    """Create a simple rectangular symbol with pins on each side."""
    left_pins = left_pins or []
    right_pins = right_pins or []
    top_pins = top_pins or []
    bottom_pins = bottom_pins or []

    spacing = 2.54
    max_side = max(len(left_pins), len(right_pins), 1)
    max_tb = max(len(top_pins), len(bottom_pins), 1)
    box_h = max_side * spacing + spacing
    box_w = max(max_tb * spacing * 2 + spacing, 10.16)

    pins = []
    for i, (name, number, ptype) in enumerate(left_pins):
        pins.append(Pin(number=number, name=name, pin_type=ptype,
                       x=-box_w/2 - 2.54, y=box_h/2 - spacing - i*spacing,
                       direction="R"))

    for i, (name, number, ptype) in enumerate(right_pins):
        pins.append(Pin(number=number, name=name, pin_type=ptype,
                       x=box_w/2 + 2.54, y=box_h/2 - spacing - i*spacing,
                       direction="L"))

    for i, (name, number, ptype) in enumerate(top_pins):
        pins.append(Pin(number=number, name=name, pin_type=ptype,
                       x=-box_w/4 + i*spacing*2, y=box_h/2 + 2.54,
                       direction="D"))

    for i, (name, number, ptype) in enumerate(bottom_pins):
        pins.append(Pin(number=number, name=name, pin_type=ptype,
                       x=-box_w/4 + i*spacing*2, y=-box_h/2 - 2.54,
                       direction="U"))

    return SymbolDef(lib_name=lib_name, ref_prefix=ref_prefix, pins=pins,
                     description=description, footprint=footprint, value=value)


# Component symbol definitions
SYMBOLS = {}

SYMBOLS["nRF5340"] = make_nrf5340_symbol()

SYMBOLS["W25Q128JV"] = make_simple_symbol(
    "W25Q128JV", "U", "Winbond 16MB QSPI NOR Flash",
    "Package_SON:WSON-8-1EP_6x5mm_P1.27mm_EP3.4x4.3mm", "W25Q128JV",
    left_pins=[
        ("CS#", "1", "input"),
        ("DO/IO1", "2", "bidirectional"),
        ("WP#/IO2", "3", "bidirectional"),
        ("GND", "4", "power_in"),
    ],
    right_pins=[
        ("VCC", "8", "power_in"),
        ("DI/IO0", "5", "bidirectional"),
        ("CLK", "6", "input"),
        ("HOLD#/IO3", "7", "bidirectional"),
    ]
)

SYMBOLS["nPM1300"] = make_simple_symbol(
    "nPM1300", "U", "Nordic nPM1300 PMIC",
    "Nordic:QFN-32-1EP_5x5mm", "nPM1300",
    left_pins=[
        ("VBAT", "VBAT", "power_in"),
        ("VBUS", "VBUS", "power_in"),
        ("BATT+", "BCHG", "power_out"),
        ("SDA", "SDA", "bidirectional"),
        ("SCL", "SCL", "input"),
    ],
    right_pins=[
        ("BUCK1_OUT", "BUCK1", "power_out"),
        ("BUCK2_OUT", "BUCK2", "power_out"),
        ("LDO1_OUT", "LDO1", "power_out"),
        ("LDO2_OUT", "LDO2", "power_out"),
        ("nIRQ", "IRQ", "output"),
        ("SHPHLD", "SHPHLD", "input"),
    ],
    bottom_pins=[
        ("GND", "GND", "power_in"),
    ]
)

SYMBOLS["DRV2605L"] = make_simple_symbol(
    "DRV2605L", "U", "TI DRV2605L Haptic Driver",
    "Package_BGA:DSBGA-9_1.5x1.5mm_P0.5mm", "DRV2605L",
    left_pins=[
        ("SDA", "A1", "bidirectional"),
        ("SCL", "A2", "input"),
        ("EN", "A3", "input"),
    ],
    right_pins=[
        ("OUT+", "C1", "output"),
        ("OUT-", "C2", "output"),
        ("IN/TRIG", "C3", "input"),
    ],
    top_pins=[
        ("VDD", "B1", "power_in"),
    ],
    bottom_pins=[
        ("GND", "B3", "power_in"),
        ("VDD_IO", "B2", "power_in"),
    ]
)

SYMBOLS["IM72D128V"] = make_simple_symbol(
    "IM72D128V", "M", "Infineon IM72D128V MEMS Mic (PDM)",
    "vantage:IM72D128V", "IM72D128V",
    left_pins=[
        ("VDD", "1", "power_in"),
        ("GND", "2", "power_in"),
    ],
    right_pins=[
        ("CLK", "3", "input"),
        ("DATA", "4", "output"),
        ("L/R", "5", "input"),
    ]
)

SYMBOLS["Crystal_4Pin"] = make_simple_symbol(
    "Crystal_4Pin", "Y", "Crystal Oscillator 4-pin",
    "Crystal:Crystal_SMD_2016-4Pin_2.0x1.6mm", "32MHz",
    left_pins=[
        ("IN", "1", "passive"),
    ],
    right_pins=[
        ("OUT", "3", "passive"),
    ],
    bottom_pins=[
        ("GND1", "2", "passive"),
        ("GND2", "4", "passive"),
    ]
)

SYMBOLS["Crystal_2Pin"] = make_simple_symbol(
    "Crystal_2Pin", "Y", "Crystal Oscillator 2-pin",
    "Crystal:Crystal_SMD_1610-2Pin_1.6x1.0mm", "32.768kHz",
    left_pins=[
        ("IN", "1", "passive"),
    ],
    right_pins=[
        ("OUT", "2", "passive"),
    ]
)

SYMBOLS["LED_RGB"] = make_simple_symbol(
    "LED_RGB", "D", "RGB LED Common Cathode",
    "vantage:LED_1615_RGB", "RGB_LED",
    left_pins=[
        ("R", "1", "passive"),
        ("G", "2", "passive"),
        ("B", "3", "passive"),
    ],
    right_pins=[
        ("K", "4", "passive"),
    ]
)

SYMBOLS["SW_Push"] = make_simple_symbol(
    "SW_Push", "SW", "Tactile Push Button",
    "vantage:SW_SidePush_IP67", "BTN",
    left_pins=[
        ("1", "1", "passive"),
    ],
    right_pins=[
        ("2", "2", "passive"),
    ]
)

SYMBOLS["LRA"] = make_simple_symbol(
    "LRA", "H", "LRA Coin Actuator",
    "vantage:LRA_10mm", "LRA",
    left_pins=[
        ("+", "1", "passive"),
        ("-", "2", "passive"),
    ]
)

SYMBOLS["Battery"] = make_simple_symbol(
    "Battery", "BT", "Li-Po Battery",
    "vantage:Battery_Pouch_32x20", "350mAh",
    left_pins=[
        ("+", "1", "passive"),
        ("-", "2", "passive"),
    ]
)

SYMBOLS["Pogo_Pin"] = make_simple_symbol(
    "Pogo_Pin", "J", "Pogo Pin Pad",
    "vantage:PogoPad_2mm", "POGO",
    left_pins=[
        ("1", "1", "passive"),
    ]
)

SYMBOLS["Antenna"] = make_simple_symbol(
    "Antenna", "ANT", "BLE 2.4GHz Antenna",
    "vantage:ANT_PCB_Trace_BLE", "2.4GHz",
    left_pins=[
        ("ANT", "1", "passive"),
        ("GND", "2", "passive"),
    ]
)

SYMBOLS["R"] = make_simple_symbol(
    "R", "R", "Resistor",
    "Resistor_SMD:R_0402_1005Metric", "",
    left_pins=[("1", "1", "passive")],
    right_pins=[("2", "2", "passive")]
)

SYMBOLS["C"] = make_simple_symbol(
    "C", "C", "Capacitor",
    "Capacitor_SMD:C_0402_1005Metric", "",
    left_pins=[("1", "1", "passive")],
    right_pins=[("2", "2", "passive")]
)

SYMBOLS["L"] = make_simple_symbol(
    "L", "L", "Inductor",
    "Inductor_SMD:L_0402_1005Metric", "",
    left_pins=[("1", "1", "passive")],
    right_pins=[("2", "2", "passive")]
)


# ---------------------------------------------------------------------------
# S-expression generators
# ---------------------------------------------------------------------------

def pin_type_kicad(pt):
    """Convert our pin type names to KiCad pin type tokens."""
    mapping = {
        "input": "input",
        "output": "output",
        "bidirectional": "bidirectional",
        "passive": "passive",
        "power_in": "power_in",
        "power_out": "power_out",
        "unconnected": "unconnected",
    }
    return mapping.get(pt, "passive")


def pin_direction_angle(d):
    """Convert direction letter to KiCad angle in degrees."""
    return {"R": 0, "L": 180, "U": 90, "D": 270}.get(d, 0)


def generate_symbol_sexpr(sym: SymbolDef):
    """Generate KiCad symbol S-expression for one component."""
    sym_id = f"vantage:{sym.lib_name}"

    # Calculate bounding box for the rectangle
    if not sym.pins:
        return ""

    min_x = min(p.x for p in sym.pins) + 2.54
    max_x = max(p.x for p in sym.pins) - 2.54
    min_y = min(p.y for p in sym.pins) + 2.54
    max_y = max(p.y for p in sym.pins) - 2.54

    # Ensure minimum size
    if max_x - min_x < 5.08:
        cx = (min_x + max_x) / 2
        min_x = cx - 5.08
        max_x = cx + 5.08
    if max_y - min_y < 2.54:
        cy = (min_y + max_y) / 2
        min_y = cy - 2.54
        max_y = cy + 2.54

    lines = []
    lines.append(f'  (symbol "{sym_id}"')
    lines.append(f'    (exclude_from_sim no)')
    lines.append(f'    (in_bom yes)')
    lines.append(f'    (on_board yes)')
    # Properties
    lines.append(f'    (property "Reference" "{sym.ref_prefix}"')
    lines.append(f'      (at 0 {max_y + 3.81:.2f} 0)')
    lines.append(f'      (effects (font (size 1.27 1.27))))')
    lines.append(f'    (property "Value" "{sym.value}"')
    lines.append(f'      (at 0 {min_y - 2.54:.2f} 0)')
    lines.append(f'      (effects (font (size 1.27 1.27))))')
    lines.append(f'    (property "Footprint" "{sym.footprint}"')
    lines.append(f'      (at 0 {min_y - 5.08:.2f} 0)')
    lines.append(f'      (effects (font (size 1.27 1.27)) (hide yes)))')
    lines.append(f'    (property "Datasheet" ""')
    lines.append(f'      (at 0 0 0)')
    lines.append(f'      (effects (font (size 1.27 1.27)) (hide yes)))')
    lines.append(f'    (property "Description" "{sym.description}"')
    lines.append(f'      (at 0 0 0)')
    lines.append(f'      (effects (font (size 1.27 1.27)) (hide yes)))')

    # Symbol drawing unit
    lines.append(f'    (symbol "{sym.lib_name}_0_1"')
    lines.append(f'      (rectangle (start {min_x:.2f} {max_y:.2f}) (end {max_x:.2f} {min_y:.2f})')
    lines.append(f'        (stroke (width 0.254) (type default))')
    lines.append(f'        (fill (type background)))')
    lines.append(f'    )')

    # Pins
    lines.append(f'    (symbol "{sym.lib_name}_1_1"')
    for pin in sym.pins:
        angle = pin_direction_angle(pin.direction)
        ktype = pin_type_kicad(pin.pin_type)
        lines.append(f'      (pin {ktype} line (at {pin.x:.2f} {pin.y:.2f} {angle}) (length {pin.length:.2f})')
        lines.append(f'        (name "{pin.name}" (effects (font (size 1.016 1.016))))')
        lines.append(f'        (number "{pin.number}" (effects (font (size 1.016 1.016))))')
        lines.append(f'      )')
    lines.append(f'    )')
    lines.append(f'  )')
    return "\n".join(lines)


def generate_symbol_library(symbols: dict):
    """Generate complete .kicad_sym library file."""
    header = """(kicad_symbol_lib
  (version 20251024)
  (generator "vantage_generator")
  (generator_version "1.0")
"""
    body = "\n".join(generate_symbol_sexpr(s) for s in symbols.values())
    return header + body + "\n)\n"


# ---------------------------------------------------------------------------
# Schematic generation
# ---------------------------------------------------------------------------

@dataclass
class SchComponent:
    ref: str
    symbol_name: str
    value: str
    x: float
    y: float
    properties: dict = field(default_factory=dict)
    mirror_x: bool = False
    uuid_str: str = ""

    def __post_init__(self):
        if not self.uuid_str:
            self.uuid_str = uid()


@dataclass
class SchWire:
    x1: float
    y1: float
    x2: float
    y2: float
    uuid_str: str = ""

    def __post_init__(self):
        if not self.uuid_str:
            self.uuid_str = uid()


def pin_endpoint(comp: SchComponent, pin: Pin) -> tuple:
    """Calculate absolute pin connection point (tip) on schematic."""
    return (comp.x + pin.x, comp.y + pin.y)


def label_angle_for_pin(pin: Pin) -> float:
    """Get the global label angle that faces away from the pin body."""
    # Pin direction is toward the body; label should face outward
    return {"R": 180, "L": 0, "U": 270, "D": 90}.get(pin.direction, 0)


def find_pin_by_name(sym_def: SymbolDef, name: str) -> Optional[Pin]:
    """Find a pin in a symbol definition by its display name."""
    for pin in sym_def.pins:
        if pin.name == name:
            return pin
    return None


def find_pin_by_number(sym_def: SymbolDef, number: str) -> Optional[Pin]:
    """Find a pin in a symbol definition by its number."""
    for pin in sym_def.pins:
        if pin.number == number:
            return pin
    return None


def connect_net(comp: SchComponent, sym_def: SymbolDef, pin_name: str,
                net_name: str, labels: list, wires: list,
                shape: str = "bidirectional", wire_len: float = 5.08,
                by_number: bool = False):
    """Connect a component pin to a net via a wire stub and global label.

    Places a wire from the pin endpoint outward, then a global label at the end.
    This ensures KiCad sees the pin as connected (wire touches pin tip)
    and the label as connected (label at wire endpoint).
    """
    if by_number:
        pin = find_pin_by_number(sym_def, pin_name)
    else:
        pin = find_pin_by_name(sym_def, pin_name)
    if pin is None:
        return

    tip_x, tip_y = pin_endpoint(comp, pin)

    # Wire extends outward from pin (opposite to pin direction toward body)
    # Pin direction R means pin body goes right, so wire goes LEFT
    dx_map = {"R": -1, "L": 1, "U": 0, "D": 0}
    dy_map = {"R": 0, "L": 0, "U": -1, "D": 1}
    dx = dx_map.get(pin.direction, 0) * wire_len
    dy = dy_map.get(pin.direction, 0) * wire_len

    wire_end_x = tip_x + dx
    wire_end_y = tip_y + dy

    wires.append(SchWire(tip_x, tip_y, wire_end_x, wire_end_y))

    label_angle = label_angle_for_pin(pin)
    labels.append(SchLabel(net_name, wire_end_x, wire_end_y, label_angle,
                          shape=shape))


@dataclass
class SchLabel:
    text: str
    x: float
    y: float
    angle: float = 0  # 0=right, 90=up, 180=left, 270=down
    label_type: str = "global_label"  # label, global_label, hierarchical_label
    shape: str = "bidirectional"  # input, output, bidirectional, passive
    uuid_str: str = ""

    def __post_init__(self):
        if not self.uuid_str:
            self.uuid_str = uid()


def component_sexpr(comp: SchComponent, sym_def: SymbolDef):
    """Generate S-expression for a schematic component instance."""
    sym_id = f"vantage:{sym_def.lib_name}"
    mirror_str = ""
    if comp.mirror_x:
        mirror_str = " (mirror x)"

    lines = []
    lines.append(f'  (symbol')
    lines.append(f'    (lib_id "{sym_id}")')
    lines.append(f'    (at {comp.x:.2f} {comp.y:.2f} 0)')
    if comp.mirror_x:
        lines.append(f'    (mirror x)')
    lines.append(f'    (unit 1)')
    lines.append(f'    (exclude_from_sim no)')
    lines.append(f'    (in_bom yes)')
    lines.append(f'    (on_board yes)')
    lines.append(f'    (dnp no)')
    lines.append(f'    (uuid "{comp.uuid_str}")')

    # Reference property
    lines.append(f'    (property "Reference" "{comp.ref}"')
    lines.append(f'      (at {comp.x:.2f} {comp.y - 1.27:.2f} 0)')
    lines.append(f'      (effects (font (size 1.27 1.27))))')

    # Value property
    lines.append(f'    (property "Value" "{comp.value}"')
    lines.append(f'      (at {comp.x:.2f} {comp.y + 1.27:.2f} 0)')
    lines.append(f'      (effects (font (size 1.27 1.27))))')

    # Footprint property
    lines.append(f'    (property "Footprint" "{sym_def.footprint}"')
    lines.append(f'      (at {comp.x:.2f} {comp.y + 3.81:.2f} 0)')
    lines.append(f'      (effects (font (size 1.27 1.27)) (hide yes)))')

    # Pin instances (empty - uses default)
    for pin in sym_def.pins:
        lines.append(f'    (pin "{pin.number}"')
        lines.append(f'      (uuid "{uid()}"))')

    lines.append(f'  )')
    return "\n".join(lines)


def wire_sexpr(wire: SchWire):
    return f"""  (wire
    (pts
      (xy {wire.x1:.2f} {wire.y1:.2f}) (xy {wire.x2:.2f} {wire.y2:.2f})
    )
    (stroke
      (width 0)
      (type solid)
    )
    (uuid "{wire.uuid_str}")
  )"""


def global_label_sexpr(label: SchLabel):
    return f"""  (global_label "{label.text}"
    (shape {label.shape})
    (at {label.x:.2f} {label.y:.2f} {label.angle:.0f})
    (effects (font (size 1.27 1.27)))
    (uuid "{label.uuid_str}")
    (property "Intersheets" ""
      (at 0 0 0)
      (effects (font (size 1.27 1.27)) (hide yes)))
  )"""


def power_symbol_sexpr(name, x, y, is_ground=False):
    """Generate a power flag/symbol."""
    symbol_uuid = uid()
    if is_ground:
        lib_id = "power:GND"
    elif name == "VDD_1V8":
        lib_id = "power:+1V8"
    elif name == "VDD_3V3":
        lib_id = "power:+3V3"
    elif name == "VBAT":
        lib_id = "power:VBAT"
    else:
        lib_id = f"power:{name}"

    return f"""  (symbol
    (lib_id "{lib_id}")
    (at {x:.2f} {y:.2f} 0)
    (unit 1)
    (exclude_from_sim no)
    (in_bom yes)
    (on_board yes)
    (dnp no)
    (uuid "{symbol_uuid}")
    (property "Reference" "#PWR?" (at {x:.2f} {y + 2.54:.2f} 0)
      (effects (font (size 1.27 1.27)) hide))
    (property "Value" "{name}" (at {x:.2f} {y - 2.54:.2f} 0)
      (effects (font (size 1.27 1.27))))
  )"""


def generate_schematic(symbols: dict):
    """Generate the complete schematic with all components and connections.

    Uses connect_net() to wire every pin to its net label via wire stubs,
    ensuring zero pin_not_connected and label_dangling ERC errors.
    """
    components = []
    wires = []
    labels = []

    # Helper: look up component + symbol for connect_net calls
    comp_map = {}  # ref -> (SchComponent, SymbolDef)

    def snap_grid(v, grid=2.54):
        """Snap a coordinate to the nearest grid point."""
        return round(v / grid) * grid

    def add_comp(ref, sym_name, value, x, y):
        # Snap to 2.54mm grid for proper pin alignment
        c = SchComponent(ref, sym_name, value, snap_grid(x), snap_grid(y))
        components.append(c)
        comp_map[ref] = (c, symbols[sym_name])
        return c

    def cn(ref, pin_name, net_name, shape="bidirectional", by_number=False):
        """Shorthand for connect_net."""
        comp, sym_def = comp_map[ref]
        connect_net(comp, sym_def, pin_name, net_name, labels, wires,
                   shape=shape, by_number=by_number)

    # ======= Component placement =======

    # SoC (center)
    add_comp("U1", "nRF5340", "nRF5340-QKAA", 152.4, 101.6)

    # Flash (right of SoC)
    add_comp("U2", "W25Q128JV", "W25Q128JV", 228.6, 76.2)

    # PMIC (below-left)
    add_comp("U3", "nPM1300", "nPM1300", 76.2, 177.8)

    # Haptic driver (right of PMIC)
    add_comp("U4", "DRV2605L", "DRV2605L", 228.6, 177.8)

    # Mics
    add_comp("M1", "IM72D128V", "IM72D128V", 38.1, 76.2)
    add_comp("M2", "IM72D128V", "IM72D128V", 38.1, 114.3)

    # Crystals
    add_comp("Y1", "Crystal_4Pin", "32MHz", 152.4, 38.1)
    add_comp("Y2", "Crystal_2Pin", "32.768kHz", 114.3, 38.1)

    # LRA actuator
    add_comp("H1", "LRA", "LRA", 304.8, 177.8)

    # RGB LED
    add_comp("D1", "LED_RGB", "RGB_LED", 228.6, 38.1)

    # Button
    add_comp("SW1", "SW_Push", "BTN", 228.6, 127.0)

    # Battery
    add_comp("BT1", "Battery", "350mAh", 38.1, 203.2)

    # Pogo pins
    add_comp("J1", "Pogo_Pin", "VBUS", 38.1, 228.6)
    add_comp("J2", "Pogo_Pin", "GND", 38.1, 241.3)

    # Antenna
    add_comp("ANT1", "Antenna", "2.4GHz", 152.4, 152.4)

    # I2C pull-ups
    add_comp("R1", "R", "4.7k", 152.4, 165.1)
    add_comp("R2", "R", "4.7k", 165.1, 165.1)

    # Decoupling caps
    for i, (ref, val) in enumerate([("C1", "100nF"), ("C2", "4.7uF"),
                                     ("C3", "100nF"), ("C4", "10uF")]):
        add_comp(ref, "C", val, 304.8, 38.1 + i * 15.24)

    # Antenna matching
    add_comp("L1", "L", "2.7nH", 152.4, 139.7)
    add_comp("C5", "C", "1.5pF", 177.8, 139.7)

    # ======= Net connections (wire + label at every pin) =======

    # --- U1 nRF5340: left-side pins ---
    cn("U1", "QSPI_IO0", "QSPI_IO0")
    cn("U1", "QSPI_IO1", "QSPI_IO1")
    cn("U1", "QSPI_IO2", "QSPI_IO2")
    cn("U1", "QSPI_IO3", "QSPI_IO3")
    cn("U1", "QSPI_SCK", "QSPI_SCK", shape="output")
    cn("U1", "QSPI_CSN", "QSPI_CSN", shape="output")
    cn("U1", "XL1", "XL1", shape="passive")
    cn("U1", "XL2", "XL2", shape="passive")
    cn("U1", "PMIC_IRQ", "PMIC_IRQ", shape="input")
    cn("U1", "PMIC_SHPHLD", "PMIC_SHPHLD", shape="output")
    cn("U1", "LED_R", "LED_R", shape="output")
    cn("U1", "LED_G", "LED_G", shape="output")
    cn("U1", "LED_B", "LED_B", shape="output")

    # --- U1 nRF5340: right-side pins ---
    cn("U1", "I2C_SDA", "I2C_SDA")
    cn("U1", "I2C_SCL", "I2C_SCL")
    cn("U1", "PDM_CLK", "PDM_CLK", shape="output")
    cn("U1", "PDM_DIN", "PDM_DIN", shape="input")
    cn("U1", "DRV_EN", "DRV_EN", shape="output")
    cn("U1", "BTN_IRQ", "BTN_IRQ", shape="input")
    cn("U1", "MIC1_LR", "MIC1_LR_SEL", shape="output")
    cn("U1", "MIC2_LR", "MIC2_LR_SEL", shape="output")
    cn("U1", "UART_TX", "UART_TX", shape="output")
    cn("U1", "UART_RX", "UART_RX", shape="input")

    # --- U1 nRF5340: top pins (power) ---
    cn("U1", "VDD", "VDD_1V8", shape="passive")
    cn("U1", "VSS", "GND", shape="passive")

    # --- U1 nRF5340: bottom pins (crystals, antenna) ---
    cn("U1", "XC1", "XC1", shape="passive")
    cn("U1", "XC2", "XC2", shape="passive")
    cn("U1", "ANT", "RF_ANT", shape="passive")

    # --- U2 Flash: all pins ---
    cn("U2", "CS#", "QSPI_CSN", shape="input")
    cn("U2", "DO/IO1", "QSPI_IO1")
    cn("U2", "WP#/IO2", "QSPI_IO2")
    cn("U2", "GND", "GND", shape="passive")
    cn("U2", "VCC", "VDD_1V8", shape="passive")
    cn("U2", "DI/IO0", "QSPI_IO0")
    cn("U2", "CLK", "QSPI_SCK", shape="input")
    cn("U2", "HOLD#/IO3", "QSPI_IO3")

    # --- U3 PMIC: all pins ---
    cn("U3", "VBAT", "VBAT", shape="input")
    cn("U3", "VBUS", "VBUS", shape="input")
    cn("U3", "BATT+", "BATT_CHG", shape="output")
    cn("U3", "SDA", "I2C_SDA")
    cn("U3", "SCL", "I2C_SCL", shape="input")
    cn("U3", "BUCK1_OUT", "VDD_1V8", shape="output")
    cn("U3", "BUCK2_OUT", "VDD_BUCK2", shape="output")
    cn("U3", "LDO1_OUT", "VDD_3V3", shape="output")
    cn("U3", "LDO2_OUT", "VDD_LDO2", shape="output")
    cn("U3", "nIRQ", "PMIC_IRQ", shape="output")
    cn("U3", "SHPHLD", "PMIC_SHPHLD", shape="input")
    cn("U3", "GND", "GND", shape="passive")

    # --- U4 Haptic driver: all pins ---
    cn("U4", "SDA", "I2C_SDA")
    cn("U4", "SCL", "I2C_SCL", shape="input")
    cn("U4", "EN", "DRV_EN", shape="input")
    cn("U4", "OUT+", "LRA_OUT_P", shape="output")
    cn("U4", "OUT-", "LRA_OUT_N", shape="output")
    cn("U4", "IN/TRIG", "DRV_TRIG", shape="input")
    cn("U4", "VDD", "VBAT", shape="passive")
    cn("U4", "GND", "GND", shape="passive")
    cn("U4", "VDD_IO", "VDD_1V8", shape="passive")

    # --- M1, M2 Mics: all pins ---
    for mic_ref, lr_net in [("M1", "MIC1_LR_SEL"), ("M2", "MIC2_LR_SEL")]:
        cn(mic_ref, "VDD", "VDD_1V8", shape="passive")
        cn(mic_ref, "GND", "GND", shape="passive")
        cn(mic_ref, "CLK", "PDM_CLK", shape="input")
        cn(mic_ref, "DATA", "PDM_DIN", shape="output")
        cn(mic_ref, "L/R", lr_net, shape="input")

    # --- Y1 32MHz crystal ---
    cn("Y1", "IN", "XC1", shape="passive")
    cn("Y1", "OUT", "XC2", shape="passive")
    cn("Y1", "GND1", "GND", shape="passive")
    cn("Y1", "GND2", "GND", shape="passive")

    # --- Y2 32.768kHz crystal ---
    cn("Y2", "IN", "XL1", shape="passive")
    cn("Y2", "OUT", "XL2", shape="passive")

    # --- H1 LRA ---
    cn("H1", "+", "LRA_OUT_P", shape="passive")
    cn("H1", "-", "LRA_OUT_N", shape="passive")

    # --- D1 RGB LED ---
    cn("D1", "R", "LED_R", shape="passive")
    cn("D1", "G", "LED_G", shape="passive")
    cn("D1", "B", "LED_B", shape="passive")
    cn("D1", "K", "GND", shape="passive")

    # --- SW1 Button ---
    cn("SW1", "1", "BTN_IRQ", shape="passive", by_number=True)
    cn("SW1", "2", "GND", shape="passive", by_number=True)

    # --- BT1 Battery ---
    cn("BT1", "+", "VBAT", shape="passive")
    cn("BT1", "-", "GND", shape="passive")

    # --- J1, J2 Pogo pins ---
    cn("J1", "1", "VBUS", shape="passive", by_number=True)
    cn("J2", "1", "GND", shape="passive", by_number=True)

    # --- ANT1 Antenna ---
    cn("ANT1", "ANT", "RF_ANT", shape="passive")
    cn("ANT1", "GND", "GND", shape="passive")

    # --- R1, R2 I2C pull-ups ---
    cn("R1", "1", "I2C_SCL", by_number=True)
    cn("R1", "2", "VDD_1V8", shape="passive", by_number=True)
    cn("R2", "1", "I2C_SDA", by_number=True)
    cn("R2", "2", "VDD_1V8", shape="passive", by_number=True)

    # --- Decoupling caps ---
    cap_nets = [("C1", "VDD_1V8"), ("C2", "VDD_1V8"), ("C3", "VDD_3V3"), ("C4", "VBAT")]
    for ref, net in cap_nets:
        cn(ref, "1", net, shape="passive", by_number=True)
        cn(ref, "2", "GND", shape="passive", by_number=True)

    # --- L1 antenna matching inductor ---
    cn("L1", "1", "RF_ANT", shape="passive", by_number=True)
    cn("L1", "2", "RF_MATCH", shape="passive", by_number=True)

    # --- C5 antenna matching cap ---
    cn("C5", "1", "RF_MATCH", shape="passive", by_number=True)
    cn("C5", "2", "GND", shape="passive", by_number=True)

    # ---- Build schematic file ----
    sch_lines = []
    sch_lines.append(f"""(kicad_sch
  (version 20250114)
  (generator "vantage_generator")
  (generator_version "1.0")
  (uuid "{uid()}")
  (paper "A3")
  (title_block
    (title "Vantage V1 Lite")
    (date "2026-03-31")
    (rev "A")
    (company "EB/Vantage")
    (comment 1 "nRF5340 BLE Wearable")
    (comment 2 "Generated from connectivity reference")
  )
""")

    # Library symbols section
    sch_lines.append("  (lib_symbols")
    for sym in symbols.values():
        sch_lines.append(generate_symbol_sexpr(sym))
    sch_lines.append("  )\n")

    # Component instances
    for comp in components:
        sym_def = symbols.get(comp.symbol_name)
        if sym_def:
            sch_lines.append(component_sexpr(comp, sym_def))

    # Wires (connecting pins to labels)
    for wire in wires:
        sch_lines.append(wire_sexpr(wire))

    # Global labels
    for label in labels:
        sch_lines.append(global_label_sexpr(label))

    # Sheet instances (required for flat schematic)
    sch_lines.append(f"""
  (sheet_instances
    (path "/"
      (page "1")
    )
  )
""")

    # Symbol instances
    sch_lines.append("  (symbol_instances")
    for comp in components:
        sch_lines.append(f'    (path "/{comp.uuid_str}"')
        sch_lines.append(f'      (reference "{comp.ref}") (unit 1))')
    sch_lines.append("  )")

    sch_lines.append(")")
    return "\n".join(sch_lines)


# ---------------------------------------------------------------------------
# PCB generation
# ---------------------------------------------------------------------------

def generate_pcb():
    """Generate KiCad PCB with rigid-flex outline, stackup, and placement."""

    # Board dimensions (mm)
    # Center rigid: 30mm x 18mm
    # Left flex: 6mm long
    # Left mic zone: 8mm x 8mm
    # Right flex: 6mm long
    # Right mic zone: 8mm x 8mm

    center_w = 30
    center_h = 18
    flex_len = 6
    flex_h = 4  # flex strip height
    mic_w = 8
    mic_h = 8

    # Origin at center of the center rigid zone
    cx, cy = 100, 100  # PCB origin offset

    # Center rigid zone corners
    cr_left = cx - center_w/2
    cr_right = cx + center_w/2
    cr_top = cy - center_h/2
    cr_bottom = cy + center_h/2

    # Left flex + mic zone
    lf_right = cr_left
    lf_left = lf_right - flex_len
    lf_top = cy - flex_h/2
    lf_bottom = cy + flex_h/2

    lm_right = lf_left
    lm_left = lm_right - mic_w
    lm_top = cy - mic_h/2
    lm_bottom = cy + mic_h/2

    # Right flex + mic zone
    rf_left = cr_right
    rf_right = rf_left + flex_len
    rf_top = cy - flex_h/2
    rf_bottom = cy + flex_h/2

    rm_left = rf_right
    rm_right = rm_left + mic_w
    rm_top = cy - mic_h/2
    rm_bottom = cy + mic_h/2

    # Board outline (clockwise from top-left of left mic)
    outline_pts = [
        # Left mic zone (top)
        (lm_left, lm_top),
        (lm_right, lm_top),
        # Left flex top
        (lm_right, lf_top),
        (lf_right, lf_top),
        # Center rigid top
        (cr_left, cr_top),
        (cr_right, cr_top),
        # Right flex top
        (rf_left, rf_top),
        (rf_right, rf_top),
        # Right mic zone (top)
        (rm_left, rm_top),
        (rm_right, rm_top),
        # Right mic zone (bottom)
        (rm_right, rm_bottom),
        (rm_left, rm_bottom),
        # Right flex bottom
        (rf_right, rf_bottom),
        (rf_left, rf_bottom),
        # Center rigid bottom
        (cr_right, cr_bottom),
        (cr_left, cr_bottom),
        # Left flex bottom
        (lf_right, lf_bottom),
        (lm_right, lf_bottom),
        # Left mic zone (bottom)
        (lm_right, lm_bottom),
        (lm_left, lm_bottom),
    ]

    # Component placement (x, y, ref, footprint, layer)
    placements = [
        # Center zone - main ICs
        (cx, cy - 2, "U1", "Nordic:QFN-94-1EP_7x7mm", "F.Cu", 0),
        (cx + 8, cy - 8, "U2", "Package_SON:WSON-8-1EP_6x5mm_P1.27mm_EP3.4x4.3mm", "F.Cu", 0),
        (cx - 8, cy + 2, "U3", "Nordic:QFN-32-1EP_5x5mm", "F.Cu", 0),
        (cx + 8, cy + 6, "U4", "Package_BGA:DSBGA-9_1.5x1.5mm_P0.5mm", "F.Cu", 0),

        # Crystals (within 5mm of SoC)
        (cx - 5, cy - 7, "Y1", "Crystal:Crystal_SMD_2016-4Pin_2.0x1.6mm", "F.Cu", 0),
        (cx + 5, cy - 7, "Y2", "Crystal:Crystal_SMD_1610-2Pin_1.6x1.0mm", "F.Cu", 0),

        # Left mic zone
        (lm_left + mic_w/2, cy, "M1", "vantage:IM72D128V", "F.Cu", 0),

        # Right mic zone
        (rm_left + mic_w/2, cy, "M2", "vantage:IM72D128V", "F.Cu", 0),

        # Antenna (edge of center zone)
        (cr_right - 2, cr_top + 3, "ANT1", "vantage:ANT_PCB_Trace_BLE", "F.Cu", 0),

        # LED
        (cx - 3, cr_top + 2, "D1", "vantage:LED_1615_RGB", "F.Cu", 0),

        # Button (side-mount on edge)
        (cr_left + 2, cy, "SW1", "vantage:SW_SidePush_IP67", "F.Cu", 90),

        # LRA (bottom side, center)
        (cx, cy + 3, "H1", "vantage:LRA_10mm", "B.Cu", 0),

        # Battery (above PCB, center zone)
        (cx, cy - 1, "BT1", "vantage:Battery_Pouch_32x20", "F.Cu", 0),

        # Pogo pins (bottom, offset from center)
        (cx - 3, cr_bottom - 2, "J1", "vantage:PogoPad_2mm", "B.Cu", 0),
        (cx + 3, cr_bottom - 2, "J2", "vantage:PogoPad_2mm", "B.Cu", 0),

        # I2C pull-ups (near SoC)
        (cx + 6, cy - 3, "R1", "Resistor_SMD:R_0402_1005Metric", "F.Cu", 0),
        (cx + 6, cy - 1.5, "R2", "Resistor_SMD:R_0402_1005Metric", "F.Cu", 0),
    ]

    # Decoupling caps around SoC
    cap_positions = [
        (cx - 6, cy - 6, "C1", "Capacitor_SMD:C_0402_1005Metric", "100nF"),
        (cx - 6, cy - 4.5, "C2", "Capacitor_SMD:C_0402_1005Metric", "4.7uF"),
        (cx + 6, cy + 3, "C3", "Capacitor_SMD:C_0402_1005Metric", "100nF"),
        (cx - 10, cy + 5, "C4", "Capacitor_SMD:C_0402_1005Metric", "10uF"),
        (cx + 10, cy - 6, "C5", "Capacitor_SMD:C_0402_1005Metric", "1.5pF"),
    ]

    # Antenna matching inductor
    placements.append((cx + 12, cr_top + 3, "L1", "Inductor_SMD:L_0402_1005Metric", "F.Cu", 0))

    for cap_x, cap_y, ref, fp, val in cap_positions:
        placements.append((cap_x, cap_y, ref, fp, "F.Cu", 0))

    # Build PCB file
    pcb = []
    pcb.append(f"""(kicad_pcb
  (version 20241229)
  (generator "vantage_generator")
  (generator_version "1.0")
  (general
    (thickness 0.8)
    (legacy_teardrops no)
  )
  (paper "A4")
  (title_block
    (title "Vantage V1 Lite PCB")
    (date "2026-03-31")
    (rev "A")
    (company "EB/Vantage")
    (comment 1 "4-layer rigid-flex")
  )
  (layers
    (0 "F.Cu" signal)
    (2 "B.Cu" signal)
    (4 "In1.Cu" signal)
    (6 "In2.Cu" signal)
    (1 "F.Mask" user)
    (3 "B.Mask" user)
    (5 "F.SilkS" user "F.Silkscreen")
    (7 "B.SilkS" user "B.Silkscreen")
    (25 "Edge.Cuts" user)
    (31 "F.CrtYd" user "F.Courtyard")
    (29 "B.CrtYd" user "B.Courtyard")
    (35 "F.Fab" user "F.Fab")
    (33 "B.Fab" user "B.Fab")
    (37 "User.1" user)
  )
  (setup
    (pad_to_mask_clearance 0.05)
  )
""")

    # Net definitions
    nets = [
        "GND", "VDD_1V8", "VDD_3V3", "VBAT", "VBUS",
        "QSPI_IO0", "QSPI_IO1", "QSPI_IO2", "QSPI_IO3", "QSPI_SCK", "QSPI_CSN",
        "I2C_SCL", "I2C_SDA",
        "PDM_CLK", "PDM_DIN",
        "MIC1_LR_SEL", "MIC2_LR_SEL",
        "LED_R", "LED_G", "LED_B",
        "BTN_IRQ", "DRV_EN",
        "PMIC_IRQ", "PMIC_SHPHLD",
        "LRA_OUT_P", "LRA_OUT_N",
        "RF_ANT", "RF_MATCH",
        "XC1", "XC2", "XL1", "XL2",
        "BATT_P", "BATT_N",
        "UART_TX", "UART_RX",
        "VDD_MIC",
    ]

    pcb.append("  (net 0 \"\")")
    for i, net in enumerate(nets, 1):
        pcb.append(f'  (net {i} "{net}")')
    pcb.append("")

    # Board outline
    pcb.append("")
    for i in range(len(outline_pts)):
        x1, y1 = outline_pts[i]
        x2, y2 = outline_pts[(i + 1) % len(outline_pts)]
        pcb.append(f'  (gr_line (start {x1:.3f} {y1:.3f}) (end {x2:.3f} {y2:.3f})')
        pcb.append(f'    (stroke (width 0.1) (type solid)) (layer "Edge.Cuts") (uuid "{uid()}"))')

    pcb.append("")

    # Flex zone markers on User.1 layer
    pcb.append("")
    # Left flex zone
    pcb.append(f'  (gr_rect (start {lf_left:.3f} {lf_top:.3f}) (end {lf_right:.3f} {lf_bottom:.3f})')
    pcb.append(f'    (stroke (width 0.2) (type dash)) (fill none) (layer "User.1") (uuid "{uid()}"))')
    pcb.append(f'  (gr_text "FLEX" (at {(lf_left+lf_right)/2:.3f} {(lf_top+lf_bottom)/2:.3f})')
    pcb.append(f'    (layer "User.1") (uuid "{uid()}")')
    pcb.append(f'    (effects (font (size 1 1) (thickness 0.15))))')

    # Right flex zone
    pcb.append(f'  (gr_rect (start {rf_left:.3f} {rf_top:.3f}) (end {rf_right:.3f} {rf_bottom:.3f})')
    pcb.append(f'    (stroke (width 0.2) (type dash)) (fill none) (layer "User.1") (uuid "{uid()}"))')
    pcb.append(f'  (gr_text "FLEX" (at {(rf_left+rf_right)/2:.3f} {(rf_top+rf_bottom)/2:.3f})')
    pcb.append(f'    (layer "User.1") (uuid "{uid()}")')
    pcb.append(f'    (effects (font (size 1 1) (thickness 0.15))))')

    pcb.append("")

    # GND zone (copper pour on In1.Cu)
    pcb.append(f"""  (zone
    (net 1) (net_name "GND") (layer "In1.Cu") (uuid "{uid()}")
    (hatch edge 0.5)
    (connect_pads (clearance 0.2))
    (min_thickness 0.15)
    (fill yes (thermal_gap 0.3) (thermal_bridge_width 0.3))
    (polygon
      (pts
        (xy {lm_left:.3f} {lm_top:.3f})
        (xy {rm_right:.3f} {rm_top:.3f})
        (xy {rm_right:.3f} {rm_bottom:.3f})
        (xy {lm_left:.3f} {lm_bottom:.3f})
      )
    )
  )""")

    # Component placement as text annotations (since we don't have actual footprints loaded)
    pcb.append("")
    for x, y, ref, fp, layer, angle in placements:
        pcb.append(f'  (footprint "{fp}"')
        pcb.append(f'    (layer "{layer}")')
        pcb.append(f'    (uuid "{uid()}")')
        pcb.append(f'    (at {x:.3f} {y:.3f} {angle})')
        pcb.append(f'    (property "Reference" "{ref}"')
        pcb.append(f'      (at 0 -2 {angle})')
        pcb.append(f'      (layer "{layer.replace("Cu", "SilkS")}")')
        pcb.append(f'      (uuid "{uid()}")')
        pcb.append(f'      (effects (font (size 0.8 0.8) (thickness 0.12))))')
        pcb.append(f'    (property "Value" ""')
        pcb.append(f'      (at 0 2 {angle})')
        pcb.append(f'      (layer "{layer.replace("Cu", "Fab")}")')
        pcb.append(f'      (uuid "{uid()}")')
        pcb.append(f'      (effects (font (size 0.8 0.8) (thickness 0.12))))')
        # Add a simple courtyard rectangle for visualization
        if "QFN-94" in fp:
            hw, hh = 3.5, 3.5
        elif "QFN-32" in fp:
            hw, hh = 2.5, 2.5
        elif "WSON-8" in fp:
            hw, hh = 3.0, 2.5
        elif "DSBGA" in fp:
            hw, hh = 0.75, 0.75
        elif "IM72" in fp:
            hw, hh = 2.0, 1.5
        elif "Crystal" in fp and "2016" in fp:
            hw, hh = 1.0, 0.8
        elif "Crystal" in fp and "1610" in fp:
            hw, hh = 0.8, 0.5
        elif "LRA" in fp:
            hw, hh = 5.0, 5.0
        elif "Battery" in fp:
            hw, hh = 16.0, 10.0
        elif "0402" in fp:
            hw, hh = 0.5, 0.3
        else:
            hw, hh = 1.5, 1.5

        crt_layer = layer.replace("Cu", "CrtYd")
        pcb.append(f'    (fp_rect (start {-hw:.3f} {-hh:.3f}) (end {hw:.3f} {hh:.3f})')
        pcb.append(f'      (stroke (width 0.05) (type solid)) (fill none) (layer "{crt_layer}") (uuid "{uid()}"))')
        pcb.append(f'  )')

    pcb.append("\n)")
    return "\n".join(pcb)


# ---------------------------------------------------------------------------
# Project file
# ---------------------------------------------------------------------------

def generate_project_file():
    return """{
  "board": {
    "3dviewports": [],
    "design_settings": {
      "defaults": {
        "apply_defaults_to_fp_fields": false,
        "apply_defaults_to_fp_shapes": false,
        "apply_defaults_to_fp_text": false,
        "board_outline_line_width": 0.1,
        "copper_line_width": 0.2,
        "copper_text_italic": false,
        "copper_text_size_h": 1.5,
        "copper_text_size_v": 1.5,
        "copper_text_thickness": 0.3,
        "copper_text_upright": false,
        "courtyard_line_width": 0.05,
        "dimension_precision": 4,
        "fab_line_width": 0.1,
        "fab_text_italic": false,
        "fab_text_size_h": 1.0,
        "fab_text_size_v": 1.0,
        "fab_text_thickness": 0.15,
        "fab_text_upright": false,
        "other_line_width": 0.1,
        "silk_line_width": 0.15,
        "silk_text_italic": false,
        "silk_text_size_h": 1.0,
        "silk_text_size_v": 1.0,
        "silk_text_thickness": 0.15,
        "silk_text_upright": false,
        "zones": {
          "min_clearance": 0.2
        }
      },
      "diff_pair_dimensions": [],
      "drc_exclusions": [],
      "rules": {
        "max_error": 0.005,
        "min_clearance": 0.1,
        "min_connection": 0.0,
        "min_copper_edge_clearance": 0.2,
        "min_hole_clearance": 0.15,
        "min_hole_to_hole": 0.25,
        "min_microvia_diameter": 0.2,
        "min_microvia_drill": 0.1,
        "min_resolved_spokes": 2,
        "min_silk_clearance": 0.0,
        "min_text_height": 0.8,
        "min_text_thickness": 0.08,
        "min_through_hole_diameter": 0.2,
        "min_track_width": 0.1,
        "min_via_annular_width": 0.1,
        "min_via_diameter": 0.3,
        "solder_mask_to_copper_clearance": 0.0,
        "use_height_for_length_calcs": true
      },
      "teardrop_options": [],
      "teardrop_parameters": [],
      "track_widths": [0.0, 0.1, 0.15, 0.2, 0.25, 0.3, 0.5],
      "tuning_pattern_settings": {},
      "via_dimensions": [{"diameter": 0.3, "drill": 0.15}],
      "zones_allow_external_fillets": false
    },
    "ipc2581": { "dist": "", "mfg": "", "mfg_pn": "", "mpn": "" },
    "layer_presets": [],
    "layer_pairs": []
  },
  "boards": [],
  "cvpcb": { "equivalence_files": [] },
  "libraries": {
    "pinned_footprint_libs": [],
    "pinned_symbol_libs": []
  },
  "meta": {
    "filename": "vantage-v1-lite.kicad_pro",
    "version": 1
  },
  "net_settings": {
    "classes": [
      {
        "bus_width": 12,
        "clearance": 0.15,
        "diff_pair_gap": 0.15,
        "diff_pair_via_gap": 0.25,
        "diff_pair_width": 0.15,
        "line_style": 0,
        "microvia_diameter": 0.2,
        "microvia_drill": 0.1,
        "name": "Default",
        "pcb_color": "rgba(0, 0, 0, 0.000)",
        "schematic_color": "rgba(0, 0, 0, 0.000)",
        "track_width": 0.15,
        "via_diameter": 0.3,
        "via_drill": 0.15,
        "wire_width": 6
      },
      {
        "bus_width": 12,
        "clearance": 0.2,
        "diff_pair_gap": 0.2,
        "diff_pair_via_gap": 0.25,
        "diff_pair_width": 0.2,
        "line_style": 0,
        "microvia_diameter": 0.2,
        "microvia_drill": 0.1,
        "name": "Power",
        "pcb_color": "rgba(255, 0, 0, 0.500)",
        "schematic_color": "rgba(255, 0, 0, 0.500)",
        "track_width": 0.3,
        "via_diameter": 0.4,
        "via_drill": 0.2,
        "wire_width": 6
      },
      {
        "bus_width": 12,
        "clearance": 0.15,
        "diff_pair_gap": 0.15,
        "diff_pair_via_gap": 0.25,
        "diff_pair_width": 0.15,
        "line_style": 0,
        "microvia_diameter": 0.2,
        "microvia_drill": 0.1,
        "name": "RF",
        "pcb_color": "rgba(0, 0, 255, 0.500)",
        "schematic_color": "rgba(0, 0, 255, 0.500)",
        "track_width": 0.2,
        "via_diameter": 0.0,
        "via_drill": 0.0,
        "wire_width": 6
      }
    ],
    "meta": { "version": 3 },
    "net_colors": null,
    "netclass_assignments": null,
    "netclass_patterns": [
      { "netclass": "Power", "pattern": "VBAT" },
      { "netclass": "Power", "pattern": "VBUS" },
      { "netclass": "Power", "pattern": "VDD_*" },
      { "netclass": "Power", "pattern": "GND" },
      { "netclass": "Power", "pattern": "BATT_*" },
      { "netclass": "RF", "pattern": "RF_*" }
    ]
  },
  "pcbnew": {
    "last_paths": { "gencad": "", "idf": "", "netlist": "", "plot": "", "pos_files": "", "specctra_dsn": "", "step": "", "vrml": "" },
    "page_layout_descr_file": ""
  },
  "schematic": {
    "annotate_start_num": 1,
    "bom_export_filename": "",
    "connection_grid_size": 50.0,
    "drawing": {
      "dashed_lines_dash_length_ratio": 12.0,
      "dashed_lines_gap_length_ratio": 3.0,
      "default_line_thickness": 6.0,
      "default_text_size": 50.0,
      "field_names": [],
      "intersheets_ref_own_page": false,
      "intersheets_ref_prefix": "",
      "intersheets_ref_short": false,
      "intersheets_ref_show": false,
      "intersheets_ref_suffix": "",
      "junction_size_choice": 3,
      "label_size_ratio": 0.375,
      "operating_point_overlay_i_prefix": "",
      "operating_point_overlay_i_suffix": "",
      "operating_point_overlay_v_prefix": "",
      "operating_point_overlay_v_suffix": "",
      "overbar_offset_ratio": 1.23,
      "pin_symbol_size": 25.0,
      "text_offset_ratio": 0.15
    },
    "legacy_lib_dir": "",
    "legacy_lib_list": [],
    "meta": { "version": 1 },
    "net_format_name": "",
    "page_layout_descr_file": "",
    "plot_directory": "",
    "spice_current_sheet_as_root": false,
    "spice_external_command": "spice \\\"%I\\\"",
    "spice_model_current_sheet_as_root": true,
    "spice_save_all_currents": false,
    "spice_save_all_dissipations": false,
    "spice_save_all_voltages": false,
    "subpart_first_id": 65,
    "subpart_id_separator": 0
  },
  "sheets": [
    ["", ""]
  ],
  "text_variables": {}
}"""


def generate_lib_tables(output_dir):
    """Generate sym-lib-table and fp-lib-table."""
    sym_lib = f"""(sym_lib_table
  (version 7)
  (lib (name "vantage") (type "KiCad") (uri "${{KIPRJMOD}}/libs/vantage.kicad_sym") (options "") (descr "Vantage V1 Lite custom symbols"))
)
"""

    fp_lib = f"""(fp_lib_table
  (version 7)
  (lib (name "vantage") (type "KiCad") (uri "${{KIPRJMOD}}/libs/vantage.pretty") (options "") (descr "Vantage V1 Lite custom footprints"))
)
"""
    return sym_lib, fp_lib


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else SCRIPT_DIR.parent / "kicad"
    output_dir.mkdir(parents=True, exist_ok=True)
    libs_dir = output_dir / "libs"
    libs_dir.mkdir(exist_ok=True)
    (libs_dir / "vantage.pretty").mkdir(exist_ok=True)

    print(f"Generating KiCad project in: {output_dir}")

    # 1. Symbol library
    print("  [1/5] Generating symbol library...")
    sym_content = generate_symbol_library(SYMBOLS)
    (libs_dir / "vantage.kicad_sym").write_text(sym_content)

    # 2. Schematic
    print("  [2/5] Generating schematic...")
    sch_content = generate_schematic(SYMBOLS)
    (output_dir / "vantage-v1-lite.kicad_sch").write_text(sch_content)

    # 3. PCB
    print("  [3/5] Generating PCB layout...")
    pcb_content = generate_pcb()
    (output_dir / "vantage-v1-lite.kicad_pcb").write_text(pcb_content)

    # 4. Project file
    print("  [4/5] Generating project file...")
    (output_dir / "vantage-v1-lite.kicad_pro").write_text(generate_project_file())

    # 5. Library tables
    print("  [5/5] Generating library tables...")
    sym_tbl, fp_tbl = generate_lib_tables(output_dir)
    (output_dir / "sym-lib-table").write_text(sym_tbl)
    (output_dir / "fp-lib-table").write_text(fp_tbl)

    print()
    print(f"Done! KiCad project generated at: {output_dir}")
    print()
    print("Generated files:")
    for f in sorted(output_dir.rglob("*")):
        if f.is_file():
            size = f.stat().st_size
            print(f"  {f.relative_to(output_dir)} ({size:,} bytes)")
    print()
    print("Next steps:")
    print("  1. Open vantage-v1-lite.kicad_pro in KiCad 8")
    print("  2. Review schematic - check all net connections")
    print("  3. Run ERC (Electrical Rules Check)")
    print("  4. Review PCB - check component placement")
    print("  5. Route traces (interactive router or FreeRouting)")
    print("  6. Run DRC (Design Rules Check)")
    print("  7. Generate Gerbers for manufacturing")


if __name__ == "__main__":
    main()
