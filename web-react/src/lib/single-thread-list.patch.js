// Patched version of @assistant-ui/react/dist/client/SingleThreadList.js
// Inline implementation of tapClientResource since it's not exported from @assistant-ui/store v0.2.22.
import { resource, tapMemo } from "@assistant-ui/tap";

// Minimal tapClientResource: returns state + methods from a resource element.
function tapClientResource(element) {
  return {
    get state() { return element.state; },
    get methods() { return element.methods; },
  };
}

const RESOLVED_PROMISE = Promise.resolve();
const THREAD_ID = "default";

const SingleThreadListItem = resource(() => {
  return {
    getState: () => ({
      id: THREAD_ID,
      remoteId: undefined,
      externalId: undefined,
      title: undefined,
      status: "regular",
    }),
    switchTo: () => { },
    rename: () => { },
    archive: () => { },
    unarchive: () => { },
    delete: () => { },
    generateTitle: () => { },
    initialize: async () => ({ remoteId: THREAD_ID, externalId: undefined }),
    detach: () => { },
  };
});

export const SingleThreadList = resource(({ thread }) => {
  const itemClient = tapClientResource(SingleThreadListItem());
  const threadClient = tapClientResource(thread);
  const state = tapMemo(
    () => ({
      mainThreadId: THREAD_ID,
      newThreadId: null,
      isLoading: false,
      threadIds: [THREAD_ID],
      archivedThreadIds: [],
      threadItems: [itemClient.state],
      main: threadClient.state,
    }),
    [itemClient.state, threadClient.state],
  );
  return {
    getState: () => state,
    switchToThread: () => {
      throw new Error("SingleThreadList does not support switchToThread");
    },
    switchToNewThread: () => {
      throw new Error("SingleThreadList does not support switchToNewThread");
    },
    getLoadThreadsPromise: () => RESOLVED_PROMISE,
    reload: () => RESOLVED_PROMISE,
    item: (selector) => {
      if (
        selector !== "main" &&
        !(typeof selector === "object" && "id" in selector && selector.id === THREAD_ID) &&
        !(typeof selector === "object" && "index" in selector && selector.index === 0)
      ) {
        throw new Error(`SingleThreadList: unknown item selector ${JSON.stringify(selector)}`);
      }
      return itemClient.methods;
    },
    thread: (selector) => {
      if (selector !== "main" && selector !== THREAD_ID) {
        throw new Error(`SingleThreadList: unknown thread selector ${JSON.stringify(selector)}`);
      }
      return threadClient.methods;
    },
  };
});
