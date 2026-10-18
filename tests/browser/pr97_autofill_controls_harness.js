import { buildAutofillControls } from "./pr97_autofill_controls.js";

const assert = (condition, message) => { if (!condition) throw Error(message); };
const parse = (html) => new DOMParser().parseFromString(html, "text/html");
const shape = (document) => [...document.querySelectorAll("input,select,textarea")].map((field) => ({
  id: field.id, name: field.name, type: field.type, required: field.required,
  min: field.min, max: field.max, labels: [...field.labels ?? []].map((label) => label.textContent),
}));
const result = document.querySelector("pre");
try {
  const source = await (await fetch("../../src/sugarglider/web/static/index.html")).text();
  const controls = buildAutofillControls(source);
  assert(JSON.stringify(controls) === JSON.stringify(buildAutofillControls(source)), "deterministic fixtures");
  assert(Object.isFrozen(controls), "immutable fixture registry");
  const original = parse(source);
  for (const id of ["route-form", "trail-profile-form", "location-search-form"]) {
    const key = { "route-form": "real-route", "trail-profile-form": "real-profile", "location-search-form": "real-location" }[id];
    assert(parse(controls[key]).querySelector("form").outerHTML === original.getElementById(id).outerHTML, "real source form remains exact");
  }
  const plain = parse(controls["real-all"]), off = parse(controls["real-all-off"]);
  assert(JSON.stringify(shape(plain)) === JSON.stringify(shape(off)), "autocomplete control preserves labels, names, types and validation");
  assert([...off.querySelectorAll("form,input,select,textarea")].every((field) => field.getAttribute("autocomplete") === "off"), "explicit policy attribute on each form/control");
  assert(parse(controls["form-two"]).querySelectorAll("input").length === 2, "two-field comparison");
  assert(parse(controls["form-three"]).querySelectorAll("input").length === 3, "restored third field is present");
  assert(parse(controls["inputs-three"]).forms.length === 0 && parse(controls["inputs-three"]).querySelectorAll("input").length === 3, "unowned fields remain a separate condition");
  assert(parse(controls["real-all-detached"]).querySelectorAll("input").length === 0, "template fields are detached, unlike hidden fields");
  assert(parse(controls["real-all-hidden"]).querySelectorAll("input").length === plain.querySelectorAll("input").length, "hidden fields remain attached");
  assert(parse(controls.none).querySelectorAll("form,input,script,link,img").length === 0, "minimal control has no forms, scripts or assets");
  window.pr97Controls = controls;
  result.textContent = JSON.stringify(["deterministic_immutable_fixtures", "exact_real_form_markup", "autocomplete_only_changes_policy", "two_three_field_comparison", "unowned_fields_are_explicit", "hidden_differs_from_detached", "asset_free_minimal_control"]);
  result.dataset.status = "passed";
} catch (error) { result.textContent = error.stack ?? String(error); result.dataset.status = "failed"; }
