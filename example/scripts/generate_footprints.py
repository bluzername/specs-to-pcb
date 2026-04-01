#!/usr/bin/env python3
"""
Vantage V1 - Custom Footprint Generator

Generates .kicad_mod footprint files for custom components in the
Vantage project. Outputs to libs/vantage.pretty/ in KiCad 10 format.

Components:
  - IM72D128V        Infineon MEMS Mic (LGA, 4x3mm, bottom sound port)
  - PogoPad_2mm      Pogo pin contact pad (2mm dia, no paste)
  - LRA_10mm         LRA coin actuator mount (10mm, B.Cu)
  - LED_1615_RGB     RGB LED 1615 package (4-pad)
  - SW_SidePush_IP67 Side-mount tactile button (IP67)
  - ANT_PCB_Trace_BLE  PCB trace inverted-F antenna for 2.4GHz BLE
  - Battery_Pouch_32x20  Battery tab connector

Usage:
  python3 generate_footprints.py [output_dir]
  Default output_dir: ../kicad/libs/vantage.pretty/
"""

from __future__ import annotations

import math
import subprocess
import sys
import uuid as uuid_mod
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def uid() -> str:
    """Generate a KiCad-compatible UUID string."""
    return str(uuid_mod.uuid4())


def _f(v: float) -> str:
    """Format a float for KiCad S-expressions, avoiding artifacts like 1.9500000000000002."""
    rounded = round(v, 6)
    # Strip trailing zeros but keep at least one decimal if it's a float
    s = f"{rounded:g}"
    return s


# ---------------------------------------------------------------------------
# S-expression building blocks
# ---------------------------------------------------------------------------

GENERATOR = "vantage_generator"
VERSION = "20260206"
GENERATOR_VERSION = "10.0"

# Line widths (mm)
SILK_WIDTH = 0.12
FAB_WIDTH = 0.1
CRTYD_WIDTH = 0.05

# Font sizes
REF_FONT = (1, 1, 0.15)
VAL_FONT = (1, 1, 0.15)
HIDDEN_FONT = (1.27, 1.27)


def _header(name: str, layer: str = "F.Cu") -> str:
    return (
        f'(footprint "{name}"\n'
        f'\t(version {VERSION})\n'
        f'\t(generator "{GENERATOR}")\n'
        f'\t(generator_version "{GENERATOR_VERSION}")\n'
        f'\t(layer "{layer}")\n'
    )


def _property(
    key: str,
    value: str,
    at: tuple[float, float, float],
    layer: str,
    font: tuple[float, ...],
    hide: bool = False,
) -> str:
    hide_str = "\n\t\t(hide yes)" if hide else ""
    thickness_str = ""
    if len(font) == 3:
        thickness_str = f"\n\t\t\t\t(thickness {_f(font[2])})"
    return (
        f'\t(property "{key}" "{value}"\n'
        f"\t\t(at {_f(at[0])} {_f(at[1])} {_f(at[2])})\n"
        f'\t\t(layer "{layer}"){hide_str}\n'
        f"\t\t(uuid \"{uid()}\")\n"
        f"\t\t(effects\n"
        f"\t\t\t(font\n"
        f"\t\t\t\t(size {_f(font[0])} {_f(font[1])}){thickness_str}\n"
        f"\t\t\t)\n"
        f"\t\t)\n"
        f"\t)\n"
    )


def _standard_properties(
    name: str,
    ref_y: float = -3.0,
    val_y: float = 3.0,
    description: str = "",
    datasheet: str = "",
) -> str:
    """Emit Reference, Value, Datasheet, Description properties."""
    lines = ""
    lines += _property("Reference", "REF**", (0, ref_y, 0), "F.SilkS", REF_FONT)
    lines += _property("Value", name, (0, val_y, 0), "F.Fab", VAL_FONT)
    lines += _property("Datasheet", datasheet, (0, 0, 0), "F.Fab", HIDDEN_FONT, hide=True)
    lines += _property("Description", description, (0, 0, 0), "F.Fab", HIDDEN_FONT, hide=True)
    return lines


def _pad_smd(
    number: str,
    shape: str,
    at: tuple[float, float],
    size: tuple[float, float],
    layers: str = '"F.Cu" "F.Mask" "F.Paste"',
    rotation: float = 0,
) -> str:
    rot_str = f" {_f(rotation)}" if rotation != 0 else ""
    return (
        f'\t(pad "{number}" smd {shape}\n'
        f"\t\t(at {_f(at[0])} {_f(at[1])}{rot_str})\n"
        f"\t\t(size {_f(size[0])} {_f(size[1])})\n"
        f"\t\t(layers {layers})\n"
        f'\t\t(uuid "{uid()}")\n'
        f"\t)\n"
    )


def _pad_smd_no_paste(
    number: str,
    shape: str,
    at: tuple[float, float],
    size: tuple[float, float],
    layers: str = '"F.Cu" "F.Mask"',
) -> str:
    """SMD pad with no paste layer (e.g. pogo contacts, gold pads)."""
    return (
        f'\t(pad "{number}" smd {shape}\n'
        f"\t\t(at {_f(at[0])} {_f(at[1])})\n"
        f"\t\t(size {_f(size[0])} {_f(size[1])})\n"
        f"\t\t(layers {layers})\n"
        f'\t\t(uuid "{uid()}")\n'
        f"\t)\n"
    )


def _pad_npth(
    at: tuple[float, float],
    drill: float,
) -> str:
    """Non-plated through-hole (e.g. acoustic port)."""
    return (
        f'\t(pad "" np_thru_hole circle\n'
        f"\t\t(at {_f(at[0])} {_f(at[1])})\n"
        f"\t\t(size {_f(drill)} {_f(drill)})\n"
        f"\t\t(drill {_f(drill)})\n"
        f'\t\t(layers "*.Cu" "*.Mask")\n'
        f'\t\t(uuid "{uid()}")\n'
        f"\t)\n"
    )


def _pad_thru(
    number: str,
    shape: str,
    at: tuple[float, float],
    size: tuple[float, float],
    drill: float,
) -> str:
    return (
        f'\t(pad "{number}" thru_hole {shape}\n'
        f"\t\t(at {_f(at[0])} {_f(at[1])})\n"
        f"\t\t(size {_f(size[0])} {_f(size[1])})\n"
        f"\t\t(drill {_f(drill)})\n"
        f'\t\t(layers "*.Cu" "*.Mask")\n'
        f"\t\t(remove_unused_layers no)\n"
        f'\t\t(uuid "{uid()}")\n'
        f"\t)\n"
    )


def _fp_line(
    start: tuple[float, float],
    end: tuple[float, float],
    layer: str,
    width: float,
) -> str:
    return (
        f"\t(fp_line\n"
        f"\t\t(start {_f(start[0])} {_f(start[1])})\n"
        f"\t\t(end {_f(end[0])} {_f(end[1])})\n"
        f"\t\t(stroke\n"
        f"\t\t\t(width {_f(width)})\n"
        f"\t\t\t(type solid)\n"
        f"\t\t)\n"
        f'\t\t(layer "{layer}")\n'
        f'\t\t(uuid "{uid()}")\n'
        f"\t)\n"
    )


def _fp_rect(
    start: tuple[float, float],
    end: tuple[float, float],
    layer: str,
    width: float,
) -> str:
    return (
        f"\t(fp_rect\n"
        f"\t\t(start {_f(start[0])} {_f(start[1])})\n"
        f"\t\t(end {_f(end[0])} {_f(end[1])})\n"
        f"\t\t(stroke\n"
        f"\t\t\t(width {_f(width)})\n"
        f"\t\t\t(type solid)\n"
        f"\t\t)\n"
        f"\t\t(fill no)\n"
        f'\t\t(layer "{layer}")\n'
        f'\t\t(uuid "{uid()}")\n'
        f"\t)\n"
    )


def _fp_circle(
    center: tuple[float, float],
    radius: float,
    layer: str,
    width: float,
    fill: str = "no",
) -> str:
    end_x = center[0] + radius
    end_y = center[1]
    return (
        f"\t(fp_circle\n"
        f"\t\t(center {_f(center[0])} {_f(center[1])})\n"
        f"\t\t(end {_f(end_x)} {_f(end_y)})\n"
        f"\t\t(stroke\n"
        f"\t\t\t(width {_f(width)})\n"
        f"\t\t\t(type solid)\n"
        f"\t\t)\n"
        f"\t\t(fill {fill})\n"
        f'\t\t(layer "{layer}")\n'
        f'\t\t(uuid "{uid()}")\n'
        f"\t)\n"
    )


def _fp_arc(
    start: tuple[float, float],
    mid: tuple[float, float],
    end: tuple[float, float],
    layer: str,
    width: float,
) -> str:
    return (
        f"\t(fp_arc\n"
        f"\t\t(start {_f(start[0])} {_f(start[1])})\n"
        f"\t\t(mid {_f(mid[0])} {_f(mid[1])})\n"
        f"\t\t(end {_f(end[0])} {_f(end[1])})\n"
        f"\t\t(stroke\n"
        f"\t\t\t(width {_f(width)})\n"
        f"\t\t\t(type solid)\n"
        f"\t\t)\n"
        f'\t\t(layer "{layer}")\n'
        f'\t\t(uuid "{uid()}")\n'
        f"\t)\n"
    )


def _fp_poly(
    pts: Sequence[tuple[float, float]],
    layer: str,
    width: float = 0,
    fill: str = "solid",
) -> str:
    pts_str = " ".join(f"(xy {_f(x)} {_f(y)})" for x, y in pts)
    return (
        f"\t(fp_poly\n"
        f"\t\t(pts {pts_str})\n"
        f"\t\t(stroke\n"
        f"\t\t\t(width {_f(width)})\n"
        f"\t\t\t(type solid)\n"
        f"\t\t)\n"
        f"\t\t(fill {fill})\n"
        f'\t\t(layer "{layer}")\n'
        f'\t\t(uuid "{uid()}")\n'
        f"\t)\n"
    )


def _footer() -> str:
    return (
        "\t(duplicate_pad_numbers_are_jumpers no)\n"
        "\t(embedded_fonts no)\n"
        ")\n"
    )


def _courtyard_rect(
    cx: float, cy: float, w: float, h: float, layer: str = "F.CrtYd"
) -> str:
    """Courtyard rectangle centered at (cx, cy) with total size w x h."""
    return _fp_rect(
        (cx - w / 2, cy - h / 2),
        (cx + w / 2, cy + h / 2),
        layer,
        CRTYD_WIDTH,
    )


def _silkscreen_rect(
    cx: float, cy: float, w: float, h: float, layer: str = "F.SilkS"
) -> str:
    """Silkscreen outline rectangle centered at (cx, cy)."""
    hx = w / 2
    hy = h / 2
    lines = ""
    lines += _fp_line((cx - hx, cy - hy), (cx + hx, cy - hy), layer, SILK_WIDTH)
    lines += _fp_line((cx + hx, cy - hy), (cx + hx, cy + hy), layer, SILK_WIDTH)
    lines += _fp_line((cx + hx, cy + hy), (cx - hx, cy + hy), layer, SILK_WIDTH)
    lines += _fp_line((cx - hx, cy + hy), (cx - hx, cy - hy), layer, SILK_WIDTH)
    return lines


def _fab_rect(
    cx: float, cy: float, w: float, h: float, layer: str = "F.Fab"
) -> str:
    """Fabrication layer rectangle centered at (cx, cy)."""
    return _fp_rect(
        (cx - w / 2, cy - h / 2),
        (cx + w / 2, cy + h / 2),
        layer,
        FAB_WIDTH,
    )


# ---------------------------------------------------------------------------
# Footprint generators
# ---------------------------------------------------------------------------


def gen_im72d128v() -> tuple[str, str]:
    """
    Infineon IM72D128V MEMS Microphone - LGA 4.0 x 3.0mm, 5 pads.

    Pad layout (bottom view, datasheet pin numbering):
        Pin 1 (VDD)  - bottom-left
        Pin 2 (GND)  - bottom-right
        Pin 3 (CLK)  - top-right
        Pin 4 (DATA) - top-left
        Pin 5 (L/R)  - top-center
    Center: 0.8mm acoustic port (NPTH)

    Pad dimensions from datasheet: 0.5 x 0.5mm nominal.
    Body: 4.0 x 3.0 x 1.2mm.
    """
    name = "IM72D128V"
    body_w, body_h = 4.0, 3.0
    pad_size = (0.5, 0.5)

    # Pad centers (measured from body center, typical LGA)
    # Bottom row: y = +1.0 (positive Y is down in KiCad)
    # Top row: y = -1.0
    # Left: x = -1.35, Right: x = +1.35, Center: x = 0
    pad_y_bot = 1.0
    pad_y_top = -1.0
    pad_x_left = -1.35
    pad_x_right = 1.35
    pad_x_center = 0.0

    s = _header(name)
    s += _standard_properties(
        name,
        ref_y=-(body_h / 2 + 1.5),
        val_y=(body_h / 2 + 1.5),
        description="Infineon IM72D128V MEMS Microphone, LGA 4x3mm, bottom port",
    )

    # Pads
    s += _pad_smd("1", "rect", (pad_x_left, pad_y_bot), pad_size)   # VDD
    s += _pad_smd("2", "rect", (pad_x_right, pad_y_bot), pad_size)  # GND
    s += _pad_smd("3", "rect", (pad_x_right, pad_y_top), pad_size)  # CLK
    s += _pad_smd("4", "rect", (pad_x_left, pad_y_top), pad_size)   # DATA
    s += _pad_smd("5", "rect", (pad_x_center, pad_y_top), pad_size) # L/R

    # Acoustic port - 0.8mm NPTH at center
    s += _pad_npth((0, 0), 0.8)

    # Silkscreen outline with pin-1 marker
    silk_margin = 0.1
    sw = body_w / 2 + silk_margin
    sh = body_h / 2 + silk_margin
    s += _silkscreen_rect(0, 0, body_w + 2 * silk_margin, body_h + 2 * silk_margin)
    # Pin 1 dot (bottom-left corner)
    s += _fp_circle(
        (pad_x_left - 0.6, pad_y_bot),
        0.15, "F.SilkS", SILK_WIDTH, fill="solid"
    )

    # Fab layer body outline
    s += _fab_rect(0, 0, body_w, body_h)

    # Courtyard (0.25mm clearance around body)
    s += _courtyard_rect(0, 0, body_w + 0.5, body_h + 0.5)

    s += _footer()
    return name, s


def gen_pogo_pad_2mm() -> tuple[str, str]:
    """
    Pogo pin contact pad - 2.0mm diameter circular SMD pad.

    No paste (gold-plated surface, no solder applied).
    Large copper area for reliable spring contact.
    """
    name = "PogoPad_2mm"
    pad_dia = 2.0

    s = _header(name)
    s += _standard_properties(
        name,
        ref_y=-2.0,
        val_y=2.0,
        description="Pogo pin contact pad, 2mm diameter, no paste",
    )

    # Single circular pad, no paste
    s += _pad_smd_no_paste("1", "circle", (0, 0), (pad_dia, pad_dia))

    # Courtyard circle (0.25mm clearance)
    s += _fp_circle((0, 0), pad_dia / 2 + 0.25, "F.CrtYd", CRTYD_WIDTH)

    # Fab layer circle
    s += _fp_circle((0, 0), pad_dia / 2, "F.Fab", FAB_WIDTH)

    s += _footer()
    return name, s


def gen_lra_10mm() -> tuple[str, str]:
    """
    LRA (Linear Resonant Actuator) coin motor mount - 10mm diameter.

    Two SMD pads on B.Cu: '+' and '-', each 2x1.5mm, spaced 4mm apart.
    10mm circle on Fab layer for motor outline.
    Mounted on bottom of PCB.
    """
    name = "LRA_10mm"
    motor_dia = 10.0
    pad_w, pad_h = 2.0, 1.5
    pad_spacing = 4.0  # center-to-center

    s = _header(name, layer="B.Cu")
    s += _standard_properties(
        name,
        ref_y=-(motor_dia / 2 + 1.5),
        val_y=(motor_dia / 2 + 1.5),
        description="LRA coin actuator mount, 10mm, bottom side",
    )

    # Pads on B.Cu
    b_layers = '"B.Cu" "B.Mask" "B.Paste"'
    s += _pad_smd("1", "rect", (-pad_spacing / 2, 0), (pad_w, pad_h), layers=b_layers)
    s += _pad_smd("2", "rect", (pad_spacing / 2, 0), (pad_w, pad_h), layers=b_layers)

    # Fab layer - motor outline circle
    s += _fp_circle((0, 0), motor_dia / 2, "B.Fab", FAB_WIDTH)

    # Polarity markers on Fab: '+' near pad 1, '-' near pad 2
    plus_x = -pad_spacing / 2
    minus_x = pad_spacing / 2
    mark_y = -1.5
    # '+' sign
    s += _fp_line((plus_x - 0.4, mark_y), (plus_x + 0.4, mark_y), "B.Fab", FAB_WIDTH)
    s += _fp_line((plus_x, mark_y - 0.4), (plus_x, mark_y + 0.4), "B.Fab", FAB_WIDTH)
    # '-' sign
    s += _fp_line((minus_x - 0.4, mark_y), (minus_x + 0.4, mark_y), "B.Fab", FAB_WIDTH)

    # Courtyard on B.CrtYd
    s += _fp_circle((0, 0), motor_dia / 2 + 0.25, "B.CrtYd", CRTYD_WIDTH)

    s += _footer()
    return name, s


def gen_led_1615_rgb() -> tuple[str, str]:
    """
    RGB LED 1615 package - 1.6 x 1.5mm body, 4 pads at corners.

    Pad assignment (top view):
        1 (R)  ---- 4 (K/cathode)
        2 (G)  ---- 3 (B)
    Pad size: 0.45 x 0.4mm
    """
    name = "LED_1615_RGB"
    body_w, body_h = 1.6, 1.5
    pad_w, pad_h = 0.45, 0.4

    # Pad center offsets from body center
    px = 0.5   # horizontal offset from center
    py = 0.45  # vertical offset from center

    s = _header(name)
    s += _standard_properties(
        name,
        ref_y=-(body_h / 2 + 1.2),
        val_y=(body_h / 2 + 1.2),
        description="RGB LED 1615, 4-pad, common cathode",
    )

    # Pads (top view orientation)
    s += _pad_smd("1", "rect", (-px, -py), (pad_w, pad_h))  # R - top-left
    s += _pad_smd("2", "rect", (-px, py), (pad_w, pad_h))   # G - bottom-left
    s += _pad_smd("3", "rect", (px, py), (pad_w, pad_h))    # B - bottom-right
    s += _pad_smd("4", "rect", (px, -py), (pad_w, pad_h))   # K - top-right

    # Pin 1 marker (cathode indicator line on silkscreen)
    silk_margin = 0.15
    s += _silkscreen_rect(0, 0, body_w + 2 * silk_margin, body_h + 2 * silk_margin)
    # Pin 1 dot
    s += _fp_circle(
        (-px - 0.5, -py),
        0.1, "F.SilkS", SILK_WIDTH, fill="solid"
    )

    # Fab layer body
    s += _fab_rect(0, 0, body_w, body_h)

    # Courtyard
    s += _courtyard_rect(0, 0, body_w + 0.5, body_h + 0.5)

    s += _footer()
    return name, s


def gen_sw_sidepush_ip67() -> tuple[str, str]:
    """
    Side-mount tactile push button (IP67 sealed).

    Body approx 4 x 3mm, side-actuated.
    2 main signal pads (1.5 x 1.2mm) on left side.
    2 mounting/ground tabs (1.0 x 1.5mm) on right side.
    Actuation direction: from right side (+X direction).
    """
    name = "SW_SidePush_IP67"
    body_w, body_h = 4.0, 3.0

    # Main switch pads on left edge
    main_pad = (1.5, 1.2)
    main_x = -(body_w / 2 + main_pad[0] / 2 - 0.3)  # slightly under body
    main_y_spacing = 1.8  # center-to-center vertical

    # Mounting tabs on right edge
    tab_pad = (1.0, 1.5)
    tab_x = (body_w / 2 + tab_pad[0] / 2 - 0.3)
    tab_y_spacing = 2.2

    s = _header(name)
    s += _standard_properties(
        name,
        ref_y=-(body_h / 2 + 1.5),
        val_y=(body_h / 2 + 1.5),
        description="Side-mount tactile switch, IP67, 4x3mm",
    )

    # Main switch pads
    s += _pad_smd("1", "rect", (main_x, -main_y_spacing / 2), main_pad)
    s += _pad_smd("2", "rect", (main_x, main_y_spacing / 2), main_pad)

    # Mounting/ground tabs
    s += _pad_smd("3", "rect", (tab_x, -tab_y_spacing / 2), tab_pad)
    s += _pad_smd("4", "rect", (tab_x, tab_y_spacing / 2), tab_pad)

    # Silkscreen body outline
    s += _silkscreen_rect(0, 0, body_w, body_h)

    # Actuation arrow on silkscreen (pointing left, from right side)
    arrow_x = body_w / 2 + 0.8
    s += _fp_line((arrow_x, 0), (arrow_x - 0.6, -0.3), "F.SilkS", SILK_WIDTH)
    s += _fp_line((arrow_x, 0), (arrow_x - 0.6, 0.3), "F.SilkS", SILK_WIDTH)
    s += _fp_line((arrow_x, 0), (arrow_x + 0.6, 0), "F.SilkS", SILK_WIDTH)

    # Fab layer body
    s += _fab_rect(0, 0, body_w, body_h)

    # Courtyard - account for pads extending beyond body
    crtyd_w = body_w + 2 * main_pad[0] + 0.5
    crtyd_h = body_h + 0.5
    s += _courtyard_rect(0, 0, crtyd_w, crtyd_h)

    s += _footer()
    return name, s


def gen_ant_pcb_trace_ble() -> tuple[str, str]:
    """
    PCB trace inverted-F antenna for 2.4GHz BLE.

    Geometry (all on F.Cu):
      - Feed point (pad 1) at origin
      - GND pad (pad 2) offset left from feed
      - Vertical stub from feed point going up
      - Horizontal radiating element at top (~12mm total trace length)
      - Inverted-F topology: feed + short to GND + radiating element

    Inverted-F antenna dimensions for 2.4GHz (FR4, er~4.4):
      - Radiating arm: ~10mm horizontal
      - Stub height: ~3mm vertical
      - GND short: ~1.5mm from feed point
      - Trace width: 0.3mm (50 ohm on typical stackup)

    3mm keepout zone on User.1 layer.
    """
    name = "ANT_PCB_Trace_BLE"
    trace_w = 0.3  # antenna trace width

    # Geometry parameters
    stub_height = 3.0     # vertical distance from feed to horizontal arm
    gnd_offset = 1.5      # horizontal distance from feed to GND short
    radiating_len = 10.0  # horizontal radiating arm length
    feed_x = 0.0
    feed_y = 0.0

    s = _header(name)
    s += _standard_properties(
        name,
        ref_y=-(stub_height + 2.0),
        val_y=2.0,
        description="PCB trace inverted-F antenna, 2.4GHz BLE, ~12mm",
    )

    # Feed pad (pad 1) - connects to RF output of SoC
    s += _pad_smd("1", "rect", (feed_x, feed_y), (0.6, 0.6))

    # GND pad (pad 2) - connects to ground plane
    s += _pad_smd("2", "rect", (-gnd_offset, feed_y), (0.6, 0.6))

    # Antenna traces on F.Cu (using fp_line for copper traces)
    # 1. Vertical stub from feed point going up (negative Y)
    s += _fp_line(
        (feed_x, feed_y), (feed_x, feed_y - stub_height), "F.Cu", trace_w
    )

    # 2. GND short: vertical from GND pad up to horizontal arm
    s += _fp_line(
        (-gnd_offset, feed_y), (-gnd_offset, feed_y - stub_height), "F.Cu", trace_w
    )

    # 3. Horizontal radiating element at top
    # Extends from GND short position to the right
    arm_y = feed_y - stub_height
    s += _fp_line(
        (-gnd_offset, arm_y), (-gnd_offset + radiating_len, arm_y), "F.Cu", trace_w
    )

    # Fab layer outline of antenna area
    ant_left = -gnd_offset - 0.5
    ant_right = -gnd_offset + radiating_len + 0.5
    ant_top = arm_y - 0.5
    ant_bot = feed_y + 0.5
    s += _fp_rect(
        (ant_left, ant_top), (ant_right, ant_bot), "F.Fab", FAB_WIDTH
    )

    # Keepout zone on User.1 layer (3mm around antenna)
    keepout_margin = 3.0
    s += _fp_rect(
        (ant_left - keepout_margin, ant_top - keepout_margin),
        (ant_right + keepout_margin, ant_bot + keepout_margin),
        "User.1",
        CRTYD_WIDTH,
    )
    # Label the keepout on User.1
    # (KiCad will display it; DRC rules reference User.1 for custom keepout)

    # Courtyard matches keepout
    s += _fp_rect(
        (ant_left - keepout_margin, ant_top - keepout_margin),
        (ant_right + keepout_margin, ant_bot + keepout_margin),
        "F.CrtYd",
        CRTYD_WIDTH,
    )

    s += _footer()
    return name, s


def gen_battery_pouch_32x20() -> tuple[str, str]:
    """
    Battery pouch connector - tab pads for 32x20mm LiPo pouch cell.

    2 large pads for battery tabs:
      '+' (pad 1): 3 x 2mm
      '-' (pad 2): 3 x 2mm
    Pads spaced 5mm apart (center-to-center).
    Large courtyard: 34 x 22mm (battery body outline).
    """
    name = "Battery_Pouch_32x20"
    pad_w, pad_h = 3.0, 2.0
    pad_spacing = 5.0
    battery_w, battery_h = 32.0, 20.0
    crtyd_w, crtyd_h = 34.0, 22.0

    s = _header(name)
    s += _standard_properties(
        name,
        ref_y=-(battery_h / 2 + 1.5),
        val_y=(battery_h / 2 + 1.5),
        description="Battery tab connector for 32x20mm LiPo pouch cell",
    )

    # Tab pads (at top edge of battery, centered horizontally)
    tab_y = -(battery_h / 2 - pad_h / 2 - 0.5)  # near top edge, slightly inset
    s += _pad_smd("1", "rect", (-pad_spacing / 2, tab_y), (pad_w, pad_h))  # +
    s += _pad_smd("2", "rect", (pad_spacing / 2, tab_y), (pad_w, pad_h))   # -

    # Battery body outline on Fab layer
    s += _fab_rect(0, 0, battery_w, battery_h)

    # Polarity markers on Fab
    plus_x = -pad_spacing / 2
    minus_x = pad_spacing / 2
    mark_y = tab_y + pad_h / 2 + 0.8
    # '+' sign
    s += _fp_line((plus_x - 0.5, mark_y), (plus_x + 0.5, mark_y), "F.Fab", FAB_WIDTH)
    s += _fp_line((plus_x, mark_y - 0.5), (plus_x, mark_y + 0.5), "F.Fab", FAB_WIDTH)
    # '-' sign
    s += _fp_line((minus_x - 0.5, mark_y), (minus_x + 0.5, mark_y), "F.Fab", FAB_WIDTH)

    # Courtyard
    s += _courtyard_rect(0, 0, crtyd_w, crtyd_h)

    # Silkscreen - just corners to avoid obstructing battery
    silk_corner = 2.0
    for sx, sy in [(-1, -1), (1, -1), (1, 1), (-1, 1)]:
        cx = sx * battery_w / 2
        cy = sy * battery_h / 2
        s += _fp_line(
            (cx, cy), (cx - sx * silk_corner, cy), "F.SilkS", SILK_WIDTH
        )
        s += _fp_line(
            (cx, cy), (cx, cy - sy * silk_corner), "F.SilkS", SILK_WIDTH
        )

    s += _footer()
    return name, s


# ---------------------------------------------------------------------------
# Registry of all footprint generators
# ---------------------------------------------------------------------------

FOOTPRINT_GENERATORS = [
    gen_im72d128v,
    gen_pogo_pad_2mm,
    gen_lra_10mm,
    gen_led_1615_rgb,
    gen_sw_sidepush_ip67,
    gen_ant_pcb_trace_ble,
    gen_battery_pouch_32x20,
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    script_dir = Path(__file__).parent
    default_output = script_dir.parent / "kicad" / "libs" / "vantage.pretty"

    if len(sys.argv) > 1:
        output_dir = Path(sys.argv[1])
    else:
        output_dir = default_output

    output_dir.mkdir(parents=True, exist_ok=True)

    generated_files: list[Path] = []
    for gen_fn in FOOTPRINT_GENERATORS:
        name, content = gen_fn()
        fp_path = output_dir / f"{name}.kicad_mod"
        fp_path.write_text(content, encoding="utf-8")
        generated_files.append(fp_path)
        print(f"  Generated: {fp_path.name}")

    print(f"\nWrote {len(generated_files)} footprints to {output_dir}/")

    # Validate with kicad-cli if available
    print("\nValidating with kicad-cli fp upgrade...")
    import shutil
    import tempfile

    kicad_cli = shutil.which("kicad-cli")
    if kicad_cli is None:
        print("  WARNING: kicad-cli not found, skipping validation")
        return 0

    # kicad-cli requires the output path to NOT already exist
    tmpdir = Path(tempfile.mkdtemp()) / "fp_validate_output"
    try:
        result = subprocess.run(
            [kicad_cli, "fp", "upgrade", str(output_dir), "--force", "-o", str(tmpdir)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  FAIL: kicad-cli returned {result.returncode}")
            if result.stderr:
                print(f"  stderr: {result.stderr}")
            if result.stdout:
                print(f"  stdout: {result.stdout}")
            return 1
    finally:
        shutil.rmtree(tmpdir.parent, ignore_errors=True)

    print("  PASS: All footprints validated successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
