import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// JSDOM lacks the native dialog top layer. These lifecycle adapters keep
// component tests usable; browser QA verifies focus containment and rendering.
if (!HTMLDialogElement.prototype.showModal)
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    writable: true,
    value: function (this: HTMLDialogElement) {
      this.open = true;
    },
  });
if (!HTMLDialogElement.prototype.close)
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    writable: true,
    value: function (this: HTMLDialogElement, returnValue?: string) {
      if (!this.open) return;
      if (returnValue !== undefined) this.returnValue = returnValue;
      this.open = false;
      this.dispatchEvent(new Event("close"));
    },
  });

afterEach(() => cleanup());
