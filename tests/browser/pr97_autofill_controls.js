// Reproducible device controls, built from public source HTML, never user state.
// These fixtures do not predict network outcomes: device UID measurements do.
export function buildAutofillControls(source) {
  const parse = (html) => new DOMParser().parseFromString(html, "text/html");
  const original = parse(source);
  const forms = [...original.querySelectorAll("form")];
  for (const id of ["trail-profile-form", "route-form", "location-search-form", "create-outing-form", "join-outing-form"]) {
    if (!forms.some((form) => form.id === id)) throw Error(`Missing real form: ${id}`);
  }
  const selected = (...ids) => forms.filter((form) => ids.includes(form.id)).map((form) => form.outerHTML).join("");
  const all = forms.map((form) => form.outerHTML).join("");
  const off = parse(all);
  for (const field of off.querySelectorAll("form,input,select,textarea")) field.setAttribute("autocomplete", "off");
  const one = '<label for="route-name">Route name</label><input id="route-name" name="route_name">';
  const two = one + '<label for="target">Distance</label><input id="target" name="target_m" type="number">';
  const three = two + '<label for="seed">Seed</label><input id="seed" name="seed" type="number">';
  const bodies = {
    none: "<p>Local control</p>", input: one, "form-one": `<form>${one}</form>`,
    "form-two": `<form>${two}</form>`, "form-three": `<form>${three}</form>`, "inputs-three": three,
    "form-three-off": `<form autocomplete="off">${three.replaceAll("<input", '<input autocomplete="off"')}</form>`,
    "form-three-hidden": `<form hidden>${three}</form>`,
    "form-three-detached": `<template><form>${three}</form></template>`,
    "form-three-dynamic": `<template><form>${three}</form></template><script>setTimeout(()=>document.body.append(document.querySelector("template").content.cloneNode(true)),3000)</script>`,
    "real-all": all, "real-all-off": off.body.innerHTML,
    "real-all-hidden": `<div hidden>${all}</div>`, "real-all-detached": `<template>${all}</template>`,
    "real-route": selected("route-form"), "real-profile": selected("trail-profile-form"),
    "real-location": selected("location-search-form"), "real-outings": selected("create-outing-form", "join-outing-form"),
  };
  const shell = (body) => '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PR97 local control</title><style>body{font:16px sans-serif}label,input,select{display:block;margin:8px} [hidden]{display:none}</style><body>' + body + "</body></html>";
  return Object.freeze(Object.fromEntries(Object.entries(bodies).map(([name, body]) => [name, shell(body)])));
}
