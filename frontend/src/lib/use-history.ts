"use client";

import { useState, useCallback, useRef } from "react";

const MAX_HISTORY = 50;

export interface HistoryEntry<T> {
  snapshot: T;
  timestamp: number;
  label: string;
}

export function useHistory<T>(initialState: T) {
  const [past, setPast] = useState<HistoryEntry<T>[]>([]);
  const [present, setPresent] = useState<T>(initialState);
  const [future, setFuture] = useState<HistoryEntry<T>[]>([]);
  const skipRef = useRef(false);

  const pushState = useCallback(
    (newState: T | ((prev: T) => T), label = "Edit") => {
      if (skipRef.current) {
        skipRef.current = false;
        return;
      }

      setPresent((current) => {
        const resolved = typeof newState === "function" ? (newState as (prev: T) => T)(current) : newState;

        setPast((prev) => {
          const entry: HistoryEntry<T> = {
            snapshot: structuredClone(current),
            timestamp: Date.now(),
            label,
          };
          return [...prev.slice(-(MAX_HISTORY - 1)), entry];
        });

        setFuture([]); // Clear redo on new action
        return resolved;
      });
    },
    []
  );

  const undo = useCallback(() => {
    if (past.length === 0) return;
    const previous = past[past.length - 1];
    setPast((prev) => prev.slice(0, -1));
    setFuture((prev) => [
      ...prev,
      { snapshot: structuredClone(present), timestamp: Date.now(), label: "Undo" },
    ]);
    skipRef.current = true;
    setPresent(previous.snapshot);
  }, [past, present]);

  const redo = useCallback(() => {
    if (future.length === 0) return;
    const next = future[future.length - 1];
    setFuture((prev) => prev.slice(0, -1));
    setPast((prev) => [
      ...prev,
      { snapshot: structuredClone(present), timestamp: Date.now(), label: "Redo" },
    ]);
    skipRef.current = true;
    setPresent(next.snapshot);
  }, [future, present]);

  const canUndo = past.length > 0;
  const canRedo = future.length > 0;

  const reset = useCallback((newState: T) => {
    setPast([]);
    setPresent(newState);
    setFuture([]);
  }, []);

  return {
    state: present,
    setState: pushState,
    undo,
    redo,
    reset,
    canUndo,
    canRedo,
    pastCount: past.length,
    futureCount: future.length,
    pastEntries: past,
  };
}
