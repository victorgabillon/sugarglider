# Packaged Open Sans Semibold map glyphs

These PBF files are the intentionally partial, locally served MapLibre glyph
set used by Sugarglider's collision-aware required-POI labels. They were
retrieved on 2026-07-18 using this exact URL template:

    https://demotiles.maplibre.org/font/Open%20Sans%20Semibold/{range}.pbf

The packaged bytes were also verified against the `gh-pages` revision
`ef4389e954d46e97cd9d3b0130881d9fb789ae2e` of
[`maplibre/demotiles`](https://github.com/maplibre/demotiles). That project
states that its font PBFs were generated with the scripts and source fonts from
[`openmaptiles/fonts`](https://github.com/openmaptiles/fonts). The corresponding
Open Sans source and Apache 2.0 license were inspected at OpenMapTiles revision
`0bcd6431ec82fbb74b3a5b697ce315ebf795ad8e`; the applicable license text is
packaged beside these files as `LICENSE.txt`.

## Packaged ranges and hashes

The filenames identify 256-codepoint chunks. Coverage is limited to glyphs
present in Open Sans within these chunks; it is not a claim of broader script
support.

| File | Codepoint chunk | Unicode blocks intersected | SHA-256 |
| --- | --- | --- | --- |
| `0-255.pbf` | U+0000–U+00FF | C0 controls, Basic Latin, C1 controls, Latin-1 Supplement | `64da7011e07531351a249a3d26aad76e2f22e4e321e50833f742697b453e8365` |
| `256-511.pbf` | U+0100–U+01FF | Latin Extended-A, Latin Extended-B | `78298bbd8198c117ccdffe66bf9bbf646fdc1210b7e1bf222f5a9b29b366d7a5` |
| `8192-8447.pbf` | U+2000–U+20FF | General Punctuation, Superscripts and Subscripts, Currency Symbols, Combining Diacritical Marks for Symbols | `ee80ee7ef05e77bea017bcb387d970d61823fc37fdb0a51c446ae322c5974990` |

## Missing ranges

No other PBF chunks are packaged. If a point name needs a codepoint outside the
three chunks above, MapLibre cannot obtain that glyph from Sugarglider's local
glyph URL, so the map label may be incomplete or unavailable. The original name
is never changed and remains available in the required-marker popup and editable
POI list. This local subset avoids adding a runtime font service.
