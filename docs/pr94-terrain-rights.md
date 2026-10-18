# PR94 terrain source and rights dossier

Evidence reviewed on 16 October 2026. **Operator publication approval is absent.**
The selected data and both built regional directories remain private. This dossier
records source evidence and engineering checks; it does not grant legal approval.

## Source decision

Use the **2021 Copernicus GLO-30 Public COG distribution** for this private staged
build. Its upstream product is **COP-DEM_GLO-30-DGED**; our acquisition identifier
`COP-DEM_GLO-30-DGED-COG` identifies the processed COG distribution, not original
Airbus DGED files. The [AWS registry](https://registry.opendata.aws/copernicus-dem/)
identifies the 2021 release and its producer/distribution. The
[distributor's processing description](https://copernicus-dem-30m.s3.amazonaws.com/readme.html)
explains the COG changes. Nine downloaded COGs and two geoid grids are pinned in
[the source ledger](../offline-regions/sources/copernicus-2021-yvelines.json).
The [per-file metadata](../offline-regions/sources/copernicus-2021-yvelines-metadata.json)
records provider/product, native format/compression/grid/CRS, vertical meaning,
licence evidence and available quality metadata against each exact source hash.
Terrain product fields describe the nine DSMs; the two NGA undulation grids are
separate inputs with their own models and licence evidence, not Copernicus rasters.

This is a practical, traceable **surface model**, not a bare-earth product. The
independent local IGN comparison demonstrates a substantial source sensitivity,
especially on the long route. Selection does not establish that Copernicus is
more accurate than IGN for hiking. A future bare-earth source decision should
retain these comparisons rather than use the old screenshots as target totals.

| Source | Rights evidence and conditions | Surface / datum | Availability, resolution and conversion | Hiking assessment |
| --- | --- | --- | --- | --- |
| IGN RGE ALTI | IGN's [published dataset](https://www.data.gouv.fr/datasets/rge-alti-r) identifies Licence Ouverte 2.0. Its [terms](https://www.etalab.gouv.fr/wp-content/uploads/2017/04/ETALAB-Licence-Ouverte-v2.0.pdf) permit reuse, modification and commercial redistribution subject to source/update attribution and truthful presentation. | DTM, heterogeneous acquisitions, principally LiDAR since 2010; mainland Lambert-93 / IGN69 normal heights. | Official Yvelines editions: 1 m, 2019-12-09, and 5 m, 2020-07-30. The actual 5 m reference archive is 90,690,133 bytes and expands to about 823 MiB. Full four-degree coverage needs other departmental inputs and a reviewed IGN69 transformation. | Ground-model semantics are preferable in woodland. Resolution is not an accuracy guarantee; source/quality layers and ZICAD no-data need review. Not implemented as a publication input in PR94. |
| USGS SRTM 1 Arc-Second Global / NASA SRTMGL1 V003 | The [USGS product page](https://www.usgs.gov/centers/eros/science/usgs-eros-archive-digital-elevation-shuttle-radar-topography-mission-srtm-1) states open distribution. The [USGS policy](https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits) concerns USGS-produced works and preserves exceptions for third-party content. Review the actual granule/fill lineage; a media “public domain” badge is not dataset clearance. | Radar-derived surface; geographic WGS84 / EGM96. Mission February 2000; void-fill inputs include other products. | Actual 1 arc-second global product, not global 3 arc-second v2. GeoTIFF/BIL/DTED via EarthExplorer; NASA V003 HGT ZIP via CMR/Earthdata. The current documented download redirected to Earthdata authentication; acquisition stopped there. | Simple HGT/datum path, but access was unavailable and radar vegetation/void-fill limitations remain. No credentials or entitlement bypass attempted. |
| Copernicus GLO-30 Public, 2021 COG release | [WorldDEM-30 licence](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf), Articles 4, 6, 7 and 9: reproduction/distribution/adaptation, source and modified-data notices, liability notice, no endorsement, downstream obligations, retained IPR/trademark conditions. | DSM: vegetation/buildings/infrastructure included; WGS84 / EGM2008. TanDEM-X 2011–2015 with older infill products. | Public bounded HTTPS COG acquisition succeeded. Here 1 arc-second node spacing, approximately 20 m east-west / 31 m north-south, not 30 m vertical precision. Requires explicit geoid conversion and missing boundary reconstruction. New four-tile elevation component is 26.72 MB. | Technically usable for an explicitly described DSM profile; forest/building effects and observed cumulative-ascent sensitivity limit terrain claims. Selected for engineering staging, with no public approval. |

IGN's [current product documentation](https://raw.githubusercontent.com/IGNF/cartes.gouv.fr-documentation/main/content/fr/partenaires/ign/observations-regulieres-territoire/relief/rge-alti.md)
states that updates stopped in 2024 and ZICAD areas use no-data. Its
[content specification](https://data.geopf.fr/annexes/ressources/documentation/DC_RGEALTI_2-0.pdf)
identifies EPSG:2154 and EPSG:5720 for mainland data. The
[IGN transformation-grid page](https://geodesie.ign.fr/grilles-de-conversion)
identifies RAF20's RGF93v2b/IGN69 role. PR94 neither assumes the software licence
licenses that grid nor relabels IGN heights EGM96. IGN is a local independent
reference in its own vertical system, not a second publication component.

USGS product DOI: `10.5066/F7PR7TFT`. NASA SRTMGL1 V003 DOI:
`10.5067/MEaSUREs/SRTM/SRTMGL1.003`. Copernicus DOI: `10.5270/ESA-c5d3d65`.
Product identifiers distinguish these from similarly named 90 m products.

## Selected licence, required notices and scope

The exact reviewed three-page Copernicus licence PDF SHA-256 is
`9cd37d37ea654bbcaf0a2e059e6a3a5b5f76072824d8dd860ccf274ada8951bd`.
The publication evidence schema pins this document identity and upstream product.
Article 1 requires acceptance of the terms. An operator record must explicitly
state acceptance; the tool never supplies that acceptance for actual data.

Required modified-data credit:

> produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved

Required liability notice:

> The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30

Retain the applicable terms, identify the transformation and avoid implying
provider/EU/ESA endorsement. Subsequent distributors must be bound by the stated
obligations. The licence does not transfer the source IPR or grant general logo
or trademark rights. Article 7 includes as-is/liability and indemnity provisions;
these need human review alongside the proposed application's terms.

The shared Regions UI exposes these notices, the DSM/datum explanation and the
licence link only when **all four derived HGT hashes match this exact dataset**.
Unknown or historical terrain never receives fabricated Copernicus attribution.
The static distribution README can retain the complete source/derived identity
evidence and explicit absence of approval, independently of the optional UI.

## Datum grids and transformation

Use pinned `us_nga_egm08_25.tif` (2.5 arc-minute EGM2008) and
`us_nga_egm96_15.tif` (15 arc-minute EGM96). The upstream
[PROJ-data NGA record](https://github.com/OSGeo/PROJ-data/blob/master/us_nga/us_nga_README.txt)
identifies both grids, their NGA origins, conversion lineage and Public Domain
status. Their bytes, HTTPS locators and observed object versions are in the ledger.
This is evidence about these specific grids, not an inference from PROJ's software
licence. The [NGA reference](https://earth-info.nga.mil/GandG/wgs84/gravitymod/egm2008/index.html)
and [PROJ operation documentation](https://proj.org/en/stable/operations/transformations/vgridshift.html)
explain the geoid and operation conventions.

At each geographic node, `H96 = H08 + N08 - N96`; inverse EGM2008 grid shift
converts to ellipsoidal height, then forward EGM96 grid shift produces the target
physical height. Grids are mandatory local files; network/optional-grid/ballpark
fallbacks are disabled. Checked offsets vary from −0.122 to +0.103 m over the
100 control positions. No constant offset is substituted. This does not establish
absolute geoid-model accuracy. Nearest-integer, ties-to-even HGT quantization adds
at most 0.5 m per valid node.

## OSM-derived components and the combined graph

Map, Places and Nature remain exact verified derivatives of the configured local
OSM PBF. The routing graph is genuinely rebuilt with the new DEM. Keep
OpenStreetMap contributor attribution, the [ODbL 1.0 terms](https://opendatacommons.org/licenses/odbl/1-0/)
and [OSM attribution guidance](https://www.openstreetmap.org/copyright).
The distribution provides the app-used databases and transformation source
references. No claim is made that a download URL establishes the PBF acquisition
or OSM edit date; its actual hash and header bounds are recorded.

**Human decision still required:** confirm the combined DEM-enriched graph's
redistribution treatment, ODbL database/source obligations, required Copernicus
notices for derivatives and subsequent users, application legal notices and
operator acceptance. Clear evidence of a source licence is not approval of this
particular combined publication. The historical Mapzen/Skadi source remains
unresolved and private; its rights were not retroactively inferred from a new DEM.

No actual operator approval record, public terrain artifact, production catalog
replacement, Pages deployment or Play release is part of this PR.
