"use client";

import { useSidebar } from "@/lib/sidebar-context";
import { cn } from "@/lib/utils";

export function MainContent({ children }: { children: React.ReactNode }) {
  const { collapsed } = useSidebar();
  return (
    <main
      className={cn(
        "min-h-screen transition-all duration-300",
        collapsed ? "pl-16" : "pl-60"
      )}
    >
      <div className="container mx-auto p-6 max-w-7xl">{children}</div>
    </main>
  );
}
