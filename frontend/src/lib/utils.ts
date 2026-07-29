import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(bytes: number, decimals = 2): string {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
}

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str;
  return str.slice(0, length) + "...";
}

/** Convert a filesystem image path to an accessible HTTP URL.
 *  Backend mounts CACHE_DIR at /static. The /static path is proxied
 *  by Next.js to the backend, so we use a relative URL that works
 *  in both dev and deployed environments. */
export function imageUrl(path?: string): string {
  if (!path) return "";
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  const idx = path.indexOf("cache/");
  if (idx >= 0) {
    const rel = path.slice(idx + 6);
    return `/static/${rel}`;
  }
  const segments = path.split("/").filter(Boolean).slice(-3);
  return segments.length >= 3 ? `/static/${segments.join("/")}` : "";
}
