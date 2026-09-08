# Protomaps basemap style 5.7.2

- Upstream: `@protomaps/basemaps@5.7.2`, git revision
  `3ea8293a28131c3dc63f1bb20827bdb8a76df06f`.
- npm tarball SHA-256:
  `2d5d41b29cdd2364f7092ad439bd9d170b4f38cbec8858cefbe84d0f98125ce6`.
- npm integrity:
  `sha512-K1Yk6bWdULulYg+R2QRVXx4NzJZan5YQhpejEG0c1/sXruJrfPIPZuakpf3jwAgVmjIRVQwAv+yRafDeN0aaUQ==`.
- Vendored file: the official `dist/esm/index.js`, renamed `basemaps.js`, with only
  a final POSIX newline added. Workspace SHA-256:
  `a41d87faaf6004ffa264d81d6afd8d819ad55f88753ad3706ba046c855a17a2b`.
- License: BSD-3-Clause. `LICENSE.md` is copied byte-for-byte from the pinned
  upstream source. SHA-256:
  `74f975cfedd168098c43b5cfd6e587e40604684c4ffcec3e90d24b3b09c061b0`.

PR36 calls `layers(source, namedFlavor("light"))` without a language and filters
symbol layers. This first local style therefore needs no remote glyph or sprite
asset while retaining land, water, landcover, land use, roads, paths, and buildings.
