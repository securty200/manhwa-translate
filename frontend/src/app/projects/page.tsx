"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Search, Plus, BookOpen, MoreHorizontal, Trash2, Edit3, Copy, Clock, Languages, ImageIcon, ExternalLink } from "lucide-react";
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
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Projects</h1>
          <p className="mt-1 text-muted-foreground">{projects.length} manga project(s)</p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="mr-2 h-4 w-4" /> New Project
        </Button>
      </div>

      {/* Search */}
      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search projects..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex h-9 w-full rounded-lg border border-input bg-background pl-9 pr-3 py-1 text-sm shadow-sm"
        />
      </div>

      {/* Project Grid */}
      {loading ? (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-72 rounded-xl bg-muted animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <BookOpen className="h-12 w-12 text-muted-foreground/50 mb-4" />
            <p className="text-lg font-medium">No projects found</p>
            <p className="text-sm text-muted-foreground mt-1">
              {search ? "Try a different search term" : "Create your first project to get started"}
            </p>
            {!search && (
              <Button className="mt-4" onClick={() => setShowCreate(true)}>
                <Plus className="mr-2 h-4 w-4" /> Create Project
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filtered.map((project) => (
            <Card
              key={project.id}
              className="group relative overflow-hidden transition-all hover:shadow-lg hover:border-primary/50 cursor-pointer"
              onClick={() => router.push(`/projects/${project.id}`)}
            >
              <div className="aspect-[3/4] bg-gradient-to-br from-muted to-muted/50 flex items-center justify-center">
                {project.cover_image_path ? (
                  <img
                    src={imageUrl(project.cover_image_path)}
                    alt={project.title}
                    className="h-full w-full object-cover"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                  />
                ) : (
                  <BookOpen className="h-12 w-12 text-muted-foreground/30" />
                )}
              </div>
              <div className="p-4 space-y-2">
                <h3 className="font-semibold leading-tight line-clamp-2">{project.title}</h3>
                {project.author && (
                  <p className="text-xs text-muted-foreground">{project.author}</p>
                )}
                <div className="flex items-center gap-2 flex-wrap">
                  <Badge variant="info" className="text-xs">
                    {project.source_language?.toUpperCase()} → {project.target_language?.toUpperCase()}
                  </Badge>
                  <span className="text-xs text-muted-foreground">{project.chapter_count} ch</span>
                </div>
                <Progress value={project.translation_progress || 0} variant="success" className="h-1" />
              </div>
              {/* Actions overlay */}
              <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
                <button
                  onClick={(e) => { e.stopPropagation(); handleDelete(project.id, project.title); }}
                  className="flex h-7 w-7 items-center justify-center rounded-md bg-background/80 backdrop-blur-sm hover:bg-destructive/10 hover:text-destructive transition-colors"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Create Dialog */}
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
