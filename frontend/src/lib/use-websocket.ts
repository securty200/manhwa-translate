"use client";

import { useEffect, useRef, useCallback, useState } from "react";

const WS_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1")
  .replace("http://", "ws://")
  .replace("https://", "wss://")
  .replace("/api/v1", "/api/v1/ws");

export interface JobProgressEvent {
  type: string;
  job_id: string;
  status: string;
  progress: number;
  current_page?: number;
  total_pages?: number;
  message?: string;
  page_id?: string;
  processing_time_ms?: number;
  timestamp: string;
}

/**
 * Subscribe to real-time progress updates for a specific job via WebSocket.
 * Falls back gracefully if the WebSocket connection fails.
 */
export function useJobProgress(jobId: string | null) {
  const [event, setEvent] = useState<JobProgressEvent | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    if (!jobId) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(`${WS_BASE}/progress/${jobId}`);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        // Reconnect after 3 seconds
        if (reconnectRef.current) clearTimeout(reconnectRef.current);
        reconnectRef.current = setTimeout(connect, 3000);
      };
      ws.onerror = () => {
        setConnected(false);
      };
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.type === "heartbeat") return;
          if (data.type === "pong") return;
          setEvent(data);
        } catch {
          // Ignore non-JSON messages
        }
      };
    } catch {
      setConnected(false);
    }
  }, [jobId]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
      setConnected(false);
    };
  }, [connect]);

  return { event, connected };
}

/**
 * Subscribe to all job events globally via WebSocket.
 */
export function useGlobalJobEvents() {
  const [events, setEvents] = useState<JobProgressEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    try {
      const ws = new WebSocket(`${WS_BASE}/global`);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);
      ws.onclose = () => setConnected(false);
      ws.onerror = () => setConnected(false);
      ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          if (data.type === "heartbeat" || data.type === "pong") return;
          setEvents((prev) => [...prev.slice(-99), data]);
        } catch {
          // Ignore
        }
      };

      return () => {
        ws.onclose = null;
        ws.close();
      };
    } catch {
      setConnected(false);
    }
  }, []);

  return { events, connected };
}
