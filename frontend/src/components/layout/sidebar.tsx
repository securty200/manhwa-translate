"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useSidebar } from "@/lib/sidebar-context";
import { LayoutDashboard, Upload, BookOpen, Eye, Settings, Clock, ScrollText, ListOrdered, Image as ImageIcon, ChevronLeft, ChevronRight, Sun, Moon, Languages, Sparkles } from "lucide-react";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/projects", label: "Projects", icon: BookOpen },
  { href: "/upload", label: "Upload", icon: Upload },
  { href: "/editor", label: "Editor", icon: ImageIcon },
  { href: "/preview", label: "Preview", icon: Eye },
  { href: "/queue", label: "Queue", icon: ListOrdered },
  { href: "/history", label: "History", icon: Clock },
  { href: "/logs", label: "Logs", icon: ScrollText },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { collapsed, setCollapsed } = useSidebar();
  const [mounted, setMounted] = React.useState(false);
  const [theme, setTheme] = React.useState<"light" | "dark">("dark");

  React.useEffect(() => setMounted(true), []);

  React.useEffect(() => {
    const stored = localStorage.getItem("theme");
    if (stored === "light" || stored === "dark") {
      setTheme(stored);
      document.documentElement.classList.toggle("dark", stored === "dark");
    } else {
      document.documentElement.classList.add("dark");
    }
  }, []);

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("theme", next);
    document.documentElement.classList.toggle("dark", next === "dark");
  };

  if (!mounted) return null;

  return (
    <aside
      className={cn(
        "fixed left-0 top-0 z-40 flex h-screen flex-col border-r border-sidebar-border bg-sidebar transition-all duration-300 ease-in-out",
        collapsed ? "w-16" : "w-60"
      )}
    >
      {/* Logo */}
      <div className={cn("flex h-14 items-center border-b border-sidebar-border", collapsed ? "justify-center px-0" : "px-4")}>
        <Link href="/dashboard" className="flex items-center gap-2.5 group">
          <div className="relative flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-primary to-accent shadow-lg shadow-primary/20 transition-transform group-hover:scale-105">
            <Languages className="h-4 w-4 text-white" />
            <div className="absolute inset-0 rounded-lg bg-primary/20 blur-md -z-10" />
          </div>
          {!collapsed && (
            <div className="flex flex-col">
              <span className="font-bold text-sm text-sidebar-foreground leading-none">MangaFlow</span>
              <span className="text-[10px] text-sidebar-foreground/40 mt-0.5">AI Translator</span>
            </div>
          )}
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-0.5 p-2 overflow-y-auto overflow-x-hidden">
        {navItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-all duration-200 nav-glow",
                isActive
                  ? "bg-gradient-to-r from-primary/15 to-transparent text-sidebar-accent"
                  : "text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-foreground/5",
                collapsed && "justify-center px-2"
              )}
            >
              {isActive && (
                <div className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-r-full bg-sidebar-accent" />
              )}
              <item.icon className={cn("h-4 w-4 shrink-0 transition-transform group-hover:scale-110", isActive && "text-sidebar-accent")} />
              {!collapsed && <span className="truncate">{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Pro badge */}
      {!collapsed && (
        <div className="px-3 pb-2">
          <div className="rounded-lg border border-sidebar-border bg-gradient-to-br from-primary/10 to-accent/5 p-3">
            <div className="flex items-center gap-2">
              <Sparkles className="h-3.5 w-3.5 text-sidebar-accent" />
              <span className="text-xs font-semibold text-sidebar-foreground">Pro Engine</span>
            </div>
            <p className="mt-1 text-[10px] text-sidebar-foreground/40">All AI engines active</p>
          </div>
        </div>
      )}

      {/* Theme toggle + collapse */}
      <div className="border-t border-sidebar-border p-2 space-y-0.5">
        <button
          onClick={toggleTheme}
          className={cn(
            "group flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-sidebar-foreground/60 transition-all hover:bg-sidebar-foreground/5 hover:text-sidebar-foreground",
            collapsed && "justify-center px-2"
          )}
        >
          {theme === "dark" ? <Sun className="h-4 w-4 transition-transform group-hover:rotate-45" /> : <Moon className="h-4 w-4 transition-transform group-hover:-rotate-12" />}
          {!collapsed && <span>{theme === "dark" ? "Light Mode" : "Dark Mode"}</span>}
        </button>
        <button
          onClick={() => setCollapsed(!collapsed)}
          className={cn(
            "group flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-sidebar-foreground/60 transition-all hover:bg-sidebar-foreground/5 hover:text-sidebar-foreground",
            collapsed && "justify-center px-2"
          )}
        >
          {collapsed ? <ChevronRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" /> : <ChevronLeft className="h-4 w-4 transition-transform group-hover:-translate-x-0.5" />}
          {!collapsed && <span>Collapse</span>}
        </button>
      </div>
    </aside>
  );
}
