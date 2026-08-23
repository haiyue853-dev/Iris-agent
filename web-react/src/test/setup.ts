import '@testing-library/jest-dom/vitest';

// Polyfill browser APIs missing in jsdom
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class ResizeObserver {
    callback: ResizeObserverCallback;
    constructor(cb: ResizeObserverCallback) { this.callback = cb; }
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

if (typeof globalThis.DOMRect === 'undefined') {
  (globalThis as unknown as Record<string, unknown>).DOMRect = class DOMRect {
    x = 0; y = 0; width = 0; height = 0;
    top = 0; right = 0; bottom = 0; left = 0;
    toJSON() { return { x: this.x, y: this.y, width: this.width, height: this.height }; }
  } as unknown as typeof DOMRect;
}

