"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Upload, FileText, FolderOpen, X, CheckCircle2, AlertCircle, Loader2, ImageIcon, FileArchive, BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { mangaApi, type Manga } from "@/lib/api";

const ACCEPTED_FORMATS = [".pdf", ".cbz", ".cbr", ".zip", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"];

interface UploadFile {
  file: File;
  name: string;
  size: number;
  format: string;
  status: "pending" | "uploading" | "success" | "error";
  progress: number;
  error?: string;
}

export default function UploadPage() {
  const router = useRouter();
  const [dragOver, setDragOver] = useState(false);
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [mangas, setMangas] = useState<Manga[]>([]);
  const [selectedManga, setSelectedManga] = useState<string>("");
  const [chapterNumber, setChapterNumber] = useState("1");
  const [projectTitle, setProjectTitle] = useState("");
  const [createNewProject, setCreateNewProject] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [overallProgress, setOverallProgress] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    mangaApi.list().then(setMangas).catch(() => {});
  }, []);

  const addFiles = useCallback((newFiles: FileList | File[]) => {
    const uploadFiles: UploadFile[] = Array.from(newFiles).map((f) => ({
      file: f,
      name: f.name,
      size: f.size,
      format: f.name.split(".").pop()?.toLowerCase() || "unknown",
      status: "pending" as const,
      progress: 0,
    }));
    setFiles((prev) => [...prev, ...uploadFiles]);
  }, []);

  const removeFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      addFiles(e.dataTransfer.files);
    }
  }, [addFiles]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => setDragOver(false), []);

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
  };

  const getFormatIcon = (fmt: string) => {
    if (["pdf", "cbz", "cbr", "zip"].includes(fmt)) return <FileArchive className="h-4 w-4" />;
    if (["png", "jpg", "jpeg", "webp", "bmp", "tiff"].includes(fmt)) return <ImageIcon className="h-4 w-4" />;
    return <FileText className="h-4 w-4" />;
  };

  const handleUpload = async () => {
    if (files.length === 0) return;

    let mangaId = selectedManga;

    if (createNewProject && projectTitle) {
      try {
        const newManga = await mangaApi.create({
          title: projectTitle,
          source_language: "ja",
          target_language: "en",
        });
        mangaId = newManga.id;
      } catch (err: any) {
        setFiles((prev) =>
          prev.map((f) => ({ ...f, status: "error" as const, error: "Failed to create project" }))
        );
        return;
      }
    }

    if (!mangaId) {
      alert("Please select or create a project");
      return;
    }

    setUploading(true);
    const chapterNum = parseFloat(chapterNumber) || 1;

    try {
      // Create chapter
      let chapterId: string;
      try {
        const chapter = await mangaApi.createChapter(mangaId, { chapter_number: chapterNum });
        chapterId = chapter.id;
      } catch (err: any) {
        // Maybe chapter already exists - list and find
        const chapters = await mangaApi.listChapters(mangaId);
        const existing = chapters.find((c) => c.chapter_number === chapterNum);
        if (existing) {
          chapterId = existing.id;
        } else {
          throw err;
        }
      }

      // Upload all files in a single request
      setFiles((prev) => prev.map((f) => ({ ...f, status: "uploading" as const, progress: 0 })));

      const formData = new FormData();
      files.forEach((f) => formData.append("files", f.file));

      try {
        const resp = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1"}/upload/${mangaId}/chapters/${chapterId}/pages`,
          { method: "POST", body: formData }
        );

        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ detail: "Upload failed" }));
          throw new Error(err.detail || "Upload failed");
        }

        setFiles((prev) => prev.map((f) => ({ ...f, status: "success" as const, progress: 100 })));
      } catch (err: any) {
        setFiles((prev) =>
          prev.map((f) => ({ ...f, status: "error" as const, error: err.message }))
        );
      }

      setOverallProgress(100);
    } catch (err: any) {
      console.error("Upload error:", err);
    } finally {
      setUploading(false);
    }
  };

  const allUploaded = files.length > 0 && files.every((f) => f.status === "success");

  return (
    <div className="space-y-6 max-w-4xl">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Upload Manga</h1>
        <p className="mt-1 text-muted-foreground">
          Import manga chapters from PDF, CBZ, CBR, ZIP, or image files
        </p>
      </div>

      {/* Project Selection */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <BookOpen className="h-4 w-4" /> Project
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {!createNewProject ? (
            <div className="space-y-2">
              <label className="text-sm font-medium">Select Project</label>
              <select
                className="flex h-9 w-full rounded-lg border border-input bg-background px-3 py-1 text-sm shadow-sm"
                value={selectedManga}
                onChange={(e) => setSelectedManga(e.target.value)}
              >
                <option value="">Choose a project...</option>
                {mangas.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.title} ({m.source_language?.toUpperCase()}→{m.target_language?.toUpperCase()})
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <Input
              label="New Project Title"
              placeholder="e.g. One Piece, Jujutsu Kaisen..."
              value={projectTitle}
              onChange={(e) => setProjectTitle(e.target.value)}
            />
          )}
          <div className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              id="newProject"
              checked={createNewProject}
              onChange={(e) => setCreateNewProject(e.target.checked)}
              className="rounded border-input"
            />
            <label htmlFor="newProject" className="text-muted-foreground cursor-pointer">
              Create new project
            </label>
          </div>
          <Input
            label="Chapter Number"
            type="number"
            value={chapterNumber}
            onChange={(e) => setChapterNumber(e.target.value)}
            placeholder="1"
          />
        </CardContent>
      </Card>

      {/* Drop Zone */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Upload className="h-4 w-4" /> Files
          </CardTitle>
          <CardDescription>Drop files or click to browse. Supported: PDF, CBZ, CBR, ZIP, PNG, JPG, WEBP</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onClick={() => fileInputRef.current?.click()}
            className={cn(
              "relative cursor-pointer rounded-xl border-2 border-dashed p-12 text-center transition-all duration-200",
              dragOver
                ? "border-primary bg-primary/5 scale-[1.02]"
                : "border-muted-foreground/25 hover:border-muted-foreground/50 hover:bg-accent/50"
            )}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={ACCEPTED_FORMATS.join(",")}
              className="hidden"
              onChange={(e) => e.target.files && addFiles(e.target.files)}
            />
            <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
              <Upload className={cn("h-6 w-6 text-primary", dragOver && "animate-bounce")} />
            </div>
            <p className="text-sm font-medium">
              {dragOver ? "Drop files here" : "Drag & drop files here, or click to browse"}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              PDF · CBZ · CBR · ZIP · PNG · JPG · WEBP · BMP · TIFF
            </p>
          </div>

          {/* File List */}
          {files.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">{files.length} file(s)</p>
                {!uploading && (
                  <button
                    onClick={() => setFiles([])}
                    className="text-xs text-muted-foreground hover:text-destructive transition-colors"
                  >
                    Clear all
                  </button>
                )}
              </div>
              {files.map((f, i) => (
                <div
                  key={i}
                  className={cn(
                    "flex items-center gap-3 rounded-lg border p-3 transition-all",
                    f.status === "success" && "border-emerald-500/30 bg-emerald-500/5",
                    f.status === "error" && "border-destructive/30 bg-destructive/5"
                  )}
                >
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-muted">
                    {getFormatIcon(f.format)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{f.name}</p>
                    <p className="text-xs text-muted-foreground">{formatFileSize(f.size)}</p>
                    {f.status === "uploading" && (
                      <Progress value={50} className="mt-1 h-1" />
                    )}
                    {f.error && <p className="text-xs text-destructive mt-1">{f.error}</p>}
                  </div>
                  <Badge
                    variant={
                      f.status === "success" ? "success" : f.status === "error" ? "destructive" : "secondary"
                    }
                    className="shrink-0"
                  >
                    {f.status === "pending" ? "Pending" : f.status === "uploading" ? "Uploading" : f.status === "success" ? "Uploaded" : "Failed"}
                  </Badge>
                  {!uploading && f.status !== "success" && (
                    <button onClick={() => removeFile(i)} className="text-muted-foreground hover:text-destructive">
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Overall Progress */}
          {uploading && (
            <div className="space-y-1">
              <div className="flex justify-between text-xs text-muted-foreground">
                <span>Uploading...</span>
                <span>{Math.round(overallProgress)}%</span>
              </div>
              <Progress value={overallProgress} />
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-3 pt-2">
            <Button
              size="lg"
              onClick={handleUpload}
              disabled={files.length === 0 || uploading}
              loading={uploading}
            >
              {uploading ? "Uploading..." : allUploaded ? "Upload More" : "Start Upload"}
            </Button>
            {allUploaded && (
              <Button
                variant="outline"
                size="lg"
                onClick={() => router.push("/projects")}
              >
                View Projects
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Format Badges */}
      <div className="flex flex-wrap gap-2">
        {ACCEPTED_FORMATS.map((fmt) => (
          <Badge key={fmt} variant="secondary" className="text-xs">
            {fmt.toUpperCase()}
          </Badge>
        ))}
      </div>
    </div>
  );
}
