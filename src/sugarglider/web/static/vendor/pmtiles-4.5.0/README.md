# PMTiles browser runtime 4.5.0

- Upstream: `pmtiles@4.5.0`, git revision
  `3b10e67edb65c6b04549f74c0279cef8328d859c`.
- npm tarball SHA-256:
  `23ae7c575578ad24cd579377d69c46550631da219e6f179997ec2cf3b8c937e5`.
- npm integrity:
  `sha512-CBeD4SoUluFziGdy/8k7FOjQxQy486n+929W/tWophauvMICpkZ26vGBWhDt/6b1FZQWNaf4jFdT/5+q0Wii5w==`.
- Vendored file: the official `dist/pmtiles.js` browser bundle, with only a final
  POSIX newline added. Workspace SHA-256:
  `08d687b3605d61ee91128086d826676708ff51e5f2e1c7acc02b5834984bbbc7`.
- License: BSD-3-Clause. `LICENSE.txt` is copied from the pinned upstream source,
  with only a final POSIX newline added. Workspace SHA-256:
  `c5430dc019512cc4f4fe8c89e9f57bc5cd3096916847fba4bb7e632d55f86579`.

The global browser build is intentional: its public `PMTiles` and `Protocol` APIs
are self-contained, whereas the package ESM distribution retains a bare dependency
specifier that browsers cannot resolve without a bundler or import map.
