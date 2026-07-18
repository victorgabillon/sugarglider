# Sugarglider brand assets

## Files

- `sugarglider-banner.png` — GitHub README and website hero
- `sugarglider-compact-icon.png` — navigation, favicon and small-size mark
- `sugarglider-app-icon.png` — installed application icon
- `sugarglider-flying-map.png` — welcome, empty-state and generation illustration
- `sugarglider-map-pin.png` — required-POI and route-start map marker

## Usage

Preserve the original aspect ratio. Do not stretch, rotate, recolor, or crop
the mascot tightly.

Use the compact icon at small sizes. The detailed app icon and illustration are
intended for larger displays.

The original high-resolution map pin remains canonical in this directory. The
browser scales it to the required marker size without resizing, recompressing,
recoloring, rotating, stretching, or tightly cropping the source image. Run
`make brand-assets` to create byte-identical packaged copies under
`src/sugarglider/web/static/brand/`; never edit those runtime copies directly.
