"use client";

import { useSidebar } from "@/lib/sidebar-context";
import { cn } from "@/lib/utils";

export function MainContent({ children }: { children: React.ReactNode }) {
  const { collapsed } = useSidebar();
  return (
    <main
      className={cn(
        "min-h-screen transition-all duration-300 ease-in-out",
        collapsed ? "pl-16" : "pl-60"
      )}
    >
      <div className="relative z-10 mx-auto max-w-7xl p-6 lg:p-8">
        <div className="animate-fade-in">{children}</div>
      </div>
    </main>
  );
}
