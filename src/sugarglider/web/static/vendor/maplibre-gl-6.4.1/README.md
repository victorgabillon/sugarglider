# MapLibre GL JS 6.4.1

Unmodified official `maplibre-gl@6.4.1` browser distribution, BSD-3-Clause.

- Package: `https://registry.npmjs.org/maplibre-gl/-/maplibre-gl-6.4.1.tgz`
- npm integrity: `sha512-KzxQKtfBu/pSz1C+yW1hNS9eyj2h2lC7ufdAi6/SEt177n3oAfDfmUmslRfJdXY7ReAFBcnvwsqmiyoDhtA9GQ==`
- Tarball SHA-256: `21d78393afc6db78f1f9963dfd979057b536b309d8c48c1a4dde95277a522fef`
- Upstream revision: `37e08c1901bee38fb5103510436b590c0460b44f`

This version fixes the attribution sanitizer bypass
[GHSA-jrc7-96c5-q579](https://github.com/maplibre/maplibre-gl-js/security/advisories/GHSA-jrc7-96c5-q579).
The ESM entry, shared module and module worker are all packaged locally; no CDN,
remote worker or fallback script is used. Debug distributions and source maps are
not packaged. JavaScript/CSS/license bytes are copied without editing or
re-minifying. The existing shared map adapter imports the module directly.

Installed file SHA-256 values:

- `maplibre-gl.mjs`: `97e8b9a39ab8b823d6a0caf9c312237262bc9138a6162d9e29606f5f8d24127d`
- `maplibre-gl-shared.mjs`: `fcf4d81450df235da0aea74897cc23926774b5228d38ae1de6a7d701c5905785`
- `maplibre-gl-worker.mjs`: `ce4957017fe705ac2f9ebef206cca966d08d8621756c39326a78cf09757e7d75`
- `maplibre-gl.css`: `8e2dbbab312dc57656fbb76e9fa5308c75c9d7c7ba5808a7d55bcdb64cc813fa`
- `LICENSE.txt`: `ee5fc05a0677eaf69601d2c7db0d9ecd6cc27c3abc1d0733bc9ed34707cf8ef2`
