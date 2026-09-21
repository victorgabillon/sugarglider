# Sugarglider brand assets

## Files

- `sugarglider-banner.png` — GitHub README and website hero
- `sugarglider-compact-icon.png` — navigation, favicon and small-size mark
- `sugarglider-app-icon.png` — installed application icon
- `sugarglider-flying-map.png` — welcome, empty-state and generation illustration
- `sugarglider-map-pin.png` — required-POI and route-start map marker
- `sugarglider-ice-cream-pin.png` — selected ice-cream place and detail artwork;
  supplied transparent RGBA source, 1024×1536, used without conversion or cropping.
  SHA-256: `79bc80cc0e3bbed28c1fafcec4b752901b563dc36a112c900683b7fd3254f427`.
  Ordinary ice-cream places use the compact code-native cone icon in
  `place_presentation.js`; the illustration is reserved for selection.

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
