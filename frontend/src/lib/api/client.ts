import createClient from "openapi-fetch";
import type { paths } from "./types";

export const api = createClient<paths>({
  baseUrl: (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000") + "/api/v1",
});

// Inject auth token tu Zustand store (cookie-based) vao moi request
api.use({
  onRequest({ request }) {
    if (typeof window !== "undefined") {
      // Import dong de tranh circular deps voi session.ts
      const Cookies = require("js-cookie") as { get: (k: string) => string | undefined };
      const token = Cookies.get("hylist_token");
      if (token) {
        request.headers.set("Authorization", `Bearer ${token}`);
      }
    }
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401 && typeof window !== "undefined") {
      window.location.href = "/login";
    }
    return response;
  },
});
