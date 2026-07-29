"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Search, Plus, BookOpen, Trash2, Languages, Image as ImageIcon } from "lucide-react";
import { cn, imageUrl } from "@/lib/utils";
import { mangaApi, type Manga } from "@/lib/api";

export default function ProjectsPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Manga[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newAuthor, setNewAuthor] = useState("");
  const [newSource, setNewSource] = useState("ja");
  const [newTarget, setNewTarget] = useState("en");

  const fetchProjects = useCallback(async () => {
    setLoading(true);
    try {
      const data = await mangaApi.list({ search: search || undefined });
      setProjects(data);
    } catch (err) {
      console.error("Failed to load projects:", err);
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => { fetchProjects(); }, [fetchProjects]);

  const handleCreate = async () => {
    if (!newTitle.trim()) return;
    try {
      await mangaApi.create({
        title: newTitle,
        author: newAuthor || undefined,
        source_language: newSource,
        target_language: newTarget,
      });
      setShowCreate(false);
      setNewTitle("");
      setNewAuthor("");
      fetchProjects();
    } catch (err) {
      console.error("Failed to create project:", err);
    }
  };

  const handleDelete = async (id: string, title: string) => {
    if (!confirm(`Delete "${title}"? This cannot be undone.`)) return;
    try {
      await mangaApi.delete(id);
      fetchProjects();
    } catch (err) {
      console.error("Failed to delete project:", err);
    }
  };

  const filtered = projects.filter((p) =>
    p.title.toLowerCase().includes(search.toLowerCase()) ||
    (p.author || "").toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Projects</h1>
          <p className="mt-1 text-muted-foreground">{projects.length} manga project(s)</p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="mr-2 h-4 w-4" /> New Project
        </Button>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search projects..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex h-10 w-full rounded-xl border border-input bg-card/50 backdrop-blur-sm pl-10 pr-3 py-2 text-sm shadow-sm transition-all focus:outline-none focus:ring-2 focus:ring-ring focus:border-primary/40"
        />
      </div>

      {loading ? (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-80 rounded-xl bg-muted animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-20">
            <div className="rounded-2xl bg-muted p-4 mb-4">
              <BookOpen className="h-10 w-10 text-muted-foreground/40" />
            </div>
            <p className="text-lg font-medium">No projects found</p>
            <p className="text-sm text-muted-foreground mt-1">
              {search ? "Try a different search term" : "Create your first project to get started"}
            </p>
            {!search && (
              <Button className="mt-6" onClick={() => setShowCreate(true)}>
                <Plus className="mr-2 h-4 w-4" /> Create Project
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((project, i) => (
            <Card
              key={project.id}
              className="group relative overflow-hidden card-hover cursor-pointer animate-slide-up"
              style={{ animationDelay: `${i * 50}ms` }}
              onClick={() => router.push(`/projects/${project.id}`)}
            >
              <div className="relative aspect-[3/4] overflow-hidden bg-gradient-to-br from-muted to-muted/30">
                {project.cover_image_path ? (
                  <img
                    src={imageUrl(project.cover_image_path)}
                    alt={project.title}
                    className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                  />
                ) : (
                  <div className="flex h-full items-center justify-center">
                    <BookOpen className="h-12 w-12 text-muted-foreground/20" />
                  </div>
                )}
                <div className="absolute inset-0 bg-gradient-to-t from-card via-transparent to-transparent" />
              </div>
              <div className="p-4 space-y-3">
                <h3 className="font-semibold leading-tight line-clamp-2">{project.title}</h3>
                {project.author && (
                  <p className="text-xs text-muted-foreground">{project.author}</p>
                )}
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="info" className="gap-1">
                    <Languages className="h-3 w-3" />
                    {project.source_language?.toUpperCase()} → {project.target_language?.toUpperCase()}
                  </Badge>
                  <span className="text-xs text-muted-foreground">{project.chapter_count} ch</span>
                </div>
                <Progress value={project.translation_progress || 0} variant="success" className="h-1.5" />
              </div>
              <div className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                <button
                  onClick={(e) => { e.stopPropagation(); handleDelete(project.id, project.title); }}
                  className="flex h-8 w-8 items-center justify-center rounded-lg bg-card/80 backdrop-blur-md border border-border/50 text-muted-foreground hover:text-destructive hover:border-destructive/30 transition-all"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Project</DialogTitle>
            <DialogDescription>Add a new manga translation project</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <Input label="Title *" placeholder="e.g. One Piece" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
            <Input label="Author" placeholder="e.g. Eiichiro Oda" value={newAuthor} onChange={(e) => setNewAuthor(e.target.value)} />
            <div className="grid grid-cols-2 gap-4">
              <Input label="Source Language" placeholder="ja" value={newSource} onChange={(e) => setNewSource(e.target.value)} />
              <Input label="Target Language" placeholder="en" value={newTarget} onChange={(e) => setNewTarget(e.target.value)} />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" onClick={() => setShowCreate(false)}>Cancel</Button>
              <Button onClick={handleCreate} disabled={!newTitle.trim()}>Create</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
