"use client";

import { useEffect, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ListOrdered, Play, Pause, XCircle, RotateCcw, Clock, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { translationApi, type TranslationJob } from "@/lib/api";

const statusConfig: Record<string, { label: string; variant: "success" | "warning" | "destructive" | "info" | "secondary"; icon: any }> = {
  pending: { label: "Pending", variant: "secondary", icon: Clock },
  queued: { label: "Queued", variant: "info", icon: Clock },
  processing: { label: "Processing", variant: "info", icon: Loader2 },
  paused: { label: "Paused", variant: "warning", icon: Pause },
  completed: { label: "Completed", variant: "success", icon: CheckCircle2 },
  failed: { label: "Failed", variant: "destructive", icon: AlertCircle },
  cancelled: { label: "Cancelled", variant: "secondary", icon: XCircle },
};

export default function QueuePage() {
  const [jobs, setJobs] = useState<TranslationJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");

  const fetchJobs = useCallback(async () => {
    try {
      const data = await translationApi.listJobs({ limit: 50 });
      setJobs(data);
    } catch (err) {
      console.error("Failed to load jobs:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, [fetchJobs]);

  const handleCancel = async (id: string) => {
    try { await translationApi.cancelJob(id); fetchJobs(); } catch (err) { console.error(err); }
  };

  const handleRetry = async (id: string, chapterId?: string) => {
    try {
      await translationApi.retryJob(id);
      fetchJobs();
    } catch (err) { console.error(err); }
  };

  const handlePauseResume = async (id: string, currentStatus: string) => {
    try {
      if (currentStatus === "processing") {
        await translationApi.stopJob(id);
      } else {
        await translationApi.resumeJob(id);
      }
      fetchJobs();
    } catch (err) { console.error(err); }
  };

  const filtered = filter === "all" ? jobs : jobs.filter((j) => j.status === filter);

  const counts = {
    processing: jobs.filter((j) => j.status === "processing").length,
    queued: jobs.filter((j) => j.status === "queued" || j.status === "pending").length,
    failed: jobs.filter((j) => j.status === "failed").length,
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Job Queue</h1>
        <p className="mt-1 text-muted-foreground">
          {counts.processing} active, {counts.queued} queued, {counts.failed} failed
        </p>
      </div>

      {/* Filter Tabs */}
      <div className="flex gap-2 flex-wrap">
        {["all", "processing", "queued", "completed", "failed", "paused", "cancelled"].map((status) => (
          <button
            key={status}
            onClick={() => setFilter(status)}
            className={cn(
              "rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
              filter === status
                ? "bg-primary text-primary-foreground"
                : "bg-secondary text-secondary-foreground hover:bg-accent"
            )}
          >
            {status === "all" ? "All" : status.charAt(0).toUpperCase() + status.slice(1)}
            {status !== "all" && ` (${jobs.filter((j) => j.status === status).length})`}
          </button>
        ))}
      </div>

      {/* Queue Status Overview */}
      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-sky-500/10 p-2.5"><Loader2 className="h-5 w-5 text-sky-500 animate-spin" /></div>
            <div><p className="text-2xl font-bold">{counts.processing}</p><p className="text-xs text-muted-foreground">Active</p></div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-amber-500/10 p-2.5"><Clock className="h-5 w-5 text-amber-500" /></div>
            <div><p className="text-2xl font-bold">{counts.queued}</p><p className="text-xs text-muted-foreground">Queued</p></div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4 flex items-center gap-3">
            <div className="rounded-lg bg-destructive/10 p-2.5"><AlertCircle className="h-5 w-5 text-destructive" /></div>
            <div><p className="text-2xl font-bold">{counts.failed}</p><p className="text-xs text-muted-foreground">Failed</p></div>
          </CardContent>
        </Card>
      </div>

      {/* Job List */}
      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-20 rounded-lg bg-muted animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center py-16">
            <ListOrdered className="h-12 w-12 text-muted-foreground/50 mb-4" />
            <p className="text-lg font-medium">No jobs found</p>
            <p className="text-sm text-muted-foreground">Jobs will appear here when you start translating chapters</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {filtered.map((job) => {
            const cfg = statusConfig[job.status] || statusConfig.pending;
            const Icon = cfg.icon;
            return (
              <Card key={job.id} className="transition-all hover:shadow-md">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <Icon className={cn("h-4 w-4 shrink-0", job.status === "processing" && "animate-spin")} />
                        <p className="text-sm font-medium truncate">
                          Job {job.id.slice(0, 8)}
                        </p>
                        <Badge variant={cfg.variant} className="text-xs">{cfg.label}</Badge>
                      </div>
                      <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                        <span>{job.total_pages} pages</span>
                        <span>Completed: {job.completed_pages}/{job.total_pages}</span>
                        {job.failed_pages > 0 && (
                          <span className="text-destructive">Failed: {job.failed_pages}</span>
                        )}
                      </div>
                      {job.status === "processing" && (
                        <Progress value={job.progress} variant="default" className="mt-2 h-1.5" />
                      )}
                      {job.error_message && (
                        <p className="mt-1 text-xs text-destructive truncate">{job.error_message}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-1 shrink-0">
                      {(job.status === "processing" || job.status === "paused") && (
                        <Button variant="ghost" size="icon" onClick={() => handlePauseResume(job.id, job.status)} title={job.status === "paused" ? "Resume" : "Pause"}>
                          {job.status === "paused" ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
                        </Button>
                      )}
                      {(job.status === "queued" || job.status === "pending" || job.status === "processing" || job.status === "paused") && (
                        <Button variant="ghost" size="icon" onClick={() => handleCancel(job.id)} title="Cancel">
                          <XCircle className="h-4 w-4" />
                        </Button>
                      )}
                      {job.status === "failed" && (
                        <Button variant="ghost" size="icon" onClick={() => handleRetry(job.id, job.chapter_id)} title="Retry">
                          <RotateCcw className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
