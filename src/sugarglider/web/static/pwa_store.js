const DATABASE_NAME = "sugarglider-pwa";
const DATABASE_VERSION = 2;

export const PWA_STORES = Object.freeze({
  publicRuntime: "public_runtime",
  offlineSnapshots: "offline_snapshots",
  participantSessions: "participant_sessions",
  positionOutbox: "position_outbox",
  trailProfile: "trail_profile",
});

const STORE_NAMES = Object.freeze(Object.values(PWA_STORES));

export async function openPwaStore({
  databaseFactory = globalThis.indexedDB,
} = {}) {
  if (!databaseFactory || typeof databaseFactory.open !== "function") {
    return createMemoryPwaStore();
  }
  try {
    const connection = await openDatabase(databaseFactory);
    return databaseStore(connection);
  } catch {
    return createMemoryPwaStore();
  }
}

export function createMemoryPwaStore() {
  const stores = new Map(
    STORE_NAMES.map((name) => [name, new Map()]),
  );
  let closed = false;

  function selected(name) {
    if (closed) throw new Error("PWA storage is closed.");
    const store = stores.get(name);
    if (!store) throw new Error("Unknown PWA store.");
    return store;
  }

  return {
    durable: false,
    async get(name, key) {
      return cloneValue(selected(name).get(key));
    },
    async put(name, key, value) {
      selected(name).set(key, cloneValue(value));
    },
    async remove(name, key) {
      selected(name).delete(key);
    },
    async removeIf(name, key, matches) {
      const store = selected(name);
      const existing = cloneValue(store.get(key));
      if (existing !== undefined && matches(existing)) {
        store.delete(key);
        return true;
      }
      return false;
    },
    async putIfNewer(name, key, value, isNewer) {
      const store = selected(name);
      const existing = cloneValue(store.get(key));
      const candidate = cloneValue(value);
      if (existing !== undefined && !isNewer(candidate, existing)) {
        return false;
      }
      store.set(key, candidate);
      return true;
    },
    async putLatestOutboxIfSessionMatches({
      sessionName,
      sessionKey,
      sessionMatches,
      outboxName,
      outboxKey,
      value,
      isNewer,
    }) {
      const session = cloneValue(selected(sessionName).get(sessionKey));
      if (session === undefined || !sessionMatches(session)) return false;
      const outboxes = selected(outboxName);
      const existing = cloneValue(outboxes.get(outboxKey));
      const candidate = cloneValue(value);
      if (existing !== undefined && !isNewer(candidate, existing)) {
        return false;
      }
      outboxes.set(outboxKey, candidate);
      return true;
    },
    async replaceAndRemovePrevious({
      name,
      key,
      value,
      relatedName,
      relatedKey,
    }) {
      const store = selected(name);
      const previous = cloneValue(store.get(key));
      const staleRelatedKey = relatedKey(previous);
      if (staleRelatedKey !== null) {
        selected(relatedName).delete(staleRelatedKey);
      }
      store.set(key, cloneValue(value));
    },
    async removeMatchingAndRelated({
      name,
      key,
      matches,
      relatedName,
      relatedKey,
    }) {
      const store = selected(name);
      const existing = cloneValue(store.get(key));
      if (existing === undefined || !matches(existing)) return false;
      store.delete(key);
      selected(relatedName).delete(relatedKey(existing));
      return true;
    },
    async removeSessionAndRelatedOutbox({
      sessionName,
      sessionKey,
      sessionMatches = () => true,
      outboxName,
      relatedOutboxKey,
    }) {
      const sessions = selected(sessionName);
      const existing = cloneValue(sessions.get(sessionKey));
      if (existing === undefined || !sessionMatches(existing)) return false;
      sessions.delete(sessionKey);
      selected(outboxName).delete(relatedOutboxKey(existing));
      return true;
    },
    async putBounded(name, key, value, {
      maximumRecords,
      retain,
      compareEviction,
      onlyIfExisting = false,
    }) {
      const store = selected(name);
      const existing = store.has(key);
      if (onlyIfExisting && !existing) return false;
      const retained = [];
      for (const [storedKey, storedValue] of store.entries()) {
        const candidate = cloneValue(storedValue);
        if (!retain(candidate, storedKey)) {
          store.delete(storedKey);
        } else if (storedKey !== key) {
          retained.push({ key: storedKey, value: candidate });
        }
      }
      retained.sort(compareEviction);
      while (retained.length > maximumRecords - 1) {
        store.delete(retained.shift().key);
      }
      store.set(key, cloneValue(value));
      return true;
    },
    async entries(name) {
      return [...selected(name).entries()].map(([key, value]) => ({
        key,
        value: cloneValue(value),
      }));
    },
    async values(name) {
      return [...selected(name).values()].map(cloneValue);
    },
    async clear(name) {
      selected(name).clear();
    },
    async clearApplicationData() {
      for (const store of stores.values()) store.clear();
    },
    close() {
      closed = true;
    },
  };
}

function openDatabase(databaseFactory) {
  return new Promise((resolve, reject) => {
    const request = databaseFactory.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      for (const name of STORE_NAMES) {
        if (!database.objectStoreNames.contains(name)) {
          database.createObjectStore(name, { keyPath: "key" });
        }
      }
    };
    request.onblocked = () => reject(new Error("PWA storage upgrade blocked."));
    request.onerror = () => reject(storageError(request.error));
    request.onsuccess = () => {
      const database = request.result;
      database.onversionchange = () => database.close();
      resolve(database);
    };
  });
}

function databaseStore(database) {
  let closed = false;

  function connection() {
    if (closed) throw new Error("PWA storage is closed.");
    return database;
  }

  return {
    durable: true,
    async get(name, key) {
      const result = await requestOperation(
        connection(),
        name,
        "readonly",
        (store) => store.get(key),
      );
      return cloneValue(result?.value);
    },
    async put(name, key, value) {
      await requestOperation(
        connection(),
        name,
        "readwrite",
        (store) => store.put({ key, value: cloneValue(value) }),
      );
    },
    async remove(name, key) {
      await requestOperation(
        connection(),
        name,
        "readwrite",
        (store) => store.delete(key),
      );
    },
    async removeIf(name, key, matches) {
      return conditionalRemove(connection(), name, key, matches);
    },
    async putIfNewer(name, key, value, isNewer) {
      return conditionalPut(
        connection(),
        name,
        key,
        value,
        isNewer,
      );
    },
    async putLatestOutboxIfSessionMatches(options) {
      return putLatestOutboxIfSessionMatches(connection(), options);
    },
    async replaceAndRemovePrevious(options) {
      await replaceAndRemovePrevious(connection(), options);
    },
    async removeMatchingAndRelated(options) {
      return removeMatchingAndRelated(connection(), options);
    },
    async removeSessionAndRelatedOutbox(options) {
      return removeSessionAndRelatedOutbox(connection(), options);
    },
    async putBounded(name, key, value, options) {
      return boundedPut(connection(), name, key, value, options);
    },
    async entries(name) {
      const records = await requestOperation(
        connection(),
        name,
        "readonly",
        (store) => store.getAll(),
      );
      return records.map((record) => ({
        key: record.key,
        value: cloneValue(record.value),
      }));
    },
    async values(name) {
      const records = await requestOperation(
        connection(),
        name,
        "readonly",
        (store) => store.getAll(),
      );
      return records.map((record) => cloneValue(record.value));
    },
    async clear(name) {
      await requestOperation(
        connection(),
        name,
        "readwrite",
        (store) => store.clear(),
      );
    },
    async clearApplicationData() {
      await transactionOperation(
        connection(),
        STORE_NAMES,
        "readwrite",
        (transaction) => {
          for (const name of STORE_NAMES) transaction.objectStore(name).clear();
        },
      );
    },
    close() {
      closed = true;
      database.close();
    },
  };
}

function requestOperation(database, name, mode, operation) {
  return new Promise((resolve, reject) => {
    let result;
    let requestFailed = false;
    const transaction = database.transaction(name, mode);
    const request = operation(transaction.objectStore(name));
    request.onsuccess = () => {
      result = request.result;
    };
    request.onerror = () => {
      requestFailed = true;
      reject(storageError(request.error));
    };
    transaction.oncomplete = () => {
      if (!requestFailed) resolve(result);
    };
    transaction.onerror = () => reject(storageError(transaction.error));
    transaction.onabort = () => reject(storageError(transaction.error));
  });
}

function transactionOperation(database, names, mode, operation) {
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(names, mode);
    try {
      operation(transaction);
    } catch (error) {
      transaction.abort();
      reject(error);
      return;
    }
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(storageError(transaction.error));
    transaction.onabort = () => reject(storageError(transaction.error));
  });
}

function conditionalRemove(database, name, key, matches) {
  return new Promise((resolve, reject) => {
    let removed = false;
    const transaction = database.transaction(name, "readwrite");
    const store = transaction.objectStore(name);
    const request = store.get(key);
    request.onsuccess = () => {
      const record = request.result;
      if (record && matches(cloneValue(record.value))) {
        store.delete(key);
        removed = true;
      }
    };
    request.onerror = () => reject(storageError(request.error));
    transaction.oncomplete = () => resolve(removed);
    transaction.onerror = () => reject(storageError(transaction.error));
    transaction.onabort = () => reject(storageError(transaction.error));
  });
}

function conditionalPut(database, name, key, value, isNewer) {
  return new Promise((resolve, reject) => {
    let accepted = false;
    const transaction = database.transaction(name, "readwrite");
    const store = transaction.objectStore(name);
    const request = store.get(key);
    request.onsuccess = () => {
      const existing = request.result?.value;
      const candidate = cloneValue(value);
      if (existing !== undefined && !isNewer(
        candidate,
        cloneValue(existing),
      )) return;
      store.put({ key, value: candidate });
      accepted = true;
    };
    request.onerror = () => reject(storageError(request.error));
    transaction.oncomplete = () => resolve(accepted);
    transaction.onerror = () => reject(storageError(transaction.error));
    transaction.onabort = () => reject(storageError(transaction.error));
  });
}

function putLatestOutboxIfSessionMatches(database, {
  sessionName,
  sessionKey,
  sessionMatches,
  outboxName,
  outboxKey,
  value,
  isNewer,
}) {
  return new Promise((resolve, reject) => {
    let accepted = false;
    const transaction = database.transaction(
      [sessionName, outboxName],
      "readwrite",
    );
    const sessions = transaction.objectStore(sessionName);
    const outboxes = transaction.objectStore(outboxName);
    const sessionRequest = sessions.get(sessionKey);
    sessionRequest.onsuccess = () => {
      const session = cloneValue(sessionRequest.result?.value);
      if (session === undefined || !sessionMatches(session)) return;
      const outboxRequest = outboxes.get(outboxKey);
      outboxRequest.onsuccess = () => {
        const existing = cloneValue(outboxRequest.result?.value);
        const candidate = cloneValue(value);
        if (
          existing !== undefined
          && !isNewer(candidate, existing)
        ) return;
        outboxes.put({ key: outboxKey, value: candidate });
        accepted = true;
      };
      outboxRequest.onerror = () => reject(
        storageError(outboxRequest.error),
      );
    };
    sessionRequest.onerror = () => reject(storageError(sessionRequest.error));
    transaction.oncomplete = () => resolve(accepted);
    transaction.onerror = () => reject(storageError(transaction.error));
    transaction.onabort = () => reject(storageError(transaction.error));
  });
}

function replaceAndRemovePrevious(database, {
  name,
  key,
  value,
  relatedName,
  relatedKey,
}) {
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(
      [name, relatedName],
      "readwrite",
    );
    const store = transaction.objectStore(name);
    const request = store.get(key);
    request.onsuccess = () => {
      const staleRelatedKey = relatedKey(
        cloneValue(request.result?.value),
      );
      if (staleRelatedKey !== null) {
        transaction.objectStore(relatedName).delete(staleRelatedKey);
      }
      store.put({ key, value: cloneValue(value) });
    };
    request.onerror = () => reject(storageError(request.error));
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(storageError(transaction.error));
    transaction.onabort = () => reject(storageError(transaction.error));
  });
}

function removeMatchingAndRelated(database, {
  name,
  key,
  matches,
  relatedName,
  relatedKey,
}) {
  return new Promise((resolve, reject) => {
    let removed = false;
    const transaction = database.transaction(
      [name, relatedName],
      "readwrite",
    );
    const store = transaction.objectStore(name);
    const request = store.get(key);
    request.onsuccess = () => {
      const existing = cloneValue(request.result?.value);
      if (existing === undefined || !matches(existing)) return;
      store.delete(key);
      transaction.objectStore(relatedName).delete(relatedKey(existing));
      removed = true;
    };
    request.onerror = () => reject(storageError(request.error));
    transaction.oncomplete = () => resolve(removed);
    transaction.onerror = () => reject(storageError(transaction.error));
    transaction.onabort = () => reject(storageError(transaction.error));
  });
}

function removeSessionAndRelatedOutbox(database, {
  sessionName,
  sessionKey,
  sessionMatches = () => true,
  outboxName,
  relatedOutboxKey,
}) {
  return new Promise((resolve, reject) => {
    let removed = false;
    const transaction = database.transaction(
      [sessionName, outboxName],
      "readwrite",
    );
    const sessions = transaction.objectStore(sessionName);
    const request = sessions.get(sessionKey);
    request.onsuccess = () => {
      const existing = cloneValue(request.result?.value);
      if (existing === undefined || !sessionMatches(existing)) return;
      sessions.delete(sessionKey);
      transaction.objectStore(outboxName).delete(
        relatedOutboxKey(existing),
      );
      removed = true;
    };
    request.onerror = () => reject(storageError(request.error));
    transaction.oncomplete = () => resolve(removed);
    transaction.onerror = () => reject(storageError(transaction.error));
    transaction.onabort = () => reject(storageError(transaction.error));
  });
}

function boundedPut(database, name, key, value, {
  maximumRecords,
  retain,
  compareEviction,
  onlyIfExisting = false,
}) {
  return new Promise((resolve, reject) => {
    let accepted = false;
    const transaction = database.transaction(name, "readwrite");
    const store = transaction.objectStore(name);
    const request = store.getAll();
    request.onsuccess = () => {
      const records = request.result;
      const existing = records.some((record) => record.key === key);
      if (onlyIfExisting && !existing) return;
      const retained = [];
      for (const record of records) {
        const candidate = cloneValue(record.value);
        if (!retain(candidate, record.key)) {
          store.delete(record.key);
        } else if (record.key !== key) {
          retained.push({ key: record.key, value: candidate });
        }
      }
      retained.sort(compareEviction);
      while (retained.length > maximumRecords - 1) {
        store.delete(retained.shift().key);
      }
      store.put({ key, value: cloneValue(value) });
      accepted = true;
    };
    request.onerror = () => reject(storageError(request.error));
    transaction.oncomplete = () => resolve(accepted);
    transaction.onerror = () => reject(storageError(transaction.error));
    transaction.onabort = () => reject(storageError(transaction.error));
  });
}

function cloneValue(value) {
  if (value === undefined) return undefined;
  if (typeof structuredClone === "function") return structuredClone(value);
  return JSON.parse(JSON.stringify(value));
}

function storageError(error) {
  return error instanceof Error ? error : new Error("PWA storage failed.");
}
