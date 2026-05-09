/**
 * API client — type-safe wrapper cho openapi-fetch.
 *
 * Tự động inject Bearer token từ auth store.
 * Pattern: một function duy nhất thay vì class-based interceptors.
 */

import createClient from "openapi-fetch";
import type { paths } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Unauthenticated client — chỉ dùng cho login/register
export const api = createClient<paths>({ baseUrl: BASE_URL });

/**
 * Tạo authenticated client với token hiện tại.
 * Gọi trong mỗi request để luôn dùng token mới nhất.
 *
 * Usage:
 *   const client = getAuthClient();
 *   const { data, error } = await client.GET("/api/v1/tasks", { ... });
 */
export function getAuthClient(token: string) {
  return createClient<paths>({
    baseUrl: BASE_URL,
    headers: { Authorization: `Bearer ${token}` },
  });
}

export { BASE_URL };
