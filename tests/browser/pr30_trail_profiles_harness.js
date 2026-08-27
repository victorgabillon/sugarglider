import {
  AVATAR_KEYS,
  DEFAULT_AVATAR_KEY,
  avatarDefaultName,
  avatarDisplayLabel,
  avatarImageUrl,
  normalizeAvatarKey,
  outingAvatarImageId,
} from "../../src/sugarglider/web/static/avatar.js";
import {
  createOuting,
  joinOuting,
} from "../../src/sugarglider/web/static/outings.js";
import {
  createMemoryPwaStore,
  PWA_STORES,
} from "../../src/sugarglider/web/static/pwa_store.js";
import {
  initializeTrailProfile,
  normalizeTrailProfile,
  trailProfileAvatarKey,
} from "../../src/sugarglider/web/static/trail_profile.js";
import {
  outingAvatarRegistrationIds,
  outingLiveAvatarProperties,
} from "../../src/sugarglider/web/static/map.js";

export async function runPr30TrailProfilesHarness() {
  const scenarios = [];
  profileValidationScenario();
  scenarios.push("profile_validation");
  await profileUiScenario();
  scenarios.push("profile_ui_and_fallback");
  await localProfileStorageScenario();
  scenarios.push("local_profile_storage");
  await outingPayloadScenario();
  scenarios.push("outing_payloads");
  await profileMarkupScenario();
  scenarios.push("profile_markup");
  avatarFallbackScenario();
  scenarios.push("avatar_fallback");
  return scenarios;
}

async function profileUiScenario() {
  installProfileFixture();
  const memory = createMemoryPwaStore();
  let failWrites = true;
  const store = {
    ...memory,
    durable: true,
    async put(...arguments_) {
      if (failWrites) throw new Error("simulated quota failure");
      return memory.put(...arguments_);
    },
  };

  await initializeTrailProfile({ requireSetup: false, store });
  const dialog = document.getElementById("trail-profile-dialog");
  assert(!dialog.open, "public viewer initialization is not blocked");
  assert(
    !document.getElementById("setup-join-profile").classList.contains("hidden"),
    "public invitation can request setup",
  );

  await initializeTrailProfile({ requireSetup: true });
  assert(dialog.open, "root first use opens the modal");
  const profileName = document.getElementById("trail-profile-name");
  document.querySelector(
    'input[name="trail-profile-avatar"][value="orange"]',
  ).click();
  equal(profileName.value, "Vico", "named badge supplies its default name");
  document.querySelector(
    'input[name="trail-profile-avatar"][value="blue"]',
  ).click();
  equal(profileName.value, "Vico", "Lake badge preserves the current name");
  document.querySelector(
    'input[name="trail-profile-avatar"][value="forest"]',
  ).click();
  equal(profileName.value, "Vico", "Forest badge preserves the current name");
  profileName.value = "Forest Fox";
  document.querySelector(
    'input[name="trail-profile-avatar"][value="forest"]',
  ).checked = true;
  document.getElementById("trail-profile-form").dispatchEvent(
    new Event("submit", { bubbles: true, cancelable: true }),
  );
  await wait(0);
  equal(trailProfileAvatarKey(), "forest", "session profile survives failed write");
  equal(
    await memory.get(PWA_STORES.trailProfile, "current"),
    undefined,
    "failed durable write stores no partial record",
  );
  assert(
    document.getElementById("trail-profile-storage-status").textContent
      .includes("this tab only"),
    "storage failure is disclosed",
  );
  await wait(1250);

  const joinName = document.getElementById("outing-join-name");
  joinName.value = "Manual invitation name";
  joinName.dispatchEvent(new Event("input", { bubbles: true }));
  failWrites = false;
  document.getElementById("edit-trail-profile").click();
  document.getElementById("trail-profile-name").value = "Masked Fox";
  document.querySelector(
    'input[name="trail-profile-avatar"][value="mask"]',
  ).checked = true;
  document.getElementById("trail-profile-form").dispatchEvent(
    new Event("submit", { bubbles: true, cancelable: true }),
  );
  await wait(0);
  equal(trailProfileAvatarKey(), "mask", "profile edit updates future avatar");
  equal(
    document.getElementById("outing-creator-name").value,
    "Masked Fox",
    "untouched create field receives edited profile name",
  );
  equal(
    joinName.value,
    "Manual invitation name",
    "manually edited join field is preserved",
  );
  equal(
    await memory.get(PWA_STORES.trailProfile, "current"),
    {
      schema_version: 1,
      display_name: "Masked Fox",
      avatar_key: "mask",
    },
    "successful edit persists exact profile fields",
  );
}

function installProfileFixture() {
  const fixture = document.createElement("section");
  fixture.innerHTML = `
    <button id="edit-trail-profile" type="button">My profile</button>
    <button id="setup-join-profile" type="button">Set up trail profile</button>
    <input id="outing-creator-name">
    <input id="outing-join-name">
    <dialog id="trail-profile-dialog">
      <form id="trail-profile-form">
        <h2 id="trail-profile-title">Welcome to Sugarglider</h2>
        <input id="trail-profile-name">
        ${AVATAR_KEYS.map((key) => (
          `<label><input type="radio" name="trail-profile-avatar" value="${key}"${key === "blue" ? " checked" : ""}>${key}</label>`
        )).join("")}
        <p id="trail-profile-storage-status"></p>
        <button id="cancel-trail-profile" type="button">Cancel</button>
        <button id="save-trail-profile" type="submit">Continue</button>
      </form>
    </dialog>
  `;
  document.body.append(fixture);
}

function profileValidationScenario() {
  const profile = normalizeTrailProfile({
    schema_version: 1,
    display_name: "  Forest Fox  ",
    avatar_key: "forest",
  });
  equal(profile.display_name, "Forest Fox", "display name trimmed");
  equal(profile.avatar_key, "forest", "avatar retained");
  for (const invalid of [
    { schema_version: 2, display_name: "Fox", avatar_key: "blue" },
    { schema_version: 1, display_name: "", avatar_key: "blue" },
    { schema_version: 1, display_name: "Fox", avatar_key: "purple" },
    {
      schema_version: 1,
      display_name: "Fox",
      avatar_key: "blue",
      participant_token: "forbidden",
    },
  ]) throws(() => normalizeTrailProfile(invalid), "invalid profile rejected");
}

async function localProfileStorageScenario() {
  const store = createMemoryPwaStore();
  const profile = normalizeTrailProfile({
    schema_version: 1,
    display_name: "Marly Runner",
    avatar_key: "tomato",
  });
  await store.put(PWA_STORES.trailProfile, "current", profile);
  equal(
    await store.get(PWA_STORES.trailProfile, "current"),
    profile,
    "profile record round trips",
  );
  equal(store.durable, false, "memory fallback is explicitly ephemeral");
  await store.clearApplicationData();
  equal(
    await store.get(PWA_STORES.trailProfile, "current"),
    undefined,
    "site-data clearing removes the profile",
  );
}

async function outingPayloadScenario() {
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    return { ok: true, json: async () => ({}) };
  };
  try {
    await createOuting("Forest day", "Fox", "saved_route_123456789", "forest");
    await joinOuting(
      "outing_slug_123456789",
      "join-capability-with-at-least-thirty-two-characters",
      "Badger",
      "saved_route_123456789",
      "mask",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
  const createBody = JSON.parse(requests[0].options.body);
  const joinBody = JSON.parse(requests[1].options.body);
  equal(createBody.participant_avatar_key, "forest", "create avatar sent");
  equal(joinBody.avatar_key, "mask", "join avatar sent");
  assert(
    !("participant_token" in createBody) && !("participant_token" in joinBody),
    "profile payloads contain no participant capability",
  );
}

async function profileMarkupScenario() {
  const applicationUrl = new URL(
    "../../src/sugarglider/web/static/index.html",
    window.location.href,
  );
  const response = await fetch(applicationUrl);
  assert(response.ok, "application markup loads");
  const document = new DOMParser().parseFromString(
    await response.text(),
    "text/html",
  );
  assert(document.getElementById("trail-profile-dialog"), "profile dialog exists");
  assert(document.getElementById("edit-trail-profile"), "Tools profile action exists");
  assert(document.getElementById("setup-join-profile"), "join setup action exists");
  const radios = [...document.querySelectorAll(
    'input[name="trail-profile-avatar"]',
  )];
  equal(radios.map((radio) => radio.value), AVATAR_KEYS, "five badge radios");
  for (const radio of radios) {
    const image = radio.closest("label")?.querySelector("img");
    const label = avatarDisplayLabel(radio.value);
    assert(image, `${radio.value} badge image exists`);
    assert(
      image.getAttribute("src") === avatarImageUrl(radio.value),
      `${radio.value} uses its real local image`,
    );
    equal(radio.getAttribute("aria-label"), `${label} trail badge`, "radio label");
    equal(image.getAttribute("alt"), `${label} Sugarglider trail badge`, "image alt");
    equal(
      radio.closest("label")?.querySelector("span")?.textContent,
      label,
      "visible badge caption",
    );
  }
}

function avatarFallbackScenario() {
  equal(normalizeAvatarKey("unknown"), DEFAULT_AVATAR_KEY, "unknown is blue");
  equal(
    AVATAR_KEYS.map((key) => avatarDisplayLabel(key)),
    ["Lake", "Forest", "Vico", "Jime", "Lezca"],
    "display labels do not change stable avatar keys",
  );
  equal(avatarDisplayLabel("unknown"), "Lake", "unknown label is Lake");
  equal(
    AVATAR_KEYS.map((key) => avatarDefaultName(key)),
    [null, null, "Vico", "Jime", "Lezca"],
    "only named badges supply default names",
  );
  equal(outingAvatarImageId("unknown"), "outing-avatar-blue", "map ID fallback");
  equal(
    outingAvatarRegistrationIds(),
    [
      "outing-avatar-blue",
      "outing-avatar-forest",
      "outing-avatar-orange",
      "outing-avatar-tomato",
      "outing-avatar-mask",
    ],
    "five stable map image IDs",
  );
  const blueOnly = (imageId) => imageId === "outing-avatar-blue";
  equal(
    outingLiveAvatarProperties("forest", blueOnly),
    { avatar_key: "forest", avatar_image: "outing-avatar-blue" },
    "missing selected image uses registered blue map image",
  );
  equal(
    outingLiveAvatarProperties("unknown", blueOnly),
    { avatar_key: "blue", avatar_image: "outing-avatar-blue" },
    "unknown participant data becomes blue",
  );
  equal(
    outingLiveAvatarProperties("mask", () => false),
    { avatar_key: "mask", avatar_image: "" },
    "colored casing remains when every image load fails",
  );
}

function throws(action, message) {
  try {
    action();
  } catch {
    return;
  }
  throw new Error(message);
}

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function equal(actual, expected, message) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(
      `${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
    );
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
