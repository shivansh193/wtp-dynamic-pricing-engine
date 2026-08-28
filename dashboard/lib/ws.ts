"use client";

import { useEffect, useRef, useState } from "react";
import { getAllSessions, wsBase } from "./api";
import type { SessionInfo, WsMessage } from "./types";

/**
 * Subscribe to /ws/sessions. Returns the running session list (seeded from
 * /sessions/all by the caller) kept live by websocket pushes, plus a
 * connection flag. Auto-reconnects with backoff.
 */
export function useSessionsFeed(
  initial: SessionInfo[],
  opts?: { onEvent?: (m: WsMessage) => void },
) {
  const [sessions, setSessions] = useState<SessionInfo[]>(initial);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);
  const onEvent = opts?.onEvent;

  // keep in sync if the caller reseeds (e.g. after an initial fetch)
  useEffect(() => {
    if (initial.length) setSessions(initial);
  }, [initial]);

  useEffect(() => {
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      const ws = new WebSocket(`${wsBase()}/ws/sessions`);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
        retryRef.current = 0;
      };
      ws.onclose = () => {
        setConnected(false);
        if (cancelled) return;
        const delay = Math.min(1000 * 2 ** retryRef.current, 15000);
        retryRef.current += 1;
        setTimeout(connect, delay);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (ev) => {
        let msg: WsMessage;
        try {
          msg = JSON.parse(ev.data);
        } catch {
          return;
        }
        onEvent?.(msg);
        if (!msg.session) return;
        const s = msg.session;
        setSessions((prev) => {
          const idx = prev.findIndex((p) => p.session_id === s.session_id);
          if (idx === -1) return [s, ...prev];
          const next = prev.slice();
          next[idx] = { ...next[idx], ...s };
          return next;
        });
      };
    };

    connect();
    return () => {
      cancelled = true;
      wsRef.current?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // fallback: while the socket is down, poll /sessions/all so the table still
  // updates (relevant on hosts where WebSockets are unreliable)
  useEffect(() => {
    if (connected) return;
    let alive = true;
    const poll = () =>
      getAllSessions()
        .then((r) => alive && r.sessions.length && setSessions(r.sessions))
        .catch(() => {});
    const id = setInterval(poll, 5000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [connected]);

  return { sessions, setSessions, connected };
}
