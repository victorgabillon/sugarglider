import {
  DEFAULT_AVATAR_KEY,
  avatarDefaultName,
  avatarDisplayLabel,
  avatarImageUrl,
  isAvatarKey,
} from "./avatar.js";
import { pwaRuntime } from "./pwa_runtime.js";
import { PWA_STORES } from "./pwa_store.js";

const PROFILE_KEY = "current";
export const TRAIL_PROFILE_SCHEMA_VERSION = 1;

let currentProfile = null;
let initialized = false;
let controlsBound = false;
let setupRequired = false;
let activeStore = null;
const profileSubscribers = new Set();

const byId = (id) => document.getElementById(id);

export async function initializeTrailProfile({
  requireSetup = false,
  store = null,
} = {}) {
  if (!initialized) {
    activeStore = store;
    bindProfileControls();
    await restoreTrailProfile();
    initialized = true;
  }
  syncProfileUi();
  if (requireSetup && !currentProfile) openTrailProfileEditor({ required: true });
  return currentProfile;
}

export function trailProfileAvatarKey() {
  return currentProfile?.avatar_key ?? DEFAULT_AVATAR_KEY;
}

export function subscribeTrailProfile(listener) {
  profileSubscribers.add(listener);
  return () => profileSubscribers.delete(listener);
}

export function normalizeTrailProfile(value) {
  if (
    !plainObject(value)
    || value.schema_version !== TRAIL_PROFILE_SCHEMA_VERSION
    || Object.keys(value).sort().join(",") !== "avatar_key,display_name,schema_version"
    || !validDisplayName(value.display_name)
    || !isAvatarKey(value.avatar_key)
  ) throw new Error("Invalid local trail profile.");
  return Object.freeze({
    schema_version: TRAIL_PROFILE_SCHEMA_VERSION,
    display_name: value.display_name.trim(),
    avatar_key: value.avatar_key,
  });
}

export function openTrailProfileEditor({ required = false } = {}) {
  const dialog = byId("trail-profile-dialog");
  if (!dialog) return;
  setupRequired = required && !currentProfile;
  const name = byId("trail-profile-name");
  name.value = currentProfile?.display_name ?? suggestedDisplayName();
  const avatar = currentProfile?.avatar_key ?? DEFAULT_AVATAR_KEY;
  byId("trail-profile-title").textContent = setupRequired
    ? "Welcome to Sugarglider"
    : currentProfile
      ? "My profile"
      : "Set up your trail profile";
  byId("save-trail-profile").textContent = setupRequired ? "Continue" : "Save";
  const radio = dialog.querySelector(
    `input[name="trail-profile-avatar"][value="${avatar}"]`,
  );
  if (radio) radio.checked = true;
  byId("cancel-trail-profile").classList.toggle("hidden", setupRequired);
  byId("trail-profile-storage-status").textContent = "";
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
  name.focus();
}

async function restoreTrailProfile() {
  try {
    const store = await profileStore();
    const stored = await store.get(PWA_STORES.trailProfile, PROFILE_KEY);
    if (stored === undefined) return;
    try {
      currentProfile = normalizeTrailProfile(stored);
    } catch {
      await store.remove(PWA_STORES.trailProfile, PROFILE_KEY);
    }
  } catch {
    currentProfile = null;
  }
}

async function saveTrailProfile(profile) {
  currentProfile = profile;
  let persisted = false;
  try {
    const store = await profileStore();
    if (store.durable) {
      await store.put(PWA_STORES.trailProfile, PROFILE_KEY, profile);
      persisted = true;
    }
  } catch {
    // The validated in-memory profile remains usable for this tab.
  }
  syncProfileUi();
  for (const subscriber of profileSubscribers) {
    try {
      subscriber(currentProfile);
    } catch {
      // Profile persistence remains authoritative if optional map rendering fails.
    }
  }
  return persisted;
}

async function profileStore() {
  if (!activeStore) activeStore = (await pwaRuntime()).store;
  return activeStore;
}

function bindProfileControls() {
  if (controlsBound || !byId("trail-profile-form")) return;
  controlsBound = true;
  synchronizeAvatarLabels();
  for (const input of document.querySelectorAll(
    'input[name="trail-profile-avatar"]',
  )) {
    input.addEventListener("click", () => {
      const defaultName = avatarDefaultName(input.value);
      if (!defaultName) return;
      const name = byId("trail-profile-name");
      name.value = defaultName;
      name.setCustomValidity("");
    });
  }
  for (const id of ["outing-creator-name", "outing-join-name"]) {
    byId(id)?.addEventListener("input", (event) => {
      event.target.dataset.profileDirty = "true";
    });
  }
  byId("edit-trail-profile")?.addEventListener("click", () => {
    openTrailProfileEditor();
  });
  byId("setup-join-profile")?.addEventListener("click", () => {
    openTrailProfileEditor();
  });
  byId("cancel-trail-profile").addEventListener("click", () => {
    closeProfileDialog();
  });
  const dialog = byId("trail-profile-dialog");
  dialog.addEventListener("cancel", (event) => {
    if (setupRequired) event.preventDefault();
  });
  byId("trail-profile-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const checked = dialog.querySelector(
      'input[name="trail-profile-avatar"]:checked',
    );
    let profile;
    try {
      profile = normalizeTrailProfile({
        schema_version: TRAIL_PROFILE_SCHEMA_VERSION,
        display_name: byId("trail-profile-name").value,
        avatar_key: checked?.value,
      });
    } catch {
      byId("trail-profile-name").setCustomValidity(
        "Enter a display name of 1 to 80 visible characters.",
      );
      byId("trail-profile-name").reportValidity();
      return;
    }
    byId("trail-profile-name").setCustomValidity("");
    const persisted = await saveTrailProfile(profile);
    byId("trail-profile-storage-status").textContent = persisted
      ? "Profile saved on this device."
      : "Browser storage is unavailable. This profile will last for this tab only.";
    setupRequired = false;
    window.setTimeout(closeProfileDialog, persisted ? 0 : 1200);
  });
}

function syncProfileUi() {
  const profile = currentProfile;
  const joinProfileAction = byId("setup-join-profile");
  if (joinProfileAction) {
    joinProfileAction.classList.remove("hidden");
    joinProfileAction.textContent = profile
      ? "Change trail profile"
      : "Set up trail profile";
  }
  byId("edit-trail-profile")?.setAttribute(
    "aria-label",
    profile
      ? `My profile: ${profile.display_name}, ${avatarDisplayLabel(profile.avatar_key)} badge`
      : "Set up my profile",
  );
  if (!profile) return;
  for (const id of ["outing-creator-name", "outing-join-name"]) {
    const field = byId(id);
    if (field && field.dataset.profileDirty !== "true") {
      field.value = profile.display_name;
    }
  }
  const joinAvatar = byId("outing-join-profile-avatar");
  if (joinAvatar) {
    joinAvatar.src = avatarImageUrl(profile.avatar_key);
    joinAvatar.alt = `${profile.display_name}'s ${avatarDisplayLabel(profile.avatar_key)} trail badge`;
    joinAvatar.classList.remove("hidden");
  }
  if (byId("outing-join-profile-name")) {
    byId("outing-join-profile-name").textContent = profile.display_name;
  }
}

function synchronizeAvatarLabels() {
  for (const input of document.querySelectorAll(
    'input[name="trail-profile-avatar"]',
  )) {
    const label = avatarDisplayLabel(input.value);
    input.setAttribute("aria-label", `${label} trail badge`);
    const card = input.closest("label");
    const image = card?.querySelector("img");
    if (image) image.alt = `${label} Sugarglider trail badge`;
    const caption = card?.querySelector("span");
    if (caption) caption.textContent = label;
  }
}

function suggestedDisplayName() {
  for (const id of ["outing-join-name", "outing-creator-name"]) {
    const value = byId(id)?.value.trim();
    if (validDisplayName(value)) return value;
  }
  return "";
}

function closeProfileDialog() {
  if (setupRequired) return;
  const dialog = byId("trail-profile-dialog");
  if (typeof dialog.close === "function") dialog.close();
  else dialog.removeAttribute("open");
}

function validDisplayName(value) {
  if (typeof value !== "string") return false;
  const trimmed = value.trim();
  return trimmed.length >= 1
    && trimmed.length <= 80
    && !/\p{C}/u.test(trimmed);
}

function plainObject(value) {
  return value !== null
    && typeof value === "object"
    && !Array.isArray(value)
    && Object.getPrototypeOf(value) === Object.prototype;
}
