import "@testing-library/jest-dom";

// jsdom não implementa PointerEvent — os arrastes do Editor (splitters, trim,
// legenda) precisam de clientX/clientY reais nos testes.
if (typeof window !== "undefined" && typeof window.PointerEvent === "undefined") {
  class PointerEventPolyfill extends MouseEvent {
    pointerId: number;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 1;
    }
  }
  // @ts-expect-error atribuição do polyfill
  window.PointerEvent = PointerEventPolyfill;
}
