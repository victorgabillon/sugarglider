"""Lossless partition integrity and resource bounds using synthetic local data."""

import gzip
import hashlib
import json
from pathlib import Path
from typing import cast

import pytest

from sugarglider.nature.models import NatureIndexDocument, NatureIndexFeature
from sugarglider.offline_regions import nature_partitions
from sugarglider.offline_regions.models import (
    RegionalManifest,
    build_identity,
    canonical_json,
)

FIXTURE = Path(__file__).parents[1] / "fixtures/pr40_regional_data.json"


def artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, RegionalManifest, NatureIndexDocument]:
    fixture = json.loads(FIXTURE.read_bytes())
    document = NatureIndexDocument.model_validate_json(json.dumps(fixture["nature"]))
    monkeypatch.setattr(nature_partitions, "MAX_PARTITION_POSITIONS", 10)
    source = tmp_path / "original.json.gz"
    source.write_bytes(gzip.compress(canonical_json(fixture["nature"]), mtime=0))
    root = tmp_path / "region"
    root.mkdir()
    nature_partitions.partition_nature(source, root / "nature", "0" * 64)
    files = []
    paths = [
        root / "nature/partitions.json",
        *sorted((root / "nature").glob("part-*.json.gz")),
    ]
    for index, path in enumerate(paths):
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "byte_size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "format": "nature-partitions-v1-json"
                if index == 0
                else "nature-index-v1-gzip-json",
            }
        )
    value = cast(dict[str, object], fixture["manifest"])
    components = cast(dict[str, dict[str, object]], value["components"])
    components["nature"]["files"] = files
    value["build_id"] = build_identity(
        {k: v for k, v in value.items() if k != "build_id"}
    )
    return root, RegionalManifest.model_validate_json(canonical_json(value)), document


def test_lossless_deterministic_partitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, manifest, original = artifact(tmp_path, monkeypatch)
    nature_partitions.verify_nature_partitions(root, manifest)
    directory = nature_partitions.NaturePartitions.model_validate_json(
        (root / "nature/partitions.json").read_bytes()
    )
    features: list[NatureIndexFeature] = []
    for part in directory.partitions:
        payload = gzip.decompress((root / part.path).read_bytes())
        doc = NatureIndexDocument.model_validate_json(payload)
        assert len(payload) <= nature_partitions.MAX_PARTITION_BYTES
        assert sum(nature_partitions.position_count(f) for f in doc.features) <= 10
        features.extend(doc.features)
    assert tuple(sorted(features, key=lambda f: f.feature_id)) == original.features
    second = tmp_path / "repeat"
    nature_partitions.partition_nature(tmp_path / "original.json.gz", second, "0" * 64)
    for file in manifest.components.nature.files:
        assert (root / file.path).read_bytes() == (
            second / Path(file.path).name
        ).read_bytes()
    with pytest.raises(FileExistsError):
        nature_partitions.partition_nature(
            tmp_path / "original.json.gz", root / "nature", "0" * 64
        )


@pytest.mark.parametrize("change", ["source", "bounds", "count", "duplicate"])
def test_partition_tampering_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    root, manifest, _ = artifact(tmp_path, monkeypatch)
    path = root / "nature/partitions.json"
    directory = json.loads(path.read_bytes())
    if change == "source":
        directory["source_sha256"] = "1" * 64
    elif change == "bounds":
        directory["partitions"][0]["bounds"][0] -= 0.001
    elif change == "count":
        directory["position_count"] += 1
    else:
        first, second = directory["partitions"][:2]
        payload = json.loads(gzip.decompress((root / second["path"]).read_bytes()))
        other = json.loads(gzip.decompress((root / first["path"]).read_bytes()))
        payload["features"][0] = other["features"][0]
        (root / second["path"]).write_bytes(
            gzip.compress(canonical_json(payload), mtime=0)
        )
    path.write_bytes(canonical_json(directory))
    with pytest.raises(ValueError):
        nature_partitions.verify_nature_partitions(root, manifest)


def test_oversized_single_feature_fails_without_splitting_geometry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(nature_partitions, "MAX_PARTITION_POSITIONS", 4)
    fixture = json.loads(FIXTURE.read_bytes())
    source = tmp_path / "original.gz"
    source.write_bytes(gzip.compress(canonical_json(fixture["nature"]), mtime=0))
    with pytest.raises(ValueError, match="one Nature feature"):
        nature_partitions.partition_nature(source, tmp_path / "parts", "0" * 64)


def test_manifest_cannot_omit_one_partition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, manifest, _ = artifact(tmp_path, monkeypatch)
    shortened = manifest.model_copy(
        update={
            "components": manifest.components.model_copy(
                update={
                    "nature": manifest.components.nature.model_copy(
                        update={"files": manifest.components.nature.files[:-1]}
                    )
                }
            )
        }
    )
    with pytest.raises(ValueError, match="identity mismatch"):
        nature_partitions.verify_nature_partitions(root, shortened)
