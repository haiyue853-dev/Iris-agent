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
if (typeof globalThis.WebGL2RenderingContext === 'undefined') {
  class WebGL2RenderingContextMock {
    static readonly BOOL = 0x8B56;
    static readonly BYTE = 0x1400;
    static readonly UNSIGNED_BYTE = 0x1401;
    static readonly SHORT = 0x1402;
    static readonly UNSIGNED_SHORT = 0x1403;
    static readonly INT = 0x1404;
    static readonly UNSIGNED_INT = 0x1405;
    static readonly FLOAT = 0x1406;
  }
  (globalThis as unknown as Record<string, unknown>).WebGL2RenderingContext = WebGL2RenderingContextMock;
}

if (typeof globalThis.WebGLRenderingContext === 'undefined') {
  class WebGLRenderingContextMock {
    static readonly UNSIGNED_BYTE = 0x1401;
    static readonly FLOAT = 0x1406;
    static readonly TRIANGLES = 0x0004;
  }
  (globalThis as unknown as Record<string, unknown>).WebGLRenderingContext = WebGLRenderingContextMock;
}
