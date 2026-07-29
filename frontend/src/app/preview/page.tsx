"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Eye, ZoomIn, ZoomOut, Maximize2, Minimize2, ChevronLeft, ChevronRight, Columns2, BookOpen, ImageIcon } from "lucide-react";
import { cn, imageUrl } from "@/lib/utils";
import { mangaApi, type Manga, type Chapter, type Page } from "@/lib/api";

export default function PreviewPage() {
  const [mangas, setMangas] = useState<Manga[]>([]);
  const [selectedManga, setSelectedManga] = useState<string>("");
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [selectedChapter, setSelectedChapter] = useState<string>("");
  const [pages, setPages] = useState<Page[]>([]);
  const [currentPage, setCurrentPage] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [fullscreen, setFullscreen] = useState(false);
  const [mode, setMode] = useState<"single" | "side-by-side">("single");
  const [showOriginal, setShowOriginal] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => { mangaApi.list().then(setMangas).catch(() => {}); }, []);

  useEffect(() => {
    if (selectedManga) {
      mangaApi.listChapters(selectedManga).then(setChapters).catch(() => {});
      setSelectedChapter("");
      setPages([]);
      setCurrentPage(0);
    }
  }, [selectedManga]);

  useEffect(() => {
    if (selectedManga && selectedChapter) {
      mangaApi.listPages(selectedManga, selectedChapter).then(setPages).catch(() => {});
      setCurrentPage(0);
    }
  }, [selectedChapter, selectedManga]);

  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
      setFullscreen(true);
    } else {
      document.exitFullscreen().catch(() => {});
      setFullscreen(false);
    }
  }, []);

  useEffect(() => {
    const handler = () => setFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (!pages.length) return;
      if (e.key === "ArrowLeft") setCurrentPage((p) => Math.max(0, p - 1));
      if (e.key === "ArrowRight") setCurrentPage((p) => Math.min(pages.length - 1, p + 1));
      if (e.key === "+" || e.key === "=") setZoom((z) => Math.min(5, z + 0.25));
      if (e.key === "-") setZoom((z) => Math.max(0.25, z - 0.25));
      if (e.key === "f") toggleFullscreen();
      if (e.key === "o") setShowOriginal((s) => !s);
      if (e.key === "Escape" && fullscreen) toggleFullscreen();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [pages.length, toggleFullscreen, fullscreen]);

  const page = pages[currentPage];
  const hasTranslation = page?.is_translated;

  return (
    <div className={cn("space-y-4", fullscreen && "fixed inset-0 z-50 bg-background p-4")}>
      {!fullscreen && (
        <>
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold tracking-tight">Preview</h1>
              <p className="mt-1 text-muted-foreground">Review and compare translated pages</p>
            </div>
          </div>

          {/* Controls */}
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
              <Select value={selectedChapter} onValueChange={setSelectedChapter}>
                <SelectTrigger className="w-40"><SelectValue placeholder="Chapter..." /></SelectTrigger>
                <SelectContent>
                  {chapters.map((c) => (
                    <SelectItem key={c.id} value={c.id}>Ch.{c.chapter_number}{c.title ? ` - ${c.title}` : ""}</SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <div className="h-6 w-px bg-border" />

              <Button variant="outline" size="icon" onClick={() => setZoom((z) => Math.max(0.25, z - 0.25))}><ZoomOut className="h-4 w-4" /></Button>
              <span className="text-xs font-medium w-12 text-center">{Math.round(zoom * 100)}%</span>
              <Button variant="outline" size="icon" onClick={() => setZoom((z) => Math.min(5, z + 0.25))}><ZoomIn className="h-4 w-4" /></Button>

              <div className="h-6 w-px bg-border" />

              <Button variant={mode === "single" ? "default" : "outline"} size="sm" onClick={() => setMode("single")}>
                <ImageIcon className="h-4 w-4 mr-1" /> Single
              </Button>
              <Button variant={mode === "side-by-side" ? "default" : "outline"} size="sm" onClick={() => setMode("side-by-side")}>
                <Columns2 className="h-4 w-4 mr-1" /> Side-by-side
              </Button>

              <div className="h-6 w-px bg-border" />

              <Button variant={showOriginal ? "default" : "outline"} size="sm" onClick={() => setShowOriginal(!showOriginal)}>
                <Eye className="h-4 w-4 mr-1" /> {showOriginal ? "Show Translated" : "Show Original"}
              </Button>
              <Button variant="outline" size="icon" onClick={toggleFullscreen}>
                <Maximize2 className="h-4 w-4" />
              </Button>
            </CardContent>
          </Card>
        </>
      )}

      {/* Viewer */}
      {!selectedChapter ? (
        <Card>
          <CardContent className="flex flex-col items-center py-16">
            <Eye className="h-12 w-12 text-muted-foreground/50 mb-4" />
            <p className="text-lg font-medium">Select a manga and chapter</p>
            <p className="text-sm text-muted-foreground">Choose from the dropdowns above to preview translations</p>
          </CardContent>
        </Card>
      ) : pages.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center py-16">
            <BookOpen className="h-12 w-12 text-muted-foreground/50 mb-4" />
            <p className="text-lg font-medium">No pages yet</p>
            <p className="text-sm text-muted-foreground">Upload pages to this chapter to preview them</p>
          </CardContent>
        </Card>
      ) : (
        <>
          <div
            ref={containerRef}
            className={cn(
              "flex items-start justify-center gap-4 overflow-auto rounded-xl border bg-muted/30 p-4",
              fullscreen && "h-[calc(100vh-2rem)]"
            )}
            style={{ minHeight: fullscreen ? undefined : "60vh" }}
          >
            {mode === "side-by-side" && page ? (
              <>
                <div className="flex-1 max-w-xl" style={{ transform: `scale(${zoom})`, transformOrigin: "top center" }}>
                  <div className="rounded-lg border bg-card overflow-hidden">
                    <div className="bg-muted px-3 py-1 text-xs text-muted-foreground">Original</div>
                    <img
                      src={imageUrl(page.original_image_path)}
                      alt={`Page ${page.page_number} original`}
                      className="w-full"
                      onError={(e) => { const t = e.target as HTMLImageElement; t.style.border = "1px dashed #666"; t.alt = "Image not found"; }}
                    />
                  </div>
                </div>
                <div className="flex-1 max-w-xl" style={{ transform: `scale(${zoom})`, transformOrigin: "top center" }}>
                  <div className="rounded-lg border bg-card overflow-hidden">
                    <div className="bg-muted px-3 py-1 text-xs text-muted-foreground">
                      Translated {!hasTranslation && <Badge variant="warning" className="ml-2 text-xs">Not translated</Badge>}
                    </div>
                    <img
                      src={imageUrl(page.translated_image_path || page.original_image_path)}
                      alt={`Page ${page.page_number} translated`}
                      className="w-full"
                    />
                  </div>
                </div>
              </>
            ) : page ? (
              <div style={{ transform: `scale(${zoom})`, transformOrigin: "top center" }}>
                <div className="rounded-lg border bg-card overflow-hidden">
                  <img
                    src={imageUrl(showOriginal ? page.original_image_path : (page.translated_image_path || page.original_image_path))}
                    alt={`Page ${page.page_number}`}
                    className="w-full max-w-2xl"
                  />
                </div>
              </div>
            ) : null}
          </div>

          {/* Page Navigation */}
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Page {currentPage + 1} of {pages.length}
              {hasTranslation && <Badge variant="success" className="ml-2">Translated</Badge>}
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setCurrentPage((p) => Math.max(0, p - 1))} disabled={currentPage === 0}>
                <ChevronLeft className="h-4 w-4 mr-1" /> Previous
              </Button>
              <Button variant="outline" size="sm" onClick={() => setCurrentPage((p) => Math.min(pages.length - 1, p + 1))} disabled={currentPage >= pages.length - 1}>
                Next <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          </div>

          {/* Thumbnails */}
          <div className="flex gap-2 overflow-x-auto pb-2">
            {pages.map((p, i) => (
              <button
                key={p.id}
                onClick={() => setCurrentPage(i)}
                className={cn(
                  "shrink-0 w-16 h-24 rounded-lg border-2 overflow-hidden transition-all",
                  i === currentPage ? "border-primary ring-1 ring-primary" : "border-transparent hover:border-muted-foreground/30"
                )}
              >
                <img src={imageUrl(p.translated_image_path || p.original_image_path)} alt={`Page ${p.page_number}`} className="h-full w-full object-cover" />
              </button>
            ))}
          </div>

          {/* Keyboard shortcuts hint */}
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            <kbd className="rounded border bg-muted px-1.5 py-0.5">←</kbd><span>Prev</span>
            <kbd className="rounded border bg-muted px-1.5 py-0.5">→</kbd><span>Next</span>
            <kbd className="rounded border bg-muted px-1.5 py-0.5">+/-</kbd><span>Zoom</span>
            <kbd className="rounded border bg-muted px-1.5 py-0.5">F</kbd><span>Fullscreen</span>
            <kbd className="rounded border bg-muted px-1.5 py-0.5">O</kbd><span>Toggle Original</span>
          </div>
        </>
      )}
    </div>
  );
}
