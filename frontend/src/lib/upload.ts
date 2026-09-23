import { ApiError, post, request } from "./api";
import type { Upload } from "../types";
export const CHUNK_SIZE = 8 * 1024 * 1024;
const storageKey = "geopol.upload.resume";
export interface ResumeRecord {
  uploadId: string;
  filename: string;
  size: number;
  lastModified: number;
  fingerprint: string;
  userId: string;
}
const resumeKey = (scope?: string) =>
  scope ? `${storageKey}.${scope}` : storageKey;
export function getResume(userId: string, scope?: string): ResumeRecord | null {
  try {
    const saved = JSON.parse(
      localStorage.getItem(resumeKey(scope)) ?? "null",
    ) as ResumeRecord | null;
    return saved?.userId === userId ? saved : null;
  } catch {
    return null;
  }
}
export function clearResume(scope?: string) {
  localStorage.removeItem(resumeKey(scope));
}
export async function fileFingerprint(file: File) {
  // Verify every byte on reselect while keeping at most one 8 MiB block in memory.
  // This local digest of chunk digests is an identity guard, not the server's file SHA-256.
  const hashes: number[] = [];
  for (let offset = 0; offset < file.size; offset += CHUNK_SIZE) {
    const chunk = await file.slice(offset, offset + CHUNK_SIZE).arrayBuffer();
    const digest = await crypto.subtle.digest("SHA-256", chunk);
    hashes.push(...new Uint8Array(digest));
  }
  const hash = await crypto.subtle.digest("SHA-256", new Uint8Array(hashes));
  return Array.from(new Uint8Array(hash), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
}
export async function uploadFile(
  file: File,
  userId: string,
  onProgress: (offset: number) => void,
  signal?: AbortSignal,
  scope?: string,
): Promise<Upload> {
  const fingerprint = await fileFingerprint(file);
  const saved = getResume(userId, scope);
  let upload: Upload | undefined;
  if (
    saved &&
    saved.filename === file.name &&
    saved.size === file.size &&
    saved.fingerprint === fingerprint
  ) {
    try {
      upload = await request<Upload>(`/uploads/${saved.uploadId}`, { signal });
    } catch (error) {
      if (!(error instanceof ApiError) || error.status !== 404) throw error;
      clearResume(scope);
    }
  }
  if (!upload) {
    upload = await post<Upload>("/uploads", {
      filename: file.name,
      size: file.size,
    });
    localStorage.setItem(
      resumeKey(scope),
      JSON.stringify({
        uploadId: upload.id,
        filename: file.name,
        size: file.size,
        lastModified: file.lastModified,
        fingerprint,
        userId,
      } satisfies ResumeRecord),
    );
  }
  onProgress(upload.offset);
  while (upload.offset < file.size) {
    const previousOffset: number = upload.offset;
    upload = await request<Upload>(`/uploads/${upload.id}`, {
      method: "PATCH",
      headers: {
        "Upload-Offset": String(previousOffset),
        "Content-Type": "application/octet-stream",
      },
      body: file.slice(previousOffset, previousOffset + CHUNK_SIZE),
      signal,
    });
    if (upload.offset <= previousOffset)
      throw new Error(
        "El servidor no confirmó el bloque enviado. Vuelve a seleccionar el archivo para reanudar.",
      );
    onProgress(upload.offset);
  }
  const completed = await post<Upload>(`/uploads/${upload.id}/complete`);
  return completed;
}
