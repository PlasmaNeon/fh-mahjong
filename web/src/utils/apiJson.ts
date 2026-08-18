/** A JSON error envelope: every API route returns `{ error }` on failure. */
export type ApiErrorBody = { error?: string }

/**
 * Parses a JSON response body, yielding `{}` when the body is absent or
 * malformed — a 500 with an HTML error page must not throw over the top of the
 * caller's own status handling.
 */
export async function readJsonBody<T = Record<string, unknown>>(
  response: Response,
): Promise<T & ApiErrorBody> {
  return (await response.json().catch(() => ({}))) as T & ApiErrorBody
}

/**
 * The server's error text when it sent one, otherwise the caller's fallback.
 * Uses `||`, not `??`, so an empty-string error also falls back — matching the
 * behaviour of every call site this replaces.
 */
export function errorMessage(data: ApiErrorBody, fallback: string): string {
  return data.error || fallback
}
