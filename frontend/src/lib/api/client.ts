import createClient from "openapi-fetch";
import type { paths } from "./types";

export const api = createClient<paths>({
  baseUrl: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
});

// Middleware for attaching Auth token
api.use({
  onRequest({ request }) {
    if (typeof window !== "undefined") {
      const token = localStorage.getItem("hylist_access_token");
      if (token) {
        request.headers.set("Authorization", `Bearer ${token}`);
      }
    }
    return request;
  },
  onResponse({ response }) {
    if (response.status === 401) {
      if (typeof window !== "undefined") {
        localStorage.removeItem("hylist_access_token");
        // Có thể emit event hoặc redirect ra login ở đây
      }
    }
    return response;
  },
});
