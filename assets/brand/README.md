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

## Supplied AI planning artwork

- `sources/sugarglider-ai-planner-original.png` preserves the user's supplied
  transparent 1536×1024 PNG byte-for-byte. SHA-256:
  `3af185b15de9cd2b8112a3f4e717720e1b805972d34be141fcae28088045e0a5`.
- `sugarglider-ai-planner.png` is the canonical UI derivative: transparent RGBA,
  256×194, 78,621 bytes. SHA-256:
  `5a0202fe8e016dadb15aada780b4fb6b6ae1514ac26d9ffba6640046528613b2`.
  The user explicitly requested trimming this illustration's transparent margins.
  Its route, red pin, stars, bubble outline, colours and proportions are preserved.
  It represents AI-assisted adventure planning; it never replaces the mascot,
  production launcher artwork or required-POI marker.

Preparation used Pillow 12.2.0: measure the alpha > 8 bounds to ignore nearly
transparent background residue, retain 12 source pixels of padding, crop to
`(324, 167, 1269, 883)`, resize proportionally with LANCZOS to fit 256×256, and save
RGBA PNG with `optimize=True, compress_level=9`. Pixels inside the crop were not
repainted, recoloured, thresholded or regenerated. The high-resolution source is
retained for future derivation; it is not copied to the runtime or APK.

Run `make brand-assets` to copy the optimized canonical file byte-for-byte into
`src/sugarglider/web/static/brand/`. The same bundled image appears in the opening
Map action, Plan action and shared adventure-dialog heading. Its empty alt text
avoids repeating the adjacent accessible text label.

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
