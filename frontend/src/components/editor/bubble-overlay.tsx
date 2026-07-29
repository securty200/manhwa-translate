"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import type { BubbleData } from "@/lib/editor-store";
import { GripVertical, RotateCw, Move } from "lucide-react";

interface BubbleOverlayProps {
  bubble: BubbleData;
  isSelected: boolean;
  onSelect: (id: string) => void;
  onMove: (id: string, x: number, y: number) => void;
  onResize: (id: string, w: number, h: number) => void;
  onRotate: (id: string, angle: number) => void;
  onTextChange: (id: string, text: string) => void;
  zoom: number;
}

export function BubbleOverlay({
  bubble,
  isSelected,
  onSelect,
  onMove,
  onResize,
  onRotate,
  onTextChange,
  zoom,
}: BubbleOverlayProps) {
  const overlayRef = React.useRef<HTMLDivElement>(null);
  const [editing, setEditing] = React.useState(false);
  const [editText, setEditText] = React.useState(bubble.text);
  const dragRef = React.useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null);
  const resizeRef = React.useRef<{ startX: number; startY: number; origW: number; origH: number } | null>(null);
  const rotateRef = React.useRef<{ startX: number; startY: number; origAngle: number } | null>(null);

  // Sync edit text when bubble text changes externally (undo/redo)
  React.useEffect(() => {
    if (!editing) setEditText(bubble.text);
  }, [bubble.text, editing]);

  // ── Drag to Move ─────────────────────────────────────────────────
  const handleMoveStart = React.useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const rect = overlayRef.current?.getBoundingClientRect();
      if (!rect) return;
      dragRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        origX: bubble.x,
        origY: bubble.y,
      };
      const handleMove = (ev: PointerEvent) => {
        if (!dragRef.current) return;
        const dx = (ev.clientX - dragRef.current.startX) / zoom;
        const dy = (ev.clientY - dragRef.current.startY) / zoom;
        onMove(bubble.id, dragRef.current.origX + dx, dragRef.current.origY + dy);
      };
      const handleUp = () => {
        dragRef.current = null;
        window.removeEventListener("pointermove", handleMove);
        window.removeEventListener("pointerup", handleUp);
      };
      window.addEventListener("pointermove", handleMove);
      window.addEventListener("pointerup", handleUp);
    },
    [bubble.id, bubble.x, bubble.y, onMove, zoom]
  );

  // ── Resize ──────────────────────────────────────────────────────────
  const handleResizeStart = React.useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      resizeRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        origW: bubble.width,
        origH: bubble.height,
      };
      const handleMove = (ev: PointerEvent) => {
        if (!resizeRef.current) return;
        const dw = (ev.clientX - resizeRef.current.startX) / zoom;
        const dh = (ev.clientY - resizeRef.current.startY) / zoom;
        onResize(bubble.id, resizeRef.current.origW + dw, resizeRef.current.origH + dh);
      };
      const handleUp = () => {
        resizeRef.current = null;
        window.removeEventListener("pointermove", handleMove);
        window.removeEventListener("pointerup", handleUp);
      };
      window.addEventListener("pointermove", handleMove);
      window.addEventListener("pointerup", handleUp);
    },
    [bubble.id, bubble.width, bubble.height, onResize, zoom]
  );

  // ── Rotate ─────────────────────────────────────────────────────────
  const handleRotateStart = React.useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const rect = overlayRef.current?.getBoundingClientRect();
      if (!rect) return;
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      rotateRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        origAngle: bubble.rotation,
      };
      const handleMove = (ev: PointerEvent) => {
        if (!rotateRef.current) return;
        const angle1 = Math.atan2(rotateRef.current.startY - cy, rotateRef.current.startX - cx);
        const angle2 = Math.atan2(ev.clientY - cy, ev.clientX - cx);
        const delta = (angle2 - angle1) * (180 / Math.PI);
        onRotate(bubble.id, rotateRef.current.origAngle + delta);
      };
      const handleUp = () => {
        rotateRef.current = null;
        window.removeEventListener("pointermove", handleMove);
        window.removeEventListener("pointerup", handleUp);
      };
      window.addEventListener("pointermove", handleMove);
      window.addEventListener("pointerup", handleUp);
    },
    [bubble.id, bubble.rotation, onRotate]
  );

  // ── Double-click to edit text ─────────────────────────────────────
  const handleDoubleClick = React.useCallback(() => {
    setEditing(true);
    setEditText(bubble.text);
  }, [bubble.text]);

  const handleTextSave = React.useCallback(() => {
    setEditing(false);
    if (editText !== bubble.text) {
      onTextChange(bubble.id, editText);
    }
  }, [editText, bubble.id, bubble.text, onTextChange]);

  const handleTextKeyDown = React.useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleTextSave();
      }
      if (e.key === "Escape") {
        setEditText(bubble.text);
        setEditing(false);
      }
    },
    [handleTextSave, bubble.text]
  );

  return (
    <div
      ref={overlayRef}
      className={cn(
        "absolute cursor-move group",
        isSelected && "z-10"
      )}
      style={{
        left: bubble.x,
        top: bubble.y,
        width: bubble.width,
        height: bubble.height,
        transform: `rotate(${bubble.rotation}deg)`,
        transformOrigin: "center center",
      }}
      onClick={() => onSelect(bubble.id)}
      onDoubleClick={handleDoubleClick}
      onPointerDown={(e) => {
        onSelect(bubble.id);
        handleMoveStart(e);
      }}
    >
      {/* Bubble background */}
      <div
        className={cn(
          "absolute inset-0 rounded-lg border-2 transition-colors",
          isSelected
            ? "border-primary bg-primary/5 shadow-lg shadow-primary/20"
            : "border-transparent bg-white/5 group-hover:border-primary/30"
        )}
      />

      {/* Text content */}
      {editing ? (
        <textarea
          className="absolute inset-2 resize-none rounded-md bg-background/95 p-1 text-xs font-medium outline-none ring-1 ring-primary z-20"
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          onBlur={handleTextSave}
          onKeyDown={handleTextKeyDown}
          autoFocus
          style={{ fontSize: Math.max(8, bubble.fontSize * 0.5) }}
        />
      ) : (
        <div
          className="absolute inset-2 flex items-center justify-center overflow-hidden text-center text-xs font-medium text-foreground/80 pointer-events-none"
          style={{ fontSize: Math.max(7, bubble.fontSize * 0.5) }}
        >
          <span className="line-clamp-4">{bubble.text}</span>
        </div>
      )}

      {/* Selection handles */}
      {isSelected && (
        <>
          {/* Move handle top-left */}
          <div
            className="absolute -left-3 -top-3 z-20 flex h-6 w-6 cursor-grab items-center justify-center rounded-full bg-primary text-primary-foreground shadow-md active:cursor-grabbing"
            onPointerDown={handleMoveStart}
          >
            <Move className="h-3 w-3" />
          </div>

          {/* Resize handle bottom-right */}
          <div
            className="absolute -bottom-3 -right-3 z-20 flex h-6 w-6 cursor-nwse-resize items-center justify-center rounded-full bg-primary text-primary-foreground shadow-md"
            onPointerDown={handleResizeStart}
          >
            <GripVertical className="h-3 w-3" />
          </div>

          {/* Rotate handle top-right */}
          <div
            className="absolute -right-3 -top-8 z-20 flex h-5 w-5 cursor-grab items-center justify-center rounded-full bg-amber-500 text-white shadow-md active:cursor-grabbing"
            onPointerDown={handleRotateStart}
          >
            <RotateCw className="h-3 w-3" />
          </div>

          {/* Bubble info label */}
          <div className="absolute -top-6 left-0 z-20 whitespace-nowrap rounded bg-primary/90 px-1.5 py-0.5 text-[10px] text-primary-foreground shadow-sm">
            {Math.round(bubble.width)}×{Math.round(bubble.height)} · {Math.round(bubble.rotation)}°
          </div>
        </>
      )}
    </div>
  );
}
