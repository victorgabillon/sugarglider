const ICON_PATHS = {
  json: "M6 2.75h8l4 4V21.25H6z M14 2.75v4h4 M9 11h6 M9 15h6",
  gpx: "M4 18.5c2-5 4-7 7-7s3 3 5 3 3-3 4-9 M4 18.5l1.5-4 M4 18.5l4-.25 M20 2.5l-1.5 4 M20 2.5l-4 .25",
  add: "M12 5v14 M5 12h14",
  fit: "M8 3H3v5 M16 3h5v5 M8 21H3v-5 M16 21h5v-5",
  generate: "M12 2.75l2.4 6.85L21.25 12l-6.85 2.4L12 21.25l-2.4-6.85L2.75 12 9.6 9.6z",
  cancel: "M6 6l12 12 M18 6L6 18",
  clear: "M4 7h16 M9 7V4h6v3 M7 7l1 14h8l1-14 M10 11v6 M14 11v6",
  copy: "M9 9h11v11H9z M4 15H3V4h11v1",
  download: "M12 3v12 M7.5 10.5L12 15l4.5-4.5 M4 20h16",
  up: "M6 14l6-6 6 6",
  down: "M6 10l6 6 6-6",
  delete: "M4 7h16 M9 7V4h6v3 M8 7l1 14h6l1-14",
  nature: "M19.5 4.5C12 4.5 6 8 6 14c0 3 2 5.5 5 5.5 6 0 8.5-8.5 8.5-15z M5 21c2-6 6-10 12-13",
  alternatives: "M4 6h16 M4 12h11 M4 18h7 M17 10l3 2-3 2",
  direction: "M4 12h14 M13 7l5 5-5 5",
  close: "M6 6l12 12 M18 6L6 18",
  info: "M12 10.5v7 M12 6.5h.01 M3 12a9 9 0 1 0 18 0 9 9 0 1 0-18 0",
};

export function createIcon(name) {
  const pathData = ICON_PATHS[name];
  if (!pathData) throw new Error(`Unknown local icon: ${name}`);
  const namespace = "http://www.w3.org/2000/svg";
  const icon = document.createElementNS(namespace, "svg");
  icon.classList.add("action-icon");
  icon.setAttribute("viewBox", "0 0 24 24");
  icon.setAttribute("aria-hidden", "true");
  icon.setAttribute("focusable", "false");
  const path = document.createElementNS(namespace, "path");
  path.setAttribute("d", pathData);
  icon.append(path);
  return icon;
}

export function decorateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((element) => {
    if (!element.querySelector(":scope > .action-icon")) {
      element.prepend(createIcon(element.dataset.icon));
    }
  });
}
