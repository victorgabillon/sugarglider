"""Copy the canonical Sugarglider artwork into the packaged web application."""

from pathlib import Path
from shutil import copyfile

BRAND_ASSET_FILENAMES: tuple[str, ...] = (
    "sugarglider-app-icon.png",
    "sugarglider-banner.png",
    "sugarglider-compact-icon.png",
    "sugarglider-flying-map.png",
    "sugarglider-map-pin.png",
)


def repository_root() -> Path:
    """Resolve the repository independently of the caller's working directory."""
    return Path(__file__).resolve().parents[1]


def _png_names(directory: Path) -> set[str]:
    if not directory.exists():
        return set()
    return {path.name for path in directory.glob("*.png") if path.is_file()}


def sync_brand_assets() -> tuple[Path, ...]:
    """Copy every permitted asset byte-for-byte and reject unexpected PNGs."""
    root = repository_root()
    canonical_directory = root / "assets" / "brand"
    runtime_directory = root / "src" / "sugarglider" / "web" / "static" / "brand"
    permitted = set(BRAND_ASSET_FILENAMES)

    missing = tuple(
        name
        for name in BRAND_ASSET_FILENAMES
        if not (canonical_directory / name).is_file()
    )
    if missing:
        raise FileNotFoundError(
            "Missing canonical brand asset(s): " + ", ".join(missing)
        )

    unexpected_canonical = sorted(_png_names(canonical_directory) - permitted)
    if unexpected_canonical:
        raise ValueError(
            "Unexpected canonical PNG asset(s): " + ", ".join(unexpected_canonical)
        )

    runtime_directory.mkdir(parents=True, exist_ok=True)
    unexpected_runtime = sorted(_png_names(runtime_directory) - permitted)
    if unexpected_runtime:
        raise ValueError(
            "Unexpected runtime PNG asset(s): " + ", ".join(unexpected_runtime)
        )

    copied: list[Path] = []
    for filename in BRAND_ASSET_FILENAMES:
        source = canonical_directory / filename
        destination = runtime_directory / filename
        copyfile(source, destination)
        copied.append(destination)
        print(f"Copied {source.relative_to(root)} -> {destination.relative_to(root)}")
    return tuple(copied)


def main() -> int:
    """Synchronize the explicit brand-asset manifest."""
    sync_brand_assets()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
