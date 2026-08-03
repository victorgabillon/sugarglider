export function createPwaController({
  serviceWorkers = typeof navigator === "undefined"
    ? null
    : navigator.serviceWorker,
  storageManager = typeof navigator === "undefined"
    ? null
    : navigator.storage,
  locationObject = typeof window === "undefined" ? null : window.location,
  secureContext = typeof window !== "undefined" && window.isSecureContext,
  reload = () => window.location.reload(),
  onSupported = () => {},
  onUpdateAvailable = () => {},
  onStatus = () => {},
  canActivateUpdate = () => true,
} = {}) {
  let registration = null;
  let waitingWorker = null;
  let activationRequested = false;
  let reloadHandled = false;
  let controllerListenerBound = false;

  async function register() {
    if (
      !serviceWorkers
      || !allowedRegistrationContext(locationObject, secureContext)
    ) {
      onSupported(false);
      return null;
    }
    onSupported(true);
    try {
      registration = await serviceWorkers.register(
        "/service-worker.js",
        { scope: "/", type: "module", updateViaCache: "none" },
      );
      bindControllerChange();
      inspectWaitingWorker();
      registration.addEventListener("updatefound", watchInstallingWorker);
      onStatus("ready");
      return registration;
    } catch {
      onStatus("unavailable");
      return null;
    }
  }

  function watchInstallingWorker() {
    const worker = registration?.installing;
    if (!worker) return;
    worker.addEventListener("statechange", () => {
      if (
        worker.state === "installed"
        && serviceWorkers.controller
      ) inspectWaitingWorker();
    });
  }

  function inspectWaitingWorker() {
    if (!registration?.waiting) return;
    waitingWorker = registration.waiting;
    onUpdateAvailable(true);
  }

  function bindControllerChange() {
    if (controllerListenerBound) return;
    controllerListenerBound = true;
    serviceWorkers.addEventListener("controllerchange", () => {
      if (
        activationRequested
        && !reloadHandled
      ) {
        reloadHandled = true;
        reload();
      }
    });
  }

  function activateUpdate() {
    if (activationRequested || !waitingWorker) return false;
    if (!canActivateUpdate()) {
      onStatus("update_blocked");
      return false;
    }
    activationRequested = true;
    onStatus("reloading_update");
    try {
      waitingWorker.postMessage({ type: "ACTIVATE_UPDATE" });
    } catch {
      activationRequested = false;
      onStatus("update_available");
      onUpdateAvailable(true);
      return false;
    }
    return true;
  }

  async function checkForUpdate() {
    if (!registration) return false;
    await registration.update();
    inspectWaitingWorker();
    return Boolean(waitingWorker);
  }

  async function requestPersistentStorage() {
    if (typeof storageManager?.persist !== "function") return "unsupported";
    try {
      return await storageManager.persist() ? "persistent" : "evictable";
    } catch {
      return "unavailable";
    }
  }

  return {
    register,
    activateUpdate,
    checkForUpdate,
    requestPersistentStorage,
    updateWaiting: () => Boolean(waitingWorker),
  };
}

export function allowedRegistrationContext(locationObject, secureContext) {
  if (secureContext) return true;
  const hostname = locationObject?.hostname;
  return hostname === "localhost"
    || hostname === "127.0.0.1"
    || hostname === "[::1]";
}
