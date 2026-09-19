const TOKEN_KEY = "geopol.session";
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export const session = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (session.get()) headers.set("Authorization", `Bearer ${session.get()}`);
  if (
    options.body &&
    typeof options.body === "string" &&
    !headers.has("Content-Type")
  )
    headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...options, headers });
  } catch {
    throw new ApiError(
      "No se pudo conectar con el servidor. Comprueba la conexión e inténtalo de nuevo.",
      0,
    );
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : Array.isArray(body?.detail)
          ? body.detail.map((e: { msg: string }) => e.msg).join(". ")
          : `La solicitud no se pudo completar (${response.status}).`;
    if (response.status === 401 && path !== "/auth/login") {
      session.clear();
      window.dispatchEvent(new Event("geopol:unauthorized"));
    }
    throw new ApiError(detail, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
export const post = <T>(path: string, body: unknown = {}) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });

export async function downloadAuthenticated(
  path: string,
  filename: string,
): Promise<void> {
  const response = await fetch(`/api${path}`, {
    headers: { Authorization: `Bearer ${session.get() ?? ""}` },
  });
  if (!response.ok)
    throw new ApiError(
      "No se pudo descargar el archivo. Comprueba tu sesión y los permisos.",
      response.status,
    );
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
