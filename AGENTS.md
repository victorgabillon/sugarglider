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
- Do not add a composite route-quality score until its objective is explicitly
  designed.
- GPX files contain no route-analysis extensions.
- Do not add target-distance optimisation before PR3.
- Never commit PBF map data, GraphHopper caches, secrets, or generated GPX files.
