// Exercise the real upstream attribution sanitizer and module worker with only
// synthetic GeoJSON. The payload changes one test counter; no network is used.
const CREDIT = '<a href="https://www.openstreetmap.org/copyright">OpenStreetMap contributors</a>';
const PAYLOAD = '<details open onload="void 0" ontoggle="globalThis.__sugargliderAttributionProbe += 1">unsafe attribution</details>';

export async function runMapLibreSecurityHarness(maplibre) {
  const scenarios = [];
  globalThis.__sugargliderAttributionProbe = 0;
  const map = new maplibre.Map({
    container: "map",
    center: [0, 0],
    zoom: 14,
    style: style(CREDIT),
    attributionControl: { customAttribution: PAYLOAD },
    fadeDuration: 0,
  });
  try {
    await rendered(map);
    assertSanitized(map);
    scenarios.push("consecutive_custom_attribution_attributes_are_removed");
    assert(map.queryRenderedFeatures({ layers: ["fixture-line"] }).length > 0,
      "the local module worker must process and render synthetic GeoJSON");
    scenarios.push("packaged_module_worker_renders_geojson");

    map.setStyle(style(CREDIT + PAYLOAD));
    await rendered(map);
    assertSanitized(map);
    scenarios.push("source_attribution_remains_sanitized_after_style_replacement");

    const label = '<img src=x onerror="globalThis.__sugargliderAttributionProbe += 1">';
    const popup = new maplibre.Popup().setLngLat([0, 0]).setText(label).addTo(map);
    assert(popup.getElement().textContent.includes(label), "popup labels retain literal text");
    assert(!popup.getElement().querySelector("img"), "popup labels never create HTML elements");
    popup.remove();
    assert(globalThis.__sugargliderAttributionProbe === 0, "no test payload executed");
    scenarios.push("text_popup_does_not_interpret_markup");
    return scenarios;
  } finally {
    map.remove();
    delete globalThis.__sugargliderAttributionProbe;
  }
}

function style(attribution) {
  return {
    version: 8,
    sources: {
      fixture: {
        type: "geojson",
        attribution,
        data: {
          type: "Feature",
          properties: {},
          geometry: { type: "LineString", coordinates: [[-0.005, 0], [0.005, 0]] },
        },
      },
    },
    layers: [
      { id: "background", type: "background", paint: { "background-color": "#f2eee3" } },
      { id: "fixture-line", type: "line", source: "fixture", paint: { "line-color": "#214b3b", "line-width": 4 } },
    ],
  };
}

async function rendered(map) {
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("MapLibre render timed out")), 10_000);
    map.once("idle", () => { clearTimeout(timer); resolve(); });
    map.triggerRepaint();
  });
  // Give a surviving details toggle handler the opportunity to execute.
  await new Promise((resolve) => setTimeout(resolve, 50));
}

function assertSanitized(map) {
  const attribution = map.getContainer().querySelector(".maplibregl-ctrl-attrib-inner");
  assert(attribution, "attribution remains visible");
  assert(attribution.querySelector('a[href="https://www.openstreetmap.org/copyright"]'),
    "licensed map credit and its link survive sanitization");
  const elements = [attribution, ...attribution.querySelectorAll("*")];
  assert(elements.every((element) => element.getAttributeNames().every((name) => !/^on/i.test(name))),
    "no adjacent event-handler attribute survives sanitization");
  assert(globalThis.__sugargliderAttributionProbe === 0, "attribution payload never executes");
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
