"use client";

import { useEffect, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { BookOpen, Clock, CheckCircle2, Activity, TrendingUp, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { mangaApi, translationApi, type Manga, type TranslationJob } from "@/lib/api";

type BadgeVariant = "success" | "info" | "secondary" | "destructive" | "warning" | "default" | "outline";

const statusVariant: Record<string, BadgeVariant> = {
  completed: "success",
  processing: "info",
  queued: "secondary",
  pending: "secondary",
  failed: "destructive",
  cancelled: "secondary",
  paused: "warning",
};

export default function DashboardPage() {
  const [projects, setProjects] = useState<Manga[]>([]);
  const [recentJobs, setRecentJobs] = useState<TranslationJob[]>([]);
  const [queueStatus, setQueueStatus] = useState<{ active_jobs: number; pending_queue_size: number; healthy: boolean } | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [projData, jobsData, queueData] = await Promise.all([
        mangaApi.list({ per_page: 4 }).catch(() => [] as Manga[]),
        translationApi.listJobs({ limit: 5 }).catch(() => [] as TranslationJob[]),
        translationApi.getQueueStatus().catch(() => null),
      ]);
      setProjects(projData);
      setRecentJobs(jobsData);
      setQueueStatus(queueData);
    } catch (err) {
      console.error("Dashboard fetch error:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const totalPages = projects.reduce((s, p) => s + (p.total_pages || 0), 0);
  const translatedPages = projects.reduce((s, p) => s + (p.translated_pages || 0), 0);
  const activeJobs = recentJobs.filter((j) => j.status === "processing").length;
  const failedJobs = recentJobs.filter((j) => j.status === "failed").length;

  const stats = [
    { label: "Total Projects", value: String(projects.length), icon: BookOpen, color: "text-sky-500", bg: "bg-sky-500/10" },
    { label: "Translated Pages", value: String(translatedPages), icon: CheckCircle2, color: "text-emerald-500", bg: "bg-emerald-500/10" },
    { label: "Active Jobs", value: String(activeJobs), icon: Activity, color: "text-amber-500", bg: "bg-amber-500/10" },
    { label: "Total Pages", value: String(totalPages), icon: TrendingUp, color: "text-violet-500", bg: "bg-violet-500/10" },
  ];

  const systemItems: Array<{ label: string; status: string; variant: BadgeVariant }> = [
    { label: "Queue Manager", status: queueStatus?.healthy ? "Available" : "Unavailable", variant: queueStatus?.healthy ? "success" : "destructive" },
    { label: "Active Jobs", status: String(queueStatus?.active_jobs ?? 0), variant: "info" },
    { label: "Queued Jobs", status: String(queueStatus?.pending_queue_size ?? 0), variant: "secondary" },
    { label: "GPU Acceleration", status: failedJobs > 0 ? "Check logs" : "Available", variant: failedJobs > 0 ? "warning" : "success" },
  ];

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
          <p className="mt-1 text-muted-foreground">Overview of your translation projects</p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchData} disabled={loading}>
          <RefreshCw className={cn("h-3.5 w-3.5 mr-1", loading && "animate-spin")} /> Refresh
        </Button>
      </div>

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i}><CardContent className="p-6"><div className="h-20 animate-pulse rounded-lg bg-muted" /></CardContent></Card>
          ))}
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {stats.map((stat) => (
              <Card key={stat.label} className="transition-all hover:shadow-md">
                <CardContent className="p-6">
                  <div className="flex items-center justify-between">
                    <div className={cn("rounded-lg p-2.5", stat.bg)}>
                      <stat.icon className={cn("h-5 w-5", stat.color)} />
                    </div>
                  </div>
                  <div className="mt-4">
                    <p className="text-2xl font-bold">{stat.value}</p>
                    <p className="text-sm text-muted-foreground">{stat.label}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Clock className="h-4 w-4" /> Recent Jobs
                </CardTitle>
              </CardHeader>
              <CardContent>
                {recentJobs.length === 0 ? (
                  <p className="text-sm text-muted-foreground text-center py-8">No recent translation jobs</p>
                ) : (
                  <div className="space-y-4">
                    {recentJobs.map((job) => (
                      <div key={job.id} className="flex items-center justify-between gap-4 rounded-lg border p-3 transition-colors hover:bg-accent/50">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium truncate">Job {job.id.slice(0, 8)}</p>
                          <p className="text-xs text-muted-foreground">
                            {job.source_language}→{job.target_language} · {job.total_pages} pages
                          </p>
                        </div>
                        <div className="flex items-center gap-3">
                          <div className="w-20">
                            <Progress value={job.progress} variant={job.status === "completed" ? "success" : job.status === "failed" ? "warning" : "default"} />
                          </div>
                          <Badge variant={statusVariant[job.status] || "secondary"}>{job.status}</Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Activity className="h-4 w-4" /> System Status
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {systemItems.map((item) => (
                  <div key={item.label} className="flex items-center justify-between rounded-lg border p-3">
                    <span className="text-sm font-medium">{item.label}</span>
                    <Badge variant={item.variant}>{item.status}</Badge>
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
