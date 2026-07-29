"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { FONT_OPTIONS } from "@/lib/editor-store";
import {
  Undo2,
  Redo2,
  Save,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  Trash2,
  History,
  CheckCircle2,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface EditorToolbarProps {
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  zoom: number;
  onZoomChange: (zoom: number) => void;
  isDirty: boolean;
  onSave: () => void;
  onResetZoom: () => void;
  selectedBubbleId: string | null;
  selectedFont: string;
  onFontChange: (font: string) => void;
  onDeleteSelected: () => void;
  pastCount: number;
}

export function EditorToolbar({
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  zoom,
  onZoomChange,
  isDirty,
  onSave,
  onResetZoom,
  selectedBubbleId,
  selectedFont,
  onFontChange,
  onDeleteSelected,
  pastCount,
}: EditorToolbarProps) {
  return (
    <div className="flex items-center gap-1.5 rounded-xl border bg-card p-2 shadow-sm">
      {/* Undo/Redo */}
      <Button variant="ghost" size="icon" onClick={onUndo} disabled={!canUndo} title="Undo (Ctrl+Z)">
        <Undo2 className="h-4 w-4" />
      </Button>
      <Button variant="ghost" size="icon" onClick={onRedo} disabled={!canRedo} title="Redo (Ctrl+Shift+Z)">
        <Redo2 className="h-4 w-4" />
      </Button>

      <div className="mx-1 h-6 w-px bg-border" />

      {/* Font selector */}
      <Select value={selectedFont} onValueChange={onFontChange} disabled={!selectedBubbleId}>
        <SelectTrigger className="h-8 w-[140px] text-xs">
          <SelectValue placeholder="Font" />
        </SelectTrigger>
        <SelectContent>
          {FONT_OPTIONS.map((f) => (
            <SelectItem key={f.value} value={f.value} className="text-xs">
              {f.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="mx-1 h-6 w-px bg-border" />

      {/* Zoom */}
      <Button variant="ghost" size="icon" onClick={() => onZoomChange(zoom - 0.1)} title="Zoom out">
        <ZoomOut className="h-4 w-4" />
      </Button>
      <button
        onClick={onResetZoom}
        className="min-w-[50px] text-center text-xs font-medium text-muted-foreground hover:text-foreground"
        title="Reset zoom to 100%"
      >
        {Math.round(zoom * 100)}%
      </button>
      <Button variant="ghost" size="icon" onClick={() => onZoomChange(zoom + 0.1)} title="Zoom in">
        <ZoomIn className="h-4 w-4" />
      </Button>

      <div className="mx-1 h-6 w-px bg-border" />

      {/* Delete */}
      <Button
        variant="ghost"
        size="icon"
        onClick={onDeleteSelected}
        disabled={!selectedBubbleId}
        title="Delete selected bubble (Del)"
        className="text-destructive hover:text-destructive"
      >
        <Trash2 className="h-4 w-4" />
      </Button>

      <div className="flex-1" />

      {/* History count */}
      <div className="flex items-center gap-1 text-xs text-muted-foreground" title="Undo history entries">
        <History className="h-3 w-3" />
        <span>{pastCount}</span>
      </div>

      {/* Save button */}
      <Button
        onClick={onSave}
        disabled={!isDirty}
        size="sm"
        className={cn(
          "gap-1.5 transition-all",
          isDirty ? "bg-primary" : "bg-muted text-muted-foreground"
        )}
      >
        {isDirty ? (
          <>
            <Save className="h-4 w-4" />
            Save
          </>
        ) : (
          <>
            <CheckCircle2 className="h-4 w-4" />
            Saved
          </>
        )}
      </Button>
    </div>
  );
}
