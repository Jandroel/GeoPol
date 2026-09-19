import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, request, session } from "../lib/api";
describe("API session boundary", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.unstubAllGlobals();
  });
  it("clears an expired session and signals the authentication boundary", async () => {
    session.set("expired");
    const listener = vi.fn();
    window.addEventListener("geopol:unauthorized", listener);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          Response.json({ detail: "La sesión expiró" }, { status: 401 }),
        ),
    );
    await expect(request("/dashboard")).rejects.toBeInstanceOf(ApiError);
    expect(session.get()).toBeNull();
    expect(listener).toHaveBeenCalledOnce();
    window.removeEventListener("geopol:unauthorized", listener);
  });
  it("preserves structured validation messages for accessible presentation", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          Response.json(
            { detail: [{ msg: "La razón debe tener al menos 8 caracteres" }] },
            { status: 422 },
          ),
        ),
    );
    await expect(request("/results/1")).rejects.toThrow(
      "La razón debe tener al menos 8 caracteres",
    );
  });
});
