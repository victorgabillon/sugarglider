export const DEFAULT_AVATAR_KEY = "blue";

export const AVATAR_KEYS = Object.freeze([
  "blue",
  "forest",
  "orange",
  "tomato",
  "mask",
]);

export const AVATAR_LABELS = Object.freeze({
  blue: "Lake",
  forest: "Forest",
  orange: "Vico",
  tomato: "Jime",
  mask: "Lezca",
});

export const AVATAR_DEFAULT_NAMES = Object.freeze({
  blue: null,
  forest: null,
  orange: "Vico",
  tomato: "Jime",
  mask: "Lezca",
});

const AVATAR_KEY_SET = new Set(AVATAR_KEYS);

export function isAvatarKey(value) {
  return typeof value === "string" && AVATAR_KEY_SET.has(value);
}

export function normalizeAvatarKey(value) {
  return isAvatarKey(value) ? value : DEFAULT_AVATAR_KEY;
}

export function avatarDisplayLabel(value) {
  return AVATAR_LABELS[normalizeAvatarKey(value)];
}

export function avatarDefaultName(value) {
  return AVATAR_DEFAULT_NAMES[normalizeAvatarKey(value)];
}

export function avatarImageUrl(value) {
  return `/static/brand/profile-badges/${normalizeAvatarKey(value)}.png`;
}

export function outingAvatarImageId(value) {
  return `outing-avatar-${normalizeAvatarKey(value)}`;
}
