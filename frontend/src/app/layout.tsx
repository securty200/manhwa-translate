import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "@/styles/globals.css";
import { cn } from "@/lib/utils";
import { Sidebar } from "@/components/layout/sidebar";
import { MainContent } from "@/components/layout/main-content";
import { SidebarProvider } from "@/lib/sidebar-context";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "MangaFlow — AI Manga Translator",
  description: "Translate manga with AI-powered OCR, text detection, inpainting, and LLM translation.",
  icons: { icon: "/favicon.ico" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning className="dark">
      <body className={cn("min-h-screen bg-background font-sans antialiased", inter.variable)}>
        {/* Ambient background glow */}
        <div className="pointer-events-none fixed inset-0 overflow-hidden">
          <div className="absolute -top-40 -right-40 h-96 w-96 rounded-full bg-primary/5 blur-3xl" />
          <div className="absolute top-1/2 -left-40 h-96 w-96 rounded-full bg-accent/5 blur-3xl" />
        </div>
        <SidebarProvider>
          <Sidebar />
          <MainContent>{children}</MainContent>
        </SidebarProvider>
      </body>
    </html>
  );
}
