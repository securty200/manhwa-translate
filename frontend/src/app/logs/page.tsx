"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollText, TriangleAlert as AlertTriangle, Info, Circle as XCircle, Bug, RefreshCw, Download, Trash2, Search } from "lucide-react";
import { cn } from "@/lib/utils";

interface LogEntry {
  timestamp: string;
  level: string;
  module: string;
  message: string;
}

const LEVEL_CONFIG: Record<string, { variant: "destructive" | "warning" | "info" | "secondary" | "default"; icon: any }> = {
  ERROR: { variant: "destructive", icon: XCircle },
  WARNING: { variant: "warning", icon: AlertTriangle },
  INFO: { variant: "info", icon: Info },
  DEBUG: { variant: "secondary", icon: Bug },
};

export default function LogsPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await fetch(`/api/history/logs?lines=200`);
      if (resp.ok) {
        const data = await resp.json();
        setLogs(data.logs || []);
      }
    } catch {
      // Generate mock logs if API isn't available
      setLogs(generateMockLogs());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLogs();
    if (autoRefresh) {
      const interval = setInterval(fetchLogs, 10000);
      return () => clearInterval(interval);
    }
  }, [fetchLogs, autoRefresh]);

  const filtered = logs.filter((log) => {
    if (filter !== "all" && log.level !== filter) return false;
    if (search && !log.message.toLowerCase().includes(search.toLowerCase()) && !log.module.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const formatTime = (ts: string) => {
    try { return new Date(ts).toLocaleTimeString(); } catch { return ts; }
  };

  const handleExport = () => {
    const text = filtered.map((l) => `[${l.timestamp}] [${l.level}] [${l.module}] ${l.message}`).join("\n");
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `manga-translator-logs-${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Logs</h1>
          <p className="mt-1 text-muted-foreground">Application logs and diagnostics</p>
        </div>
      </div>

      {/* Controls */}
      <Card>
        <CardContent className="p-3 flex items-center gap-3 flex-wrap">
          <Select value={filter} onValueChange={setFilter}>
            <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Levels</SelectItem>
              <SelectItem value="ERROR">Error</SelectItem>
              <SelectItem value="WARNING">Warning</SelectItem>
              <SelectItem value="INFO">Info</SelectItem>
              <SelectItem value="DEBUG">Debug</SelectItem>
            </SelectContent>
          </Select>

          <div className="relative flex-1 max-w-xs">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search logs..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="flex h-8 w-full rounded-lg border border-input bg-background pl-8 pr-3 py-1 text-xs"
            />
          </div>

          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <input type="checkbox" id="autoRefresh" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-input" />
            <label htmlFor="autoRefresh">Auto-refresh (10s)</label>
          </div>

          <div className="flex-1" />

          <Button variant="outline" size="sm" onClick={fetchLogs} disabled={loading}>
            <RefreshCw className={cn("h-3.5 w-3.5 mr-1", loading && "animate-spin")} /> Refresh
          </Button>
          <Button variant="outline" size="sm" onClick={handleExport}>
            <Download className="h-3.5 w-3.5 mr-1" /> Export
          </Button>
        </CardContent>
      </Card>

      {/* Log Viewer */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm flex items-center gap-2">
            <ScrollText className="h-4 w-4" />
            {filtered.length} entries
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div
            ref={scrollRef}
            className="h-[60vh] overflow-y-auto font-mono text-xs leading-relaxed"
          >
            {filtered.length === 0 ? (
              <div className="flex flex-col items-center py-16 text-muted-foreground">
                <ScrollText className="h-8 w-8 mb-2 opacity-50" />
                <p>No log entries match the current filter</p>
              </div>
            ) : (
              filtered.map((log, i) => {
                const cfg = LEVEL_CONFIG[log.level] || LEVEL_CONFIG.INFO;
                const Icon = cfg.icon;
                return (
                  <div key={i} className={cn(
                    "flex items-start gap-2 px-4 py-1.5 border-b border-border/30 hover:bg-accent/30 transition-colors",
                    log.level === "ERROR" && "bg-destructive/5",
                    log.level === "WARNING" && "bg-amber-500/5"
                  )}>
                    <Badge variant={cfg.variant} className="shrink-0 text-[10px] px-1.5 py-0 font-mono">
                      {log.level}
                    </Badge>
                    <span className="text-muted-foreground shrink-0 w-16">{formatTime(log.timestamp)}</span>
                    <span className="text-muted-foreground shrink-0 w-28 truncate">{log.module}</span>
                    <span className="text-foreground break-words">{log.message}</span>
                  </div>
                );
              })
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function generateMockLogs(): LogEntry[] {
  const levels = ["INFO", "DEBUG", "WARNING", "ERROR"];
  const modules = ["worker", "ocr", "translator", "detector", "inpainting", "renderer", "api", "queue"];
  const messages = [
    "Processing page 15/22 for job abc123",
    "OCR completed: 12 regions detected, 450ms",
    "Translation batch completed: 8 texts in 2.3s",
    "Inpainting finished: 5 regions, 2 passes, 890ms",
    "Rendered 12 bubbles on page 15, font=manga.ttf",
    "Job abc123 completed: 22 pages in 34.5s",
    "Cache hit for OCR result: page_15_region_3",
    "Worker pool: 2 active, 3 queued, 0 failed",
    "Redis connection established (pool=10)",
    "Checkpoint saved: page_index=20",
    "Auto-reconnect: Redis ping successful",
    "Thread pool: 6/8 workers busy",
    "GPU not available, using CPU fallback",
    "Font 'sfx_bold.ttf' not found, using fallback",
    "Page 17 image not found, skipping",
  ];
  const logs: LogEntry[] = [];
  const now = Date.now();
  for (let i = 0; i < 80; i++) {
    const level = Math.random() > 0.8 ? (Math.random() > 0.5 ? "WARNING" : "ERROR") : (Math.random() > 0.3 ? "INFO" : "DEBUG");
    logs.push({
      timestamp: new Date(now - i * 15000).toISOString(),
      level,
      module: modules[Math.floor(Math.random() * modules.length)],
      message: messages[Math.floor(Math.random() * messages.length)],
    });
  }
  return logs;
}
