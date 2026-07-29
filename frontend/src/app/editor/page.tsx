"use client";

import * as React from "react";
import { useReducer, useCallback, useEffect } from "react";
import { EditorCanvas } from "@/components/editor/editor-canvas";
import { EditorToolbar } from "@/components/editor/editor-toolbar";
import { useHistory } from "@/lib/use-history";
import {
  editorReducer,
  createInitialState,
  type BubbleData,
  type EditorState,
} from "@/lib/editor-store";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Plus, FileUp, Hash } from "lucide-react";

export default function EditorPage() {
  // Main editor state
  const [state, dispatch] = useReducer(editorReducer, createInitialState(800, 1200));

  // Undo/redo history for bubble state
  const {
    state: historyBubbles,
    setState: setHistoryBubbles,
    undo,
    redo,
    reset: resetHistory,
    canUndo,
    canRedo,
    pastCount,
  } = useHistory<BubbleData[]>([]);

  // Sync history bubbles to editor state
  useEffect(() => {
    dispatch({ type: "SET_BUBBLES", bubbles: historyBubbles });
  }, [historyBubbles]);

  // Wrap dispatch to also push to history
  const dispatchWithHistory = useCallback(
    (action: any, historyLabel = "Edit") => {
      const prevBubbles = state.bubbles;
      dispatch(action);

      // After React processes the dispatch, push to history
      setTimeout(() => {
        setHistoryBubbles((current: BubbleData[]) => {
          // Compute the new state based on action
          const next = editorReducer(
            { ...state, bubbles: current },
            action
          );
          return next.bubbles;
        }, historyLabel);
      }, 0);
    },
    [state, setHistoryBubbles]
  );

  // ── Action handlers ──────────────────────────────────────────────
  const handleSelectBubble = useCallback(
    (id: string | null) => dispatch({ type: "SELECT_BUBBLE", id }),
    []
  );

  const handleMoveBubble = useCallback(
    (id: string, x: number, y: number) => {
      dispatch({ type: "MOVE_BUBBLE", id, x, y });
      setHistoryBubbles((prev: BubbleData[]) =>
        prev.map((b) => (b.id === id ? { ...b, x, y } : b)),
        "Move"
      );
    },
    [setHistoryBubbles]
  );

  const handleResizeBubble = useCallback(
    (id: string, width: number, height: number) => {
      dispatch({ type: "RESIZE_BUBBLE", id, width, height });
      setHistoryBubbles((prev: BubbleData[]) =>
        prev.map((b) => (b.id === id ? { ...b, width, height } : b)),
        "Resize"
      );
    },
    [setHistoryBubbles]
  );

  const handleRotateBubble = useCallback(
    (id: string, rotation: number) => {
      dispatch({ type: "ROTATE_BUBBLE", id, rotation });
      setHistoryBubbles((prev: BubbleData[]) =>
        prev.map((b) => (b.id === id ? { ...b, rotation } : b)),
        "Rotate"
      );
    },
    [setHistoryBubbles]
  );

  const handleTextChange = useCallback(
    (id: string, text: string) => {
      dispatch({ type: "UPDATE_TEXT", id, text });
      setHistoryBubbles((prev: BubbleData[]) =>
        prev.map((b) => (b.id === id ? { ...b, text } : b)),
        "Edit text"
      );
    },
    [setHistoryBubbles]
  );

  const handleFontChange = useCallback(
    (fontFamily: string) => {
      if (!state.selectedId) return;
      dispatch({ type: "CHANGE_FONT", id: state.selectedId, fontFamily });
      setHistoryBubbles((prev: BubbleData[]) =>
        prev.map((b) =>
          b.id === state.selectedId ? { ...b, fontFamily } : b
        ),
        "Change font"
      );
    },
    [state.selectedId, setHistoryBubbles]
  );

  const handleDeleteSelected = useCallback(() => {
    if (!state.selectedId) return;
    const id = state.selectedId;
    dispatch({ type: "DESELECT_ALL" });
    setHistoryBubbles(
      (prev: BubbleData[]) => prev.filter((b) => b.id !== id),
      "Delete bubble"
    );
  }, [state.selectedId, setHistoryBubbles]);

  const handleZoomChange = useCallback(
    (zoom: number) => dispatch({ type: "SET_ZOOM", zoom }),
    []
  );

  const handleResetZoom = useCallback(
    () => dispatch({ type: "SET_ZOOM", zoom: 1 }),
    []
  );

  const handleSave = useCallback(() => {
    // Persist to backend
    console.log("Saving bubbles:", state.bubbles);
    dispatch({ type: "SAVED" });
  }, [state.bubbles]);

  // ── Keyboard shortcuts ──────────────────────────────────────────
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "z" && !e.shiftKey) {
        e.preventDefault();
        undo();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "z" && e.shiftKey) {
        e.preventDefault();
        redo();
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        handleSave();
      }
      if (e.key === "Delete" || e.key === "Backspace") {
        if (state.selectedId && document.activeElement?.tagName !== "TEXTAREA") {
          handleDeleteSelected();
        }
      }
      if (e.key === "Escape") {
        dispatch({ type: "DESELECT_ALL" });
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [undo, redo, handleSave, handleDeleteSelected, state.selectedId]);

  const selectedBubble = state.bubbles.find((b) => b.id === state.selectedId);

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Page Editor</h1>
          <p className="text-sm text-muted-foreground">
            Drag to move · Double-click to edit text · Drag handles to resize/rotate
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={state.isDirty ? "warning" : "success"}>
            {state.isDirty ? "Unsaved changes" : "All saved"}
          </Badge>
          <Badge variant="secondary">
            {state.bubbles.length} bubbles
          </Badge>
        </div>
      </div>

      {/* Toolbar */}
      <EditorToolbar
        canUndo={canUndo}
        canRedo={canRedo}
        onUndo={undo}
        onRedo={redo}
        zoom={state.zoom}
        onZoomChange={handleZoomChange}
        isDirty={state.isDirty}
        onSave={handleSave}
        onResetZoom={handleResetZoom}
        selectedBubbleId={state.selectedId}
        selectedFont={selectedBubble?.fontFamily || "manga.ttf"}
        onFontChange={handleFontChange}
        onDeleteSelected={handleDeleteSelected}
        pastCount={pastCount}
      />

      {/* Canvas */}
      <div className="flex-1">
        <EditorCanvas
          bubbles={state.bubbles}
          pageWidth={state.pageWidth}
          pageHeight={state.pageHeight}
          zoom={state.zoom}
          selectedId={state.selectedId}
          onSelectBubble={handleSelectBubble}
          onMoveBubble={handleMoveBubble}
          onResizeBubble={handleResizeBubble}
          onRotateBubble={handleRotateBubble}
          onTextChange={handleTextChange}
        />
      </div>

      {/* Selected bubble details */}
      {selectedBubble && (
        <Card className="fixed bottom-4 right-4 w-72 shadow-xl">
          <CardContent className="p-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-semibold">Bubble Details</h4>
                <Badge variant="outline" className="text-[10px]">
                  {selectedBubble.bubbleType}
                </Badge>
              </div>
              <div className="grid grid-cols-2 gap-1 text-xs text-muted-foreground">
                <span>Position: {Math.round(selectedBubble.x)}, {Math.round(selectedBubble.y)}</span>
                <span>Size: {Math.round(selectedBubble.width)}×{Math.round(selectedBubble.height)}</span>
                <span>Rotation: {Math.round(selectedBubble.rotation)}°</span>
                <span>Font: {selectedBubble.fontFamily}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
