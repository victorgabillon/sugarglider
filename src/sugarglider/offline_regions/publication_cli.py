"""Prepare unsigned evidence or an independently authorized new release copy."""

import argparse
from pathlib import Path

from sugarglider.offline_regions.ign_publication import (
    IGNLegalEvidence,
    IGNNotices,
    prepare_ign_request,
)
from sugarglider.offline_regions.models import canonical_json
from sugarglider.offline_regions.publication import (
    ReleaseEvidence,
    parse_publication_evidence,
    prepare_approved_region,
    prepare_publication_request,
)
from sugarglider.offline_regions.publication_records import bounded_record
from sugarglider.offline_regions.source_notices import SupplementaryNotices
from sugarglider.offline_regions.terrain_source import TerrainSources


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("request", "ign-request", "approved-copy"))
    parser.add_argument("--private-region", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--source-pins", type=Path)
    parser.add_argument("--originals", type=Path, required=True)
    parser.add_argument("--transformation", type=Path, required=True)
    parser.add_argument("--graph-build-record", type=Path, required=True)
    parser.add_argument("--operator-approval", type=Path)
    parser.add_argument("--trusted-approval-sha256")
    parser.add_argument("--prepared", type=Path)
    parser.add_argument("--legal-directory", type=Path)
    parser.add_argument("--legal-evidence", type=Path)
    parser.add_argument("--notices", type=Path)
    parser.add_argument("--osm-pbf", type=Path)
    parser.add_argument("--supplementary-notices", type=Path)
    args = parser.parse_args()
    evidence: ReleaseEvidence
    if args.command == "ign-request":
        if any(
            p is None
            for p in (
                args.prepared,
                args.legal_directory,
                args.legal_evidence,
                args.notices,
                args.osm_pbf,
            )
        ):
            parser.error(
                "IGN request requires preparation, legal documents, notices and OSM"
            )
        if (
            args.output is not None
            or args.operator_approval is not None
            or args.trusted_approval_sha256 is not None
        ):
            parser.error(
                "IGN request only writes unsigned evidence, never a release copy"
            )
        evidence = prepare_ign_request(
            args.private_region,
            args.originals,
            args.prepared,
            args.transformation,
            args.graph_build_record,
            args.legal_directory,
            IGNLegalEvidence.model_validate_json(bounded_record(args.legal_evidence)),
            IGNNotices.model_validate_json(bounded_record(args.notices)),
            args.osm_pbf,
            supplementary_notices=SupplementaryNotices.model_validate_json(
                bounded_record(args.supplementary_notices)
            )
            if args.supplementary_notices is not None
            else None,
        )
        with args.evidence.open("xb") as stream:
            stream.write(canonical_json(evidence.model_dump(mode="json")))
        print(
            f"UNSIGNED IGN69 request: {evidence.release_build_id}; no approval granted."
        )
        return
    if args.output is None:
        parser.error("request/approved-copy requires a fresh --output")
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
        evidence = parse_publication_evidence(bounded_record(args.evidence))
        manifest = prepare_approved_region(
            args.private_region,
            args.output,
            evidence,
            args.originals,
            args.transformation,
            args.graph_build_record,
            approval_bytes=args.operator_approval.read_bytes(),
            trusted_approval_sha256=args.trusted_approval_sha256,
            prepared=args.prepared,
            legal_directory=args.legal_directory,
            osm_pbf=args.osm_pbf,
        )
        print(f"Authorized new copy verified: {manifest.build_id}. Nothing uploaded.")


if __name__ == "__main__":
    main()
