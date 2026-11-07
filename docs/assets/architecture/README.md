# Architecture illustration

Pogo's README uses `../architecture.png`, a 3200 × 1400 raster export of
`../architecture.svg`. The SVG contains outlined Athletics lettering and embedded
PNG spot illustrations, so it needs no external fonts, images, or network requests.
The bastion server is depicted as a laptop. Its reverse-SSH arrow points back to
the public relay because the bastion initiates that connection.

## Rebuild

Install `requirements-dev.txt` and librsvg's `rsvg-convert`, then supply your own
licensed Athletics Regular and Bold OTF files:

```bash
python3 scripts/render-architecture.py --font-dir /path/to/athletics
rsvg-convert -w 3200 -h 1400 docs/assets/architecture.svg -o docs/assets/architecture.png
```
