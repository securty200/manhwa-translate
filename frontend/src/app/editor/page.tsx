"use client";

import * as React from "react";
import { useReducer, useCallback, useEffect, useState } from "react";
import { EditorCanvas } from "@/components/editor/editor-canvas";
import { EditorToolbar } from "@/components/editor/editor-toolbar";
import { useHistory } from "@/lib/use-history";
import {
  editorReducer,
  createInitialState,
  createBubble,
  type BubbleData,
} from "@/lib/editor-store";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Loader as Loader2 } from "lucide-react";
import { mangaApi, type Manga, type Chapter, type Page } from "@/lib/api";
import { imageUrl } from "@/lib/utils";

export default function EditorPage() {
  // Manga/chapter/page selection state
  const [mangas, setMangas] = useState<Manga[]>([]);
  const [selectedManga, setSelectedManga] = useState<string>("");
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedChapter, setSelectedChapter] = useState<string>("");
  const [pages, setPages] = useState<Page[]>([]);
  const [selectedPageId, setSelectedPageId] = useState<string>("");
  const [loadingBubbles, setLoadingBubbles] = useState(false);

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

  // Load manga list on mount
  useEffect(() => {
    mangaApi.list().then(setMangas).catch(() => {});
  }, []);

  // Load chapters when manga changes
  useEffect(() => {
    if (selectedManga) {
      mangaApi.listChapters(selectedManga).then(setChapters).catch(() => {});
      setSelectedChapter("");
      setPages([]);
      setSelectedPageId("");
    }
  }, [selectedManga]);

  // Load pages when chapter changes
  useEffect(() => {
    if (selectedManga && selectedChapter) {
      mangaApi.listPages(selectedManga, selectedChapter).then(setPages).catch(() => {});
      setSelectedPageId("");
    }
  }, [selectedChapter, selectedManga]);

  // Load bubbles from backend when page changes
  const loadPageBubbles = useCallback(async (pageId: string) => {
    if (!pageId) return;
    setLoadingBubbles(true);
    try {
      const resp = await fetch(
        `/api/manga/${selectedManga}/chapters/${selectedChapter}/bubbles`,
      );
      if (resp.ok) {
        const allBubbles = await resp.json();
        const pageBubbles = allBubbles.filter((b: any) => b.page_id === pageId);
        const bubbleData: BubbleData[] = pageBubbles.map((b: any) => ({
          id: b.id,
          x: b.x,
          y: b.y,
          width: b.width,
          height: b.height,
          rotation: b.rotation || 0,
          text: b.translated_text || "",
          originalText: b.original_text || "",
          fontFamily: "manga.ttf",
          fontSize: 16,
          bubbleType: b.bubble_type || "speech",
          isSelected: false,
        }));
        resetHistory(bubbleData);
      } else {
        resetHistory([]);
      }
    } catch {
      resetHistory([]);
    } finally {
      setLoadingBubbles(false);
    }
  }, [selectedManga, selectedChapter, resetHistory]);

  useEffect(() => {
    if (selectedPageId) {
      loadPageBubbles(selectedPageId);
    } else {
      resetHistory([]);
    }
  }, [selectedPageId, loadPageBubbles, resetHistory]);

  // Update page size when page changes
  const currentPage = pages.find((p) => p.id === selectedPageId);
  useEffect(() => {
    if (currentPage?.width && currentPage?.height) {
      dispatch({ type: "SET_PAGE_SIZE", width: currentPage.width, height: currentPage.height });
    }
  }, [currentPage]);

  // ── Action handlers ──────────────────────────────────────────────
  const handleSelectBubble = useCallback(
    (id: string | null) => dispatch({ type: "SELECT_BUBBLE", id }),
    []
  );

  const handleAddBubble = useCallback(() => {
    const cx = state.pageWidth / 2 - 75;
    const cy = state.pageHeight / 2 - 40;
    const bubble = createBubble(cx, cy);
    dispatch({ type: "ADD_BUBBLE", bubble });
    setHistoryBubbles((prev: BubbleData[]) => [...prev, bubble], "Add bubble");
  }, [state.pageWidth, state.pageHeight, setHistoryBubbles]);

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
    dispatch({ type: "SAVED" });
  }, []);

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
  const currentImageUrl = currentPage ? imageUrl(currentPage.original_image_path) : undefined;

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

      {/* Page selector */}
      <Card>
        <CardContent className="p-3 flex items-center gap-3 flex-wrap">
          <Select value={selectedManga} onValueChange={setSelectedManga}>
            <SelectTrigger className="w-48"><SelectValue placeholder="Select manga..." /></SelectTrigger>
            <SelectContent>
              {mangas.map((m) => (
                <SelectItem key={m.id} value={m.id}>{m.title}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={selectedChapter} onValueChange={setSelectedChapter} disabled={!selectedManga}>
            <SelectTrigger className="w-40"><SelectValue placeholder="Chapter..." /></SelectTrigger>
            <SelectContent>
              {chapters.map((c) => (
                <SelectItem key={c.id} value={c.id}>Ch.{c.chapter_number}{c.title ? ` - ${c.title}` : ""}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={selectedPageId} onValueChange={setSelectedPageId} disabled={!selectedChapter}>
            <SelectTrigger className="w-36"><SelectValue placeholder="Page..." /></SelectTrigger>
            <SelectContent>
              {pages.map((p) => (
                <SelectItem key={p.id} value={p.id}>Page {p.page_number}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="h-6 w-px bg-border" />
          <Button size="sm" onClick={handleAddBubble} disabled={!selectedPageId}>
            <Plus className="h-4 w-4 mr-1" /> Add Bubble
          </Button>
        </CardContent>
      </Card>

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
        {loadingBubbles ? (
          <div className="flex h-full items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
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
            imageUrl={currentImageUrl}
          />
        )}
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
