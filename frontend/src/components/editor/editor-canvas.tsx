"use client";

import * as React from "react";
import { BubbleOverlay } from "./bubble-overlay";
import type { BubbleData } from "@/lib/editor-store";
import { cn } from "@/lib/utils";

interface EditorCanvasProps {
  bubbles: BubbleData[];
  pageWidth: number;
  pageHeight: number;
  zoom: number;
  selectedId: string | null;
  onSelectBubble: (id: string | null) => void;
  onMoveBubble: (id: string, x: number, y: number) => void;
  onResizeBubble: (id: string, w: number, h: number) => void;
  onRotateBubble: (id: string, angle: number) => void;
  onTextChange: (id: string, text: string) => void;
  imageUrl?: string;
}

export function EditorCanvas({
  bubbles,
  pageWidth,
  pageHeight,
  zoom,
  selectedId,
  onSelectBubble,
  onMoveBubble,
  onResizeBubble,
  onRotateBubble,
  onTextChange,
  imageUrl,
}: EditorCanvasProps) {
  const canvasRef = React.useRef<HTMLDivElement>(null);

  // Deselect on canvas click
  const handleCanvasClick = React.useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) {
        onSelectBubble(null);
      }
    },
    [onSelectBubble]
  );

  return (
    <div className="flex items-center justify-center overflow-auto rounded-xl border bg-muted/30 p-4 min-h-[500px]" ref={canvasRef}>
      <div
        className="relative overflow-hidden rounded-lg bg-white shadow-2xl"
        style={{
          width: pageWidth * zoom,
          height: pageHeight * zoom,
          minWidth: pageWidth * zoom,
          minHeight: pageHeight * zoom,
        }}
      >
        {/* Page image background */}
        {imageUrl ? (
          <img
            src={imageUrl}
            alt="Page"
            className="absolute inset-0 h-full w-full object-contain"
            draggable={false}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center text-muted-foreground">
              <div className="mb-2 text-4xl">📄</div>
              <p className="text-sm">No page loaded. Upload or select a manga page to begin editing.</p>
            </div>
          </div>
        )}

        {/* Click capture for deselection */}
        <div
          className="absolute inset-0 z-[1]"
          onClick={handleCanvasClick}
        />

        {/* Bubble overlays */}
        {bubbles.map((bubble) => (
          <div
            key={bubble.id}
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              width: "100%",
              height: "100%",
              zIndex: bubble.isSelected ? 10 : 2,
            }}
          >
            <BubbleOverlay
              bubble={bubble}
              isSelected={bubble.isSelected}
              onSelect={onSelectBubble}
              onMove={onMoveBubble}
              onResize={onResizeBubble}
              onRotate={onRotateBubble}
              onTextChange={onTextChange}
              zoom={zoom}
            />
          </div>
        ))}

        {/* Empty state */}
        {bubbles.length === 0 && imageUrl && (
          <div className="absolute inset-0 z-[3] flex items-center justify-center pointer-events-none">
            <div className="rounded-xl bg-black/50 px-4 py-2 text-sm text-white backdrop-blur-sm">
              No bubbles detected. Double-click on the page to add one.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
