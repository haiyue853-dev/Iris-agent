// Shim for @assistant-ui/store — re-export everything plus the missing tapClientResource
import { resource } from "@assistant-ui/tap";

// Minimal tapClientResource: wraps a resource element into { state, methods }.
function tapClientResource(element) {
  return {
    get state() { return element.state; },
    get methods() { return element.methods; },
  };
}

export { tapClientResource };

// Re-export everything from the real store
export * from "@assistant-ui/store";
