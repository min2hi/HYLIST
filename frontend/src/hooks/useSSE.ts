/**
 * useSSE — Production-grade Server-Sent Events hook.
 *
 * Pattern dùng tại: Linear, Vercel, Loom (real-time update systems).
 *
 * Features:
 *   - Auto-reconnect với exponential backoff (0.5s → 1s → 2s → max 30s)
 *   - Token tự động inject từ Zustand auth store qua query param
 *     (EventSource không support custom headers — ADR-001)
 *   - Typed event handlers map
 *   - Connection state tracking cho UI feedback
 *   - Cleanup on unmount (no memory leaks)
 *
 * Usage:
 *   useSSE("/api/v1/events/stream", {
 *     tags_updated: (data) => { ... },
 *     prediction_done: (data) => { ... },
 *   }, !!token);
 */

import { useEffect, useRef, useState } from "react";
import { useAuthStore } from "@/lib/auth/session";

// ─── Event Handler Map ─────────────────────────────────────────────────────────

type SSEHandlers = {
  tags_updated?: (data: unknown) => void;
  prediction_done?: (data: unknown) => void;
  heartbeat?: (data: unknown) => void;
  [key: string]: ((data: unknown) => void) | undefined;
};

export type SSEConnectionState = "connecting" | "connected" | "disconnected" | "error";

// ─── Config ────────────────────────────────────────────────────────────────────

const INITIAL_RETRY_MS = 500;
const MAX_RETRY_MS = 30_000;
const BACKOFF_FACTOR = 2;

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ─── Hook ──────────────────────────────────────────────────────────────────────

/**
 * @param path   - SSE endpoint path, e.g. "/api/v1/events/stream"
 * @param handlers - Event handlers keyed by event type
 * @param enabled - Set to false to pause connection (e.g. when logged out)
 */
export function useSSE(
  path: string,
  handlers: SSEHandlers,
  enabled: boolean = true,
): { connectionState: SSEConnectionState } {
  const [connectionState, setConnectionState] = useState<SSEConnectionState>("disconnected");

  // Ref để tránh stale closure trong callbacks
  const handlersRef = useRef<SSEHandlers>(handlers);
  handlersRef.current = handlers;

  const esRef = useRef<EventSource | null>(null);
  const retryMsRef = useRef(INITIAL_RETRY_MS);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const connect = () => {
      // Lấy token tươi mỗi lần connect (tránh dùng stale token)
      const token = useAuthStore.getState().token;
      if (!token) return;

      const url = `${API_BASE}${path}?token=${encodeURIComponent(token)}`;
      const es = new EventSource(url);
      esRef.current = es;
      setConnectionState("connecting");

      es.onopen = () => {
        setConnectionState("connected");
        retryMsRef.current = INITIAL_RETRY_MS; // Reset backoff on success
      };

      // Đăng ký dynamic handlers
      const registeredEvents = new Set<string>();
      for (const eventType of Object.keys(handlersRef.current)) {
        es.addEventListener(eventType, (e: MessageEvent) => {
          try {
            const data = JSON.parse(e.data) as unknown;
            handlersRef.current[eventType]?.(data);
          } catch {
            console.warn(`[SSE] Parse error for event "${eventType}":`, e.data);
          }
        });
        registeredEvents.add(eventType);
      }

      es.onerror = () => {
        setConnectionState("error");
        es.close();
        esRef.current = null;

        // Exponential backoff reconnect
        const delay = retryMsRef.current;
        retryMsRef.current = Math.min(delay * BACKOFF_FACTOR, MAX_RETRY_MS);

        retryTimerRef.current = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      retryTimerRef.current && clearTimeout(retryTimerRef.current);
      esRef.current?.close();
      esRef.current = null;
      setConnectionState("disconnected");
    };
  }, [path, enabled]); // Re-connect khi path thay đổi

  return { connectionState };
}
