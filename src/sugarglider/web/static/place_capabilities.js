// Index capabilities describe data availability, never routing eligibility.
const FIRST_CLASSIFIER = Object.freeze({ ice_cream: 2, toilets: 3, cafe: 3, bakery: 3, picnic_area: 3 });
export function placeCompatibilityMessage(categories, version) {
  if (!["1", "2", "3"].includes(version)) return "";
  const missing = categories.filter((category) => (FIRST_CLASSIFIER[category] ?? 1) > Number(version));
  if (!missing.length) return "";
  const practical = missing.some((category) => category !== "ice_cream");
  return practical && missing.includes("ice_cream")
    ? "This installed region predates ice-cream and practical-place categories."
    : practical ? "This installed region predates practical-place categories."
      : "This installed region does not include ice-cream places yet.";
}
