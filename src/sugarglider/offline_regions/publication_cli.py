"""Prepare unsigned evidence or an independently authorized new release copy."""

import argparse
from pathlib import Path

from sugarglider.offline_regions.models import canonical_json
from sugarglider.offline_regions.publication import (
    PublicationEvidence,
    prepare_approved_region,
    prepare_publication_request,
)
from sugarglider.offline_regions.terrain_source import TerrainSources


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("request", "approved-copy"))
    parser.add_argument("--private-region", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--source-pins", type=Path)
    parser.add_argument("--originals", type=Path, required=True)
    parser.add_argument("--transformation", type=Path, required=True)
    parser.add_argument("--graph-build-record", type=Path, required=True)
    parser.add_argument("--operator-approval", type=Path)
    parser.add_argument("--trusted-approval-sha256")
    args = parser.parse_args()
    if args.command == "request":
        if args.source_pins is None or args.evidence.exists():
            parser.error("request requires source pins and a fresh evidence path")
        if args.source_pins.stat().st_size > 32_768:
            parser.error("source pins exceed limit")
        sources = TerrainSources.model_validate_json(args.source_pins.read_bytes())
        evidence = prepare_publication_request(
            args.private_region,
            args.output,
            sources,
            args.originals,
            args.transformation,
            args.graph_build_record,
        )
        with args.evidence.open("xb") as stream:
            stream.write(canonical_json(evidence.model_dump(mode="json")))
        print("Private documented copy and UNSIGNED approval request prepared.")
        print("No publication approval granted; publication_allowed remains false.")
    else:
        if args.operator_approval is None or args.trusted_approval_sha256 is None:
            parser.error(
                "approved copy requires independently authorized operator approval"
            )
        if (
            args.evidence.stat().st_size > 32_768
            or args.operator_approval.stat().st_size > 4096
        ):
            parser.error("evidence/approval exceeds limit")
        evidence = PublicationEvidence.model_validate_json(args.evidence.read_bytes())
        manifest = prepare_approved_region(
            args.private_region,
            args.output,
            evidence,
            args.originals,
            args.transformation,
            args.graph_build_record,
            approval_bytes=args.operator_approval.read_bytes(),
            trusted_approval_sha256=args.trusted_approval_sha256,
        )
        print(f"Authorized new copy verified: {manifest.build_id}. Nothing uploaded.")


if __name__ == "__main__":
    main()
