import { Blob as NodeBlob, File as NodeFile } from "node:buffer";
import { webcrypto } from "node:crypto";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CHUNK_SIZE, getResume, uploadFile } from "../lib/upload";
import { session } from "../lib/api";

describe("resumable uploads", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    vi.stubGlobal("Blob", NodeBlob);
    vi.stubGlobal("crypto", webcrypto);
  });
  it("resumes from the confirmed server offset after an interrupted chunk without restarting the upload", async () => {
    const file = new NodeFile(
      [new Uint8Array(CHUNK_SIZE + 17)],
      "synthetic.csv",
    ) as unknown as File;
    session.set("private-session");
    const response = (value: unknown) =>
      new Response(JSON.stringify(value), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        response({
          id: "up-1",
          filename: file.name,
          size: file.size,
          offset: 0,
          status: "OPEN",
        }),
      )
      .mockResolvedValueOnce(
        response({
          id: "up-1",
          filename: file.name,
          size: file.size,
          offset: CHUNK_SIZE,
          status: "OPEN",
        }),
      )
      .mockRejectedValueOnce(new Error("Disconnected"));
    vi.stubGlobal("fetch", fetch);
    const progress = vi.fn();
    await expect(uploadFile(file, "user-1", progress)).rejects.toThrow(
      "No se pudo conectar",
    );
    expect(getResume("user-1")?.uploadId).toBe("up-1");
    expect(getResume("other-user")).toBeNull();
    expect(fetch.mock.calls[1][1].body.size).toBe(CHUNK_SIZE);
    expect(fetch.mock.calls[1][1].headers.get("Authorization")).toBe(
      "Bearer private-session",
    );
    fetch
      .mockResolvedValueOnce(
        response({
          id: "up-1",
          filename: file.name,
          size: file.size,
          offset: CHUNK_SIZE,
          status: "OPEN",
        }),
      )
      .mockResolvedValueOnce(
        response({
          id: "up-1",
          filename: file.name,
          size: file.size,
          offset: file.size,
          status: "OPEN",
        }),
      )
      .mockResolvedValueOnce(
        response({
          id: "up-1",
          filename: file.name,
          size: file.size,
          offset: file.size,
          status: "COMPLETE",
          profile: { columns: [] },
        }),
      );
    const result = await uploadFile(file, "user-1", progress);
    expect(result.status).toBe("COMPLETE");
    expect(fetch.mock.calls[3][0]).toBe("/api/uploads/up-1");
    expect(fetch.mock.calls[4][1].headers.get("Upload-Offset")).toBe(
      String(CHUNK_SIZE),
    );
    expect(fetch.mock.calls[4][1].body.size).toBe(17);
    expect(
      fetch.mock.calls.filter(
        ([url, options]) => url === "/api/uploads" && options.method === "POST",
      ),
    ).toHaveLength(1);
  });
});
