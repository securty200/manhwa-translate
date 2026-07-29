"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { ChevronLeft, Plus, Trash2, BookOpen, Languages, Clock, Image as ImageIcon, Play, Download, Loader as Loader2, CircleAlert as AlertCircle } from "lucide-react";
import { cn, imageUrl } from "@/lib/utils";
import { mangaApi, translationApi, type Manga, type Chapter, type Page } from "@/lib/api";

export default function ProjectDetailPage() {
  const params = useParams();
  const router = useRouter();
  const mangaId = params.id as string;

  const [manga, setManga] = useState<Manga | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddChapter, setShowAddChapter] = useState(false);
  const [newChapterNum, setNewChapterNum] = useState("");
  const [newChapterTitle, setNewChapterTitle] = useState("");
  const [chapterPages, setChapterPages] = useState<Record<string, Page[]>>({});
  const [translating, setTranslating] = useState<string | null>(null);
  const [jobInfo, setJobInfo] = useState<{ id: string; status: string; progress: number } | null>(null);

  const fetchProject = useCallback(async () => {
    setLoading(true);
    try {
      const [m, ch] = await Promise.all([
        mangaApi.get(mangaId),
        mangaApi.listChapters(mangaId),
      ]);
      setManga(m);
      setChapters(ch);

      // Load pages for each chapter
      const pagesMap: Record<string, Page[]> = {};
      await Promise.all(
        ch.map(async (c) => {
          try {
            pagesMap[c.id] = await mangaApi.listPages(mangaId, c.id);
          } catch {
            pagesMap[c.id] = [];
          }
        })
      );
      setChapterPages(pagesMap);
    } catch (err) {
      console.error("Failed to load project:", err);
    } finally {
      setLoading(false);
    }
  }, [mangaId]);

  useEffect(() => { fetchProject(); }, [fetchProject]);

  // Poll job status if translating
  useEffect(() => {
    if (!jobInfo) return;
    if (jobInfo.status === "completed" || jobInfo.status === "failed") {
      setTranslating(null);
      setJobInfo(null);
      fetchProject();
      return;
    }
    const interval = setInterval(async () => {
      try {
        const status = await translationApi.getJobStatus(jobInfo.id);
        setJobInfo({ id: jobInfo.id, status: status.status, progress: status.progress });
      } catch {
        clearInterval(interval);
      }
    }, 2000);
    return () => clearInterval(interval);
  }, [jobInfo, fetchProject]);

  const handleAddChapter = async () => {
    const num = parseFloat(newChapterNum);
    if (isNaN(num)) return;
    try {
      await mangaApi.createChapter(mangaId, {
        chapter_number: num,
        title: newChapterTitle || undefined,
      });
      setShowAddChapter(false);
      setNewChapterNum("");
      setNewChapterTitle("");
      fetchProject();
    } catch (err) {
      console.error("Failed to add chapter:", err);
    }
  };

  const handleDeleteChapter = async (chapterId: string, num: number) => {
    if (!confirm(`Delete chapter ${num}? This cannot be undone.`)) return;
    try {
      await mangaApi.deleteChapter(mangaId, chapterId);
      fetchProject();
    } catch (err) {
      console.error("Failed to delete chapter:", err);
    }
  };

  const handleTranslate = async (chapterId: string) => {
    setTranslating(chapterId);
    try {
      const job = await translationApi.createJob({ chapter_id: chapterId });
      setJobInfo({ id: job.id, status: job.status, progress: 0 });
    } catch (err: any) {
      console.error("Failed to start translation:", err);
      setTranslating(null);
      alert(err.message || "Failed to start translation");
    }
  };

  const handleExport = (chapterId: string) => {
    router.push(`/preview?manga=${mangaId}&chapter=${chapterId}`);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!manga) {
    return (
      <div className="flex flex-col items-center py-20">
        <AlertCircle className="h-12 w-12 text-muted-foreground/50 mb-4" />
        <p className="text-lg font-medium">Project not found</p>
        <Button variant="outline" className="mt-4" onClick={() => router.push("/projects")}>
          Back to Projects
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <button
        onClick={() => router.push("/projects")}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ChevronLeft className="h-4 w-4" /> Back to Projects
      </button>

      {/* Header */}
      <div className="flex items-start gap-6">
        <div className="h-40 w-28 shrink-0 overflow-hidden rounded-lg border bg-muted">
          {manga.cover_image_path ? (
            <img
              src={imageUrl(manga.cover_image_path)}
              alt={manga.title}
              className="h-full w-full object-cover"
              onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
            />
          ) : (
            <div className="flex h-full items-center justify-center">
              <BookOpen className="h-8 w-8 text-muted-foreground/30" />
            </div>
          )}
        </div>
        <div className="flex-1 space-y-2">
          <h1 className="text-3xl font-bold tracking-tight">{manga.title}</h1>
          {manga.title_original && (
            <p className="text-lg text-muted-foreground">{manga.title_original}</p>
          )}
          {manga.author && <p className="text-sm text-muted-foreground">by {manga.author}</p>}
          {manga.description && <p className="text-sm text-muted-foreground">{manga.description}</p>}
          <div className="flex items-center gap-2 flex-wrap pt-1">
            <Badge variant="info">
              <Languages className="h-3 w-3 mr-1" />
              {manga.source_language?.toUpperCase()} → {manga.target_language?.toUpperCase()}
            </Badge>
            <Badge variant="secondary">{chapters.length} chapters</Badge>
            <Badge variant="secondary">{manga.total_pages || 0} pages</Badge>
            {manga.translated_pages && manga.translated_pages > 0 && (
              <Badge variant="success">{manga.translated_pages} translated</Badge>
            )}
          </div>
        </div>
      </div>

      {/* Progress bar */}
      {(manga.total_pages || 0) > 0 && (
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">Translation Progress</span>
              <span className="text-sm text-muted-foreground">
                {manga.translated_pages || 0} / {manga.total_pages || 0} pages ({Math.round(manga.translation_progress || 0)}%)
              </span>
            </div>
            <Progress value={manga.translation_progress || 0} variant="success" />
          </CardContent>
        </Card>
      )}

      {/* Chapters */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold">Chapters</h2>
          <Button size="sm" onClick={() => setShowAddChapter(true)}>
            <Plus className="h-4 w-4 mr-1" /> Add Chapter
          </Button>
        </div>

        {chapters.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center py-16">
              <BookOpen className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-lg font-medium">No chapters yet</p>
              <p className="text-sm text-muted-foreground mb-4">Add a chapter and upload pages to get started</p>
              <Button onClick={() => setShowAddChapter(true)}>
                <Plus className="h-4 w-4 mr-1" /> Add Chapter
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {chapters.map((chapter) => {
              const pages = chapterPages[chapter.id] || [];
              const translatedCount = pages.filter((p) => p.is_translated).length;
              const progress = pages.length > 0 ? (translatedCount / pages.length) * 100 : 0;
              const isTranslating = translating === chapter.id;
              return (
                <Card key={chapter.id} className="transition-all hover:shadow-md">
                  <CardContent className="p-4">
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium">
                            Chapter {chapter.chapter_number}
                          </span>
                          {chapter.title && (
                            <span className="text-sm text-muted-foreground">— {chapter.title}</span>
                          )}
                          {chapter.is_translated && <Badge variant="success" className="text-xs">Translated</Badge>}
                        </div>
                        <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                          <span>{pages.length} pages</span>
                          {translatedCount > 0 && <span>{translatedCount} translated</span>}
                          <span>
                            <Clock className="h-3 w-3 inline mr-1" />
                            {new Date(chapter.created_at).toLocaleDateString()}
                          </span>
                        </div>
                        {pages.length > 0 && (
                          <div className="mt-2">
                            <Progress value={progress} variant="success" className="h-1" />
                          </div>
                        )}
                        {isTranslating && jobInfo && (
                          <div className="mt-2 flex items-center gap-2">
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            <span className="text-xs text-muted-foreground">
                              Translating... {Math.round(jobInfo.progress)}%
                            </span>
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-1 shrink-0">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => router.push(`/upload?manga=${mangaId}&chapter=${chapter.id}`)}
                          title="Upload pages"
                        >
                          <ImageIcon className="h-3.5 w-3.5 mr-1" /> Upload
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleTranslate(chapter.id)}
                          disabled={isTranslating || pages.length === 0}
                          title="Translate chapter"
                        >
                          {isTranslating ? (
                            <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
                          ) : (
                            <Play className="h-3.5 w-3.5 mr-1" />
                          )}
                          Translate
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleExport(chapter.id)}
                          disabled={pages.length === 0}
                          title="Preview"
                        >
                          <Download className="h-3.5 w-3.5 mr-1" /> Preview
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDeleteChapter(chapter.id, chapter.chapter_number)}
                          title="Delete chapter"
                          className="text-destructive hover:text-destructive"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* Add Chapter Dialog */}
      <Dialog open={showAddChapter} onOpenChange={setShowAddChapter}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Chapter</DialogTitle>
            <DialogDescription>Create a new chapter for this manga</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <Input
              label="Chapter Number *"
              type="number"
              placeholder="e.g. 1"
              value={newChapterNum}
              onChange={(e) => setNewChapterNum(e.target.value)}
            />
            <Input
              label="Chapter Title"
              placeholder="e.g. The Beginning"
              value={newChapterTitle}
              onChange={(e) => setNewChapterTitle(e.target.value)}
            />
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" onClick={() => setShowAddChapter(false)}>Cancel</Button>
              <Button onClick={handleAddChapter} disabled={!newChapterNum.trim()}>
                Add Chapter
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
