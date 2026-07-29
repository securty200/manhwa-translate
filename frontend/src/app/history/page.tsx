"use client";

import { useEffect, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Clock, CheckCircle2, AlertCircle, XCircle, Loader2, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { cn, formatDuration } from "@/lib/utils";
import { translationApi, type TranslationJob } from "@/lib/api";

const statusConfig: Record<string, { variant: "success" | "warning" | "destructive" | "info" | "secondary"; label: string }> = {
  completed: { variant: "success", label: "Completed" },
  failed: { variant: "destructive", label: "Failed" },
  cancelled: { variant: "secondary", label: "Cancelled" },
  processing: { variant: "info", label: "Processing" },
  paused: { variant: "warning", label: "Paused" },
  pending: { variant: "secondary", label: "Pending" },
  queued: { variant: "info", label: "Queued" },
};

export default function HistoryPage() {
  const [jobs, setJobs] = useState<TranslationJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const perPage = 15;

  const fetchJobs = useCallback(async () => {
    setLoading(true);
    try {
      const data = await translationApi.listJobs({
        limit: perPage,
        offset: page * perPage,
        status: statusFilter || undefined,
      });
      setJobs(data);
    } catch (err) {
      console.error("Failed to load history:", err);
    } finally {
      setLoading(false);
    }
  }, [page, statusFilter]);

  useEffect(() => { fetchJobs(); }, [fetchJobs]);

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleString();
  };


  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">History</h1>
        <p className="mt-1 text-muted-foreground">Translation job history and activity log</p>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={() => { setStatusFilter(""); setPage(0); }}
          className={cn("rounded-lg px-3 py-1.5 text-xs font-medium transition-colors", !statusFilter ? "bg-primary text-primary-foreground" : "bg-secondary hover:bg-accent")}
        >
          All
        </button>
        {["completed", "failed", "cancelled", "processing"].map((s) => (
          <button
            key={s}
            onClick={() => { setStatusFilter(s); setPage(0); }}
            className={cn("rounded-lg px-3 py-1.5 text-xs font-medium transition-colors", statusFilter === s ? "bg-primary text-primary-foreground" : "bg-secondary hover:bg-accent")}
          >
            {s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 space-y-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-12 rounded-lg bg-muted animate-pulse" />
              ))}
            </div>
          ) : jobs.length === 0 ? (
            <div className="flex flex-col items-center py-16">
              <Clock className="h-12 w-12 text-muted-foreground/50 mb-4" />
              <p className="text-lg font-medium">No history yet</p>
              <p className="text-sm text-muted-foreground">Completed translation jobs will appear here</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="text-left font-medium p-3">Job ID</th>
                    <th className="text-left font-medium p-3">Status</th>
                    <th className="text-left font-medium p-3">Progress</th>
                    <th className="text-left font-medium p-3">Languages</th>
                    <th className="text-left font-medium p-3">Created</th>
                    <th className="text-left font-medium p-3">Completed</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => {
                    const cfg = statusConfig[job.status] || statusConfig.pending;
                    return (
                      <tr key={job.id} className="border-b last:border-0 hover:bg-accent/50 transition-colors">
                        <td className="p-3 font-mono text-xs">{job.id.slice(0, 12)}...</td>
                        <td className="p-3"><Badge variant={cfg.variant} className="text-xs">{cfg.label}</Badge></td>
                        <td className="p-3">
                          <div className="flex items-center gap-2">
                            <Progress value={job.progress} variant={job.status === "completed" ? "success" : "default"} className="w-20 h-1.5" />
                            <span className="text-xs text-muted-foreground">{job.completed_pages}/{job.total_pages}</span>
                          </div>
                        </td>
                        <td className="p-3 text-xs text-muted-foreground">{job.source_language} → {job.target_language}</td>
                        <td className="p-3 text-xs text-muted-foreground">{formatDate(job.created_at)}</td>
                        <td className="p-3 text-xs text-muted-foreground">{formatDate(job.completed_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>Page {page + 1}</span>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}>
            <ChevronLeft className="h-4 w-4 mr-1" /> Previous
          </Button>
          <Button variant="outline" size="sm" onClick={() => setPage(page + 1)} disabled={jobs.length < perPage}>
            Next <ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        </div>
      </div>
    </div>
  );
}
