# Repository instructions

- Use Python 3.13, `uv`, full annotations, and strict mypy typing.
- Format and lint with Ruff; run `make check` before completing work.
- Unit tests must not depend on Docker, the network, map data, or external services.
- Keep GraphHopper as an external process behind the typed routing adapter.
- Domain code must not import FastAPI.
- GPX export must contain one track and one segment, never a GPX route.
- GraphHopper's total route distance is authoritative; normalize geometry-edge
  distances to that total before calculating metrics.
- Route analysis must be deterministic, and missing path details must remain
  visibly unknown rather than being guessed.
- Fixed generation must preserve required-point order. Optimized-loop generation
  may reorder only non-start mandatory points, must retain original indices, and
  must never silently drop or replace a required point.
- Optimized-loop ordering must keep the first point fixed and use bounded,
  deterministic heuristics rather than exact exponential TSP.
- Generation must be deterministic for a fixed graph, seed, request, and settings;
  every search must enforce a strict full-route evaluation budget.
- Never use Euclidean or straight-line route fallback: all candidate and exported
  geometry must come from the routing backend.
- Target distance remains the primary generation objective; PR3's fixed score must
  keep tolerance status ahead of secondary route-quality metrics.
- Immediate backtracking and total repetition are distinct metrics; incomplete
  edge-ID coverage must remain visible, and dead-end POIs may force retracing.
- GPX files contain no route-analysis extensions.
- Generated GPX remains exactly one track and one segment, never a GPX route.
- Nature, popularity signals, and the web GUI remain future work.
- Never commit PBF map data, GraphHopper caches, secrets, or generated GPX files.
