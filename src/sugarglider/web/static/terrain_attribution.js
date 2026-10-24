// Notices are code-pinned to reviewed payload identities, never manifest source text.
const HASHES = Object.freeze(["fac3ef52cbea26ca5736a597923562f79e36c0ef041e4ddde0f5e3d4f655de95", "eea1345034e3110af7d2a0b9a706358be987182b3fb4b9e180a97e21e0f7ca7e", "1b2b3dfd1a59691f81cf3f7a33043be9dc8c4f147d7f1a13ce9ec37141a18111", "3c18a4d200ea418549ca097893338d52d47efd8eddb4b00edb2cf1cb7f457454"]);
const CREDIT = "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved";
const DISCLAIMER = "The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30";
const LICENSE = "https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf";

// Reviewed IGN derivation; source ledger and edition list are checked in Python tests.
const IGN = Object.freeze({
  "ledger_sha256": "7c5ead1c0b224ac88106c35785a36f2c7ce8105cf95f5adce592d54245d8f1b9",
  "tiles": [
    {
      "byte_size": 3597713,
      "format": "skadi-hgt-gzip-v1",
      "path": "elevation/skadi/N48/N48E001.hgt.gz",
      "sha256": "a7d55ab92559ace1c64069bdf7669717e2ddd8acfbc9c8b041a770d0461688d3"
    },
    {
      "byte_size": 4248630,
      "format": "skadi-hgt-gzip-v1",
      "path": "elevation/skadi/N48/N48E002.hgt.gz",
      "sha256": "d47f7dc9e0947cacd975be249fb73c8c7212f98b9cdb384d9044da87f81ca5e0"
    },
    {
      "byte_size": 5527281,
      "format": "skadi-hgt-gzip-v1",
      "path": "elevation/skadi/N49/N49E001.hgt.gz",
      "sha256": "d79a01593f51fa01589242892505b90e3a13479405c864373462d2b094bd7611"
    },
    {
      "byte_size": 4891056,
      "format": "skadi-hgt-gzip-v1",
      "path": "elevation/skadi/N49/N49E002.hgt.gz",
      "sha256": "7955eec7df9675fdf2d897d6f581379c87940365353a2505c420ee6565415cb3"
    }
  ],
  "routing_archive": {
    "byte_size": 99481600,
    "format": "valhalla-3.9.1-elevation-tar",
    "path": "routing/valhalla_tiles.tar",
    "sha256": "d47b022dc2036800bfa5eadc902a90d94de2cff8df32e6377ac9c0ff5fe9fb3d"
  },
  "editions": [
    "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D002_2020-09-04.7z",
    "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D027_2022-12-21.7z",
    "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D028_2019-12-16.7z",
    "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D041_2019-12-16.7z",
    "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D045_2023-01-03.7z",
    "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D060_2020-09-04.7z",
    "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D075_2020-07-30.7z",
    "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D076_2020-10-20.7z",
    "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D077_2021-03-03.7z",
    "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D078_2020-07-30.7z",
    "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D080_2019-07-09.7z",
    "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D089_2023-01-03.7z",
    "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D091_2021-03-03.7z",
    "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D092_2020-07-30.7z",
    "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D093_2020-07-30.7z",
    "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D094_2020-07-30.7z",
    "RGEALTI_2-0_5M_ASC_LAMB93-IGN69_D095_2020-07-30.7z"
  ]
});
const IGN_NAME = "IGN — RGE ALTI® 5 m";
const IGN_LICENSE = "https://www.data.gouv.fr/pages/legal/licences/etalab-2.0";

function matches(file, expected) {
  return file !== null && typeof file === "object"
    && Object.keys(expected).every(key => file[key] === expected[key]);
}

function sourceIdentity(manifest) {
  const files = manifest?.components?.elevation?.files;
  if (!Array.isArray(files) || files.length !== 5) return null;
  if (manifest.schema_version === 2
      && matches(files[0], {path:"elevation/manifest.json", format:"elevation-manifest-v1"})
      && Number.isSafeInteger(files[0].byte_size) && files[0].byte_size > 0
      && typeof files[0].sha256 === "string" && /^[a-f0-9]{64}$/.test(files[0].sha256)
      && IGN.tiles.every((expected, i) => matches(files[i + 1], expected))) return "ign";
  if (HASHES.every((hash, i) => files[i + 1]?.sha256 === hash)) return "copernicus";
  return null;
}

function paragraph(parent, text) {
  const p = parent.ownerDocument.createElement("p"); p.textContent = text; parent.append(p);
}

function link(parent, text, href) {
  const a = parent.ownerDocument.createElement("a"); a.textContent = text; a.href = href;
  a.rel = "noopener noreferrer"; a.target = "_blank"; parent.append(a);
}

function disclosure(parent, text) {
  const details = parent.ownerDocument.createElement("details");
  const summary = parent.ownerDocument.createElement("summary"); summary.textContent = text;
  details.append(summary); parent.append(details); return details;
}

function appendTerrainContent(parent, manifest, source) {
  if (source === "copernicus") {
    for (const text of ["Copernicus GLO-30, 2021 COG release. Surface model: trees and buildings may affect heights. Converted from EGM2008 to EGM96 with NGA geoid grids.", CREDIT, DISCLAIMER]) paragraph(parent, text);
    link(parent, "Copernicus WorldDEM-30 license", LICENSE);
    return;
  }
  paragraph(parent, `${IGN_NAME} · ground-elevation model. Height reference: NGF-IGN69 normal heights (EPSG:5720).`);
  paragraph(parent, "Runtime terrain: one-arcsecond HGT, resampled from the 5 m source grid and quantized to integer metres. The derived HGT does not retain the original 5 m resolution.");
  const routing = manifest?.components?.routing?.files;
  paragraph(parent, Array.isArray(routing) && routing.length === 2 && matches(routing[1], IGN.routing_archive)
    ? "Derived IGN terrain is also incorporated into this region’s Valhalla routing graph."
    : "Terrain provenance for this routing graph is unavailable; this credit identifies the elevation HGT only.");
  const licence = parent.ownerDocument.createElement("p"); parent.append(licence);
  link(licence, "Licence Ouverte 2.0", IGN_LICENSE);
  licence.append(" · "); link(licence, "IGN RGE ALTI source", "https://www.data.gouv.fr/datasets/rge-alti-r");
  paragraph(parent, "These credits do not imply endorsement by IGN or OpenStreetMap contributors.");
  const editions = disclosure(parent, `Source archive editions (${IGN.editions.length})`);
  editions.dataset.sourceDisclosure = "editions";
  paragraph(editions, "The dates in these original archive names identify source editions, not the terrain acquisition date of each individual cell.");
  const list = parent.ownerDocument.createElement("ul"); list.className = "terrain-editions";
  for (const name of IGN.editions) {
    const item = parent.ownerDocument.createElement("li"), code = parent.ownerDocument.createElement("code");
    code.textContent = name; item.append(code); list.append(item);
  }
  editions.append(list);
}

// Existing standalone Copernicus callers retain their disclosure and notices.
export function appendTerrainAttribution(parent, manifest) {
  const source = sourceIdentity(manifest);
  if (!source) return false;
  appendTerrainContent(disclosure(parent, "Elevation source and license"), manifest, source);
  return true;
}

// Descriptors come from the installed manifest. No extra I/O or legal authorization.
export function appendRegionSources(parent, manifest) {
  const details = disclosure(parent, "Data sources and licences");
  details.className = "region-sources"; details.dataset.sourceDisclosure = "sources";
  const terrain = parent.ownerDocument.createElement("h4"); terrain.textContent = "Terrain elevation sources"; details.append(terrain);
  const source = sourceIdentity(manifest);
  if (source) appendTerrainContent(details, manifest, source);
  else paragraph(details, "Terrain source information is unavailable or unsupported for this installed data. No terrain source or licence is inferred.");
  const map = parent.ownerDocument.createElement("h4"); map.textContent = "Map data sources"; details.append(map);
  paragraph(details, "See the separate credits on the map for its data sources and licences. Terrain licensing does not cover other map data.");
  return details;
}

// The chart receives the selected analysis's verified height reference, not card metadata.
export function appendElevationSource(parent, heightReference) {
  parent.replaceChildren();
  if (typeof heightReference === "string" && heightReference.startsWith("IGN69 normal metres; IGN RGE ALTI 5 m;")) {
    parent.append(`${IGN_NAME} · ground model · NGF-IGN69 normal heights (EPSG:5720). `);
    link(parent, "Licence Ouverte 2.0", IGN_LICENSE);
  } else parent.textContent = typeof heightReference === "string" && heightReference.startsWith("EGM96 orthometric")
    ? "Height reference: EGM96 orthometric metres." : "Height reference: unresolved vertical datum.";
}
