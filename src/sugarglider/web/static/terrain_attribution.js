// Attribution is shown only for the exact verified four-tile dataset.
const HASHES = Object.freeze(["fac3ef52cbea26ca5736a597923562f79e36c0ef041e4ddde0f5e3d4f655de95", "eea1345034e3110af7d2a0b9a706358be987182b3fb4b9e180a97e21e0f7ca7e", "1b2b3dfd1a59691f81cf3f7a33043be9dc8c4f147d7f1a13ce9ec37141a18111", "3c18a4d200ea418549ca097893338d52d47efd8eddb4b00edb2cf1cb7f457454"]);
const CREDIT = "produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved";
const DISCLAIMER = "The organisations in charge of the Copernicus programme by law or by delegation do not incur any liability for any use of the Copernicus WorldDEM-30";
const LICENSE = "https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf";

export function appendTerrainAttribution(parent, manifest) {
  const tiles = manifest?.components?.elevation?.files?.slice(1);
  if (!Array.isArray(tiles) || tiles.length !== HASHES.length
      || tiles.some((file, i) => file.sha256 !== HASHES[i])) return false;
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "Elevation source and license";
  details.append(summary);
  for (const text of ["Copernicus GLO-30, 2021 COG release. Surface model: trees and buildings may affect heights. Converted from EGM2008 to EGM96 with NGA geoid grids.", CREDIT, DISCLAIMER]) {
    const p = document.createElement("p"); p.textContent = text; details.append(p);
  }
  const link = document.createElement("a"); link.href = LICENSE;
  link.textContent = "Copernicus WorldDEM-30 license";
  link.rel = "noopener noreferrer"; link.target = "_blank";
  details.append(link); parent.append(details); return true;
}
