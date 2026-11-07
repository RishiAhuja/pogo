# Architecture illustration

The README uses `../architecture.png`, a 3200 × 1400 raster export of
`../architecture.svg`. The SVG contains outlined Athletics lettering and embedded
PNG spot illustrations, so it needs no external fonts, images, or network requests.
The bastion server is depicted as a laptop. Its reverse-SSH arrow points back to
the public relay because the bastion initiates that connection.

The four spot illustrations were generated as one transparent sheet with the
built-in imagegen tool on 8 November 2026, then revised into flat editorial doodles
with the same tool. The four icons were extracted, trimmed, and downscaled. The
routing, labels, and exact Athletics letterforms are composed by
`scripts/render-architecture.py`. Short captions beneath the four stops add a
little personality. The image has no port number, subtitle, or footer.
The original font binaries are not included.

## Rebuild

Install `requirements-dev.txt` and librsvg's `rsvg-convert`, then supply your own
licensed Athletics Regular and Bold OTF files:

```bash
python3 scripts/render-architecture.py --font-dir /path/to/athletics
rsvg-convert -w 3200 -h 1400 docs/assets/architecture.svg -o docs/assets/architecture.png
```

## Artwork generation prompt

> Use case: style-transfer
> Asset type: coordinated four-device illustration sheet for a dark SSH architecture diagram.
> Input image: edit target and reference for the four objects, their props, and their 2 by 2 quadrant positions.
> Primary change: redraw all four illustrations in a much simpler, flatter, more abstract editorial doodle style. The existing objects are too realistic. Replace their realistic textures and detailed modelling with bold, slightly wonky off-white hand-drawn contours and a few flat fills. Make them charming, clean, confident graphic illustrations, like contemporary independent magazine spot drawings.
> Preserve: top-left open client laptop with a coffee mug; top-right tiny server box sitting on a cloud with an aerial; bottom-left an open laptop with a backpack and a small Wi-Fi symbol, which will be labelled Bastion server later; bottom-right three computing server cabinets. Keep all four complete, separated in their own quadrants with generous transparent margins.
> Style: flat two-dimensional shapes, simplified perspective, sparse playful linework, rounded corners, tiny hand-drawn imperfections. Laptop keyboards are only a few short strokes, not individual realistic keys. Server cabinets have only a few large vent marks and dots, no detailed mesh or realistic fan components. The cloud is a simple flat scalloped silhouette, no volumetric shading.
> Palette: warm off-white contours and cream faces, charcoal grey flat screen areas, restrained muted cobalt-blue accents, suitable for placement on near-black #111111.
> Remove: graphite shading, pencil grain, crosshatching, gradients, fine surface texture, metallic highlights, volumetric light, realistic materials, photorealism, 3D-rendered appearance, cast shadows and ground planes.
> Constraints: retain the genuinely transparent background and four-quadrant arrangement. Do not add faces, eyes, arms, legs, text, logos, labels, connecting lines, borders or watermarks. No new objects. Calm and slightly witty, not childish or goofy.
