import { Blob as NodeBlob, File as NodeFile } from "node:buffer";
import { webcrypto } from "node:crypto";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  CHUNK_SIZE,
  fileFingerprint,
  getResume,
  uploadFile,
} from "../lib/upload";
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

  async function saveObsoleteResume() {
    const file = new NodeFile(
      ["address\nCALLE PRUEBA 10"],
      "synthetic.csv",
    ) as unknown as File;
    localStorage.setItem(
      "geopol.upload.resume",
      JSON.stringify({
        uploadId: "deleted-upload",
        filename: file.name,
        size: file.size,
        lastModified: file.lastModified,
        fingerprint: await fileFingerprint(file),
        userId: "user-1",
      }),
    );
    return file;
  }

  function jsonResponse(value: unknown, status = 200) {
    return new Response(JSON.stringify(value), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }

  it("starts a fresh upload for the same file when the saved upload no longer exists", async () => {
    const file = await saveObsoleteResume();
    const upload = {
      id: "new-upload",
      filename: file.name,
      size: file.size,
      offset: 0,
      status: "OPEN",
    };
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "No encontrado" }, 404))
      .mockResolvedValueOnce(jsonResponse(upload))
      .mockResolvedValueOnce(jsonResponse({ ...upload, offset: file.size }))
      .mockResolvedValueOnce(
        jsonResponse({ ...upload, offset: file.size, status: "COMPLETE" }),
      );
    vi.stubGlobal("fetch", fetch);
    const progress = vi.fn();

    const result = await uploadFile(file, "user-1", progress);

    expect(result.id).toBe("new-upload");
    expect(result.status).toBe("COMPLETE");
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      "/api/uploads/deleted-upload",
      "/api/uploads",
      "/api/uploads/new-upload",
      "/api/uploads/new-upload/complete",
    ]);
    expect(fetch.mock.calls[1][1].method).toBe("POST");
    expect(fetch.mock.calls[2][1].headers.get("Upload-Offset")).toBe("0");
    expect(fetch.mock.calls[2][1].body.size).toBe(file.size);
    expect(progress.mock.calls).toEqual([[0], [file.size]]);
    expect(getResume("user-1")?.uploadId).toBe("new-upload");
  });

  it("removes an obsolete resume even if creating the replacement upload fails", async () => {
    const file = await saveObsoleteResume();
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: "No encontrado" }, 404))
      .mockResolvedValueOnce(jsonResponse({ detail: "No disponible" }, 503));
    vi.stubGlobal("fetch", fetch);

    await expect(uploadFile(file, "user-1", vi.fn())).rejects.toMatchObject({
      status: 503,
    });
    expect(getResume("user-1")).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it.each([401, 403, 500, 0])(
    "preserves the resume and surfaces status %i without creating another upload",
    async (status) => {
      const file = await saveObsoleteResume();
      const fetch = vi.fn();
      if (status === 0) fetch.mockRejectedValueOnce(new Error("Disconnected"));
      else
        fetch.mockResolvedValueOnce(jsonResponse({ detail: "Error" }, status));
      vi.stubGlobal("fetch", fetch);

      await expect(uploadFile(file, "user-1", vi.fn())).rejects.toMatchObject({
        status,
      });
      expect(getResume("user-1")?.uploadId).toBe("deleted-upload");
      expect(fetch).toHaveBeenCalledTimes(1);
      expect(fetch.mock.calls[0][0]).toBe("/api/uploads/deleted-upload");
    },
  );
});
