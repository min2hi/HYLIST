/**
 * useSSE — Server-Sent Events hook (production-grade)
 *
 * Features:
 *  - Auto-reconnect với exponential backoff (0.5s → 30s)
 *  - Token injection qua query param (?token=...) vì EventSource
 *    không support custom headers (đây là limitation của Web API)
 *  - Type-safe event handlers
 *  - Cleanup tự động khi component unmount
 *  - Heartbeat detection: nếu không nhận event trong 60s → reconnect
 *
 * Usage:
 *  useSSE(`/api/v1/events/stream`, {
 *    tags_updated: (data) => queryClient.invalidateQueries(['tasks']),
 *    prediction_done: (data) => updatePrediction(data),
 *  });
 */

import { useEffect, useRef } from "react";
import { getToken } from "@/lib/auth/session";

export type SSEEventType =
  | "tags_updated"
  | "prediction_done"
  | "heartbeat"
  | "connected";

export type SSEHandler<T = unknown> = (data: T) => void;

export type SSEHandlers = {
  [K in SSEEventType]?: SSEHandler;
};

const INITIAL_RETRY_DELAY = 500;   // ms
const MAX_RETRY_DELAY = 30_000;    // ms
const HEARTBEAT_TIMEOUT = 60_000;  // ms — reconnect nếu im lặng 60s

export function useSSE(
  path: string,
  handlers: SSEHandlers,
  enabled = true
): void {
  const esRef = useRef<EventSource | null>(null);
  const retryDelayRef = useRef(INITIAL_RETRY_DELAY);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handlersRef = useRef(handlers);

  // Giữ handlers ref up-to-date mà không re-create EventSource
  useEffect(() => {
    handlersRef.current = handlers;
  }, [handlers]);

  useEffect(() => {
    if (!enabled) return;

    const connect = () => {
      // Cleanup old connection
      esRef.current?.close();
      clearTimeout(reconnectTimerRef.current!);
      clearTimeout(heartbeatTimerRef.current!);

      const token = getToken();
      const url = token
        ? `${path}?token=${encodeURIComponent(token)}`
        : path;

      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const fullUrl = `${apiBase}${url}`;

      const es = new EventSource(fullUrl);
      esRef.current = es;

      // Reset heartbeat timer
      const resetHeartbeat = () => {
        clearTimeout(heartbeatTimerRef.current!);
        heartbeatTimerRef.current = setTimeout(() => {
          console.warn("[SSE] Heartbeat timeout — reconnecting");
          connect();
        }, HEARTBEAT_TIMEOUT);
      };

      es.onopen = () => {
        console.info("[SSE] Connected to", path);
        retryDelayRef.current = INITIAL_RETRY_DELAY; // Reset backoff
        resetHeartbeat();
        handlersRef.current.connected?.({ connected: true });
      };

      // Named event handlers (SSE `event:` field)
      const eventTypes: SSEEventType[] = [
        "tags_updated",
        "prediction_done",
        "heartbeat",
        "connected",
      ];

      for (const eventType of eventTypes) {
        es.addEventListener(eventType, (e: MessageEvent) => {
          resetHeartbeat();
          try {
            const data = JSON.parse(e.data);
            handlersRef.current[eventType]?.(data);
          } catch {
            handlersRef.current[eventType]?.(e.data);
          }
        });
      }

      // Default message handler
      es.onmessage = (e) => {
        resetHeartbeat();
      };

      es.onerror = (err) => {
        console.warn("[SSE] Error — retrying in", retryDelayRef.current, "ms");
        es.close();
        clearTimeout(heartbeatTimerRef.current!);

        // Exponential backoff
        reconnectTimerRef.current = setTimeout(() => {
          retryDelayRef.current = Math.min(
            retryDelayRef.current * 2,
            MAX_RETRY_DELAY
          );
          connect();
        }, retryDelayRef.current);
      };
    };

    connect();

    return () => {
      esRef.current?.close();
      clearTimeout(reconnectTimerRef.current!);
      clearTimeout(heartbeatTimerRef.current!);
    };
  }, [path, enabled]);
}
