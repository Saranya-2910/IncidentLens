import "@testing-library/jest-dom";

// Polyfill ResizeObserver for Recharts in jsdom
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver = ResizeObserverMock;
