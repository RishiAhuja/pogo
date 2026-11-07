#!/usr/bin/env python3
"""Build the README illustration using local Athletics fonts and generated icons.

Requires the development dependency FontTools. No font files are embedded in the
output: lettering is converted to outlines. Use only fonts you are licensed to use.
Rasterize the SVG with rsvg-convert for the README PNG.
"""

import argparse
import base64
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
INK = "#f0efeb"
MUTED = "#8f918f"
BLUE = "#4779bf"
BG = "#111111"


class Lettering:
    def __init__(self, path, prefix):
        self.font = TTFont(path)
        self.glyphs = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.units = self.font["head"].unitsPerEm
        self.prefix = prefix
        self.definitions = {}

    def text(self, value, x, y, size, color=INK, anchor="start", tracking=0):
        scale = size / self.units
        spacing = tracking / scale
        cursor = 0
        uses = []
        for char in value:
            glyph = self.cmap.get(ord(char))
            if glyph is None:
                raise ValueError(f"Missing glyph in Athletics: {char!r}")
            identity = f"{self.prefix}-{ord(char)}"
            if identity not in self.definitions:
                pen = SVGPathPen(self.glyphs)
                self.glyphs[glyph].draw(pen)
                self.definitions[identity] = pen.getCommands()
            uses.append(f'<use href="#{identity}" transform="translate({cursor:.3f},0)"/>')
            cursor += self.font["hmtx"].metrics[glyph][0] + spacing
        width = (cursor - spacing) * scale if value else 0
        offset = width / 2 if anchor == "middle" else width if anchor == "end" else 0
        return (
            f'<g aria-label={quoteattr(value)} fill="{color}" '
            f'transform="translate({x - offset:.3f},{y}) scale({scale:.7f},{-scale:.7f})">'
            + "".join(uses)
            + "</g>"
        )

    def defs(self):
        return "\n".join(
            f'<path id="{identity}" d="{commands}"/>'
            for identity, commands in self.definitions.items()
        )


def image(path, x, bottom, width, height):
    data = base64.b64encode(path.read_bytes()).decode()
    return (
        f'<image x="{x - width / 2}" y="{bottom - height}" width="{width}" '
        f'height="{height}" preserveAspectRatio="xMidYMax meet" '
        f'href="data:image/png;base64,{data}"/>'
    )


def connection(start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = (dx**2 + dy**2) ** 0.5
    ux, uy = dx / length, dy / length
    x1, y1 = start[0] + ux * 12, start[1] + uy * 12
    x2, y2 = end[0] - ux * 16, end[1] - uy * 16
    return (
        f'<path d="M{x1:.2f},{y1:.2f} L{x2:.2f},{y2:.2f}" '
        'fill="none" stroke="#315d97" stroke-width="2.5" marker-end="url(#arrow)"/>'
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/assets/architecture.svg")
    args = parser.parse_args()
    regular = Lettering(args.font_dir / "Athletics-Regular.otf", "regular")
    bold = Lettering(args.font_dir / "Athletics-Bold.otf", "bold")
    icons = ROOT / "docs/assets/architecture"
    nodes = [(170, 600), (590, 370), (1010, 600), (1430, 370)]
    body = [f'<rect width="1600" height="700" fill="{BG}"/>']
    body.extend(
        [
            bold.text("HPC RELAY", 72, 62, 15, MUTED, tracking=1.6),
            bold.text("The scenic route to your cluster.", 72, 119, 42, tracking=-0.8),
        ]
    )
    body.extend(
        [
            connection(nodes[0], nodes[1]),
            connection(nodes[2], nodes[1]),
            connection(nodes[2], nodes[3]),
        ]
    )
    for x, label, width in [(380, "SSH", 72), (800, "reverse SSH", 142), (1220, "SSH", 72)]:
        body.append(
            f'<rect x="{x - width / 2}" y="466" width="{width}" height="38" '
            f'rx="19" fill="{BG}" stroke="#2c3034"/>'
        )
        body.append(regular.text(label, x, 492, 19, "#b8bcc1", "middle"))
    for x, y in nodes:
        body.append(f'<circle cx="{x}" cy="{y}" r="10" fill="{BG}" stroke="{BLUE}"/>')
        body.append(f'<circle cx="{x}" cy="{y}" r="3.5" fill="{BLUE}"/>')
    body.extend(
        [
            image(icons / "client.png", 170, 573, 242, 210),
            image(icons / "relay.png", 590, 344, 215, 196),
            image(icons / "bastion.png", 1010, 573, 226, 206),
            image(icons / "hpc.png", 1430, 344, 237, 207),
        ]
    )
    for x, y, title, caption in [
        (170, 646, "Client", "On holiday. Coffee in hand."),
        (590, 446, "Public relay", "A little cloud rendezvous."),
        (1010, 646, "Bastion server", "Holding the fort."),
        (1430, 446, "HPC", "Doing the heavy lifting."),
    ]:
        body.append(bold.text(title, x, y, 29, anchor="middle", tracking=-0.45))
        body.append(regular.text(caption, x, y + 31, 19, MUTED, "middle"))
    description = (
        "Four illustrated stops connected by a zigzag: a home client opens SSH to the public relay; "
        "a bastion server, depicted as a laptop, opens reverse SSH back to the relay; "
        "the bastion reaches the private HPC host over SSH."
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="700" '
        'viewBox="0 0 1600 700" role="img" aria-labelledby="title description">\n'
        '<title id="title">The scenic route to your cluster</title>\n'
        f'<desc id="description">{escape(description)}</desc>\n<defs>\n'
        '<marker id="arrow" viewBox="0 0 9 9" refX="8" refY="4.5" '
        'markerWidth="9" markerHeight="9" markerUnits="userSpaceOnUse" orient="auto">'
        '<path d="M0,0 L9,4.5 L0,9 Z" fill="#4779bf"/></marker>\n'
        + regular.defs()
        + "\n"
        + bold.defs()
        + "\n</defs>\n"
        + "\n".join(body)
        + "\n</svg>\n"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg)
    regular.font.close()
    bold.font.close()
    print(args.output)


if __name__ == "__main__":
    main()
