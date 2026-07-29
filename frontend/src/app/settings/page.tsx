"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Settings, Save, Globe, Palette, Key, Server, RefreshCw, Database, HardDrive, CheckCircle2, Languages, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";

type Tab = "appearance" | "translation" | "api" | "storage";

const tabs: { id: Tab; label: string; icon: any }[] = [
  { id: "appearance", label: "Appearance", icon: Palette },
  { id: "translation", label: "Translation", icon: Globe },
  { id: "api", label: "API Keys", icon: Key },
  { id: "storage", label: "Storage", icon: Database },
];

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("appearance");
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const [saved, setSaved] = useState(false);

  // Translation settings
  const [sourceLang, setSourceLang] = useState("ja");
  const [targetLang, setTargetLang] = useState("en");
  const [engine, setEngine] = useState("auto");
  const [batchSize, setBatchSize] = useState("5");

  // API keys
  const [openaiKey, setOpenaiKey] = useState("");
  const [anthropicKey, setAnthropicKey] = useState("");
  const [deeplKey, setDeeplKey] = useState("");
  const [googleKey, setGoogleKey] = useState("");
  const [ollamaUrl, setOllamaUrl] = useState("http://localhost:11434");

  // Storage info
  const [storageInfo, setStorageInfo] = useState({ mangaCount: 12, pageCount: 356, cacheSize: "1.2 GB", diskFree: "45.6 GB" });

  useEffect(() => {
    const stored = localStorage.getItem("theme");
    if (stored === "light" || stored === "dark") setTheme(stored);
  }, []);

  const handleSave = () => {
    localStorage.setItem("theme", theme);
    document.documentElement.classList.toggle("dark", theme === "dark");
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
          <p className="mt-1 text-muted-foreground">Configure your translation preferences</p>
        </div>
        <Button onClick={handleSave}>
          {saved ? <CheckCircle2 className="mr-2 h-4 w-4" /> : <Save className="mr-2 h-4 w-4" />}
          {saved ? "Saved!" : "Save Settings"}
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg border bg-card p-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-all",
              activeTab === tab.id ? "bg-primary text-primary-foreground shadow-sm" : "hover:bg-accent text-muted-foreground"
            )}
          >
            <tab.icon className="h-4 w-4" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Appearance */}
      {activeTab === "appearance" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Palette className="h-5 w-5" /> Appearance</CardTitle>
            <CardDescription>Customize the look and feel of the application</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div>
              <label className="text-sm font-medium">Theme</label>
              <div className="mt-2 flex gap-4">
                {["dark", "light"].map((t) => (
                  <button
                    key={t}
                    onClick={() => setTheme(t as "dark" | "light")}
                    className={cn(
                      "flex items-center gap-3 rounded-lg border-2 p-4 transition-all",
                      theme === t ? "border-primary bg-primary/5" : "border-muted hover:border-muted-foreground/30"
                    )}
                  >
                    <div className={cn(
                      "flex h-10 w-10 items-center justify-center rounded-lg",
                      t === "dark" ? "bg-slate-900 text-white" : "bg-white text-slate-900 border"
                    )}>
                      {t === "dark" ? <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" /></svg>
                      : <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" /></svg>}
                    </div>
                    <div>
                      <p className="font-medium capitalize">{t} Mode</p>
                      <p className="text-xs text-muted-foreground">{t === "dark" ? "Easy on the eyes at night" : "Bright and clean"}</p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Translation */}
      {activeTab === "translation" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Globe className="h-5 w-5" /> Translation</CardTitle>
            <CardDescription>Default translation settings for new projects</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Source Language</label>
                <Select value={sourceLang} onValueChange={setSourceLang}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ja">Japanese</SelectItem>
                    <SelectItem value="zh">Chinese</SelectItem>
                    <SelectItem value="ko">Korean</SelectItem>
                    <SelectItem value="en">English</SelectItem>
                    <SelectItem value="fr">French</SelectItem>
                    <SelectItem value="es">Spanish</SelectItem>
                    <SelectItem value="ru">Russian</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <label className="text-sm font-medium">Target Language</label>
                <Select value={targetLang} onValueChange={setTargetLang}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="en">English</SelectItem>
                    <SelectItem value="es">Spanish</SelectItem>
                    <SelectItem value="fr">French</SelectItem>
                    <SelectItem value="ru">Russian</SelectItem>
                    <SelectItem value="uz">Uzbek</SelectItem>
                    <SelectItem value="ar">Arabic</SelectItem>
                    <SelectItem value="th">Thai</SelectItem>
                    <SelectItem value="vi">Vietnamese</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1.5">
              <label className="text-sm font-medium">Translation Engine</label>
              <Select value={engine} onValueChange={setEngine}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                <SelectItem value="auto">Auto (Best Available)</SelectItem>
                <SelectItem value="offline_only">Offline Only (NLLB/M2M100)</SelectItem>
                <SelectItem value="cloud_only">Cloud Only (OpenAI/Claude)</SelectItem>
                <SelectItem value="openai">OpenAI GPT-4o</SelectItem>
                <SelectItem value="claude">Anthropic Claude</SelectItem>
                <SelectItem value="deepl">DeepL</SelectItem>
                <SelectItem value="ollama">Ollama (Local)</SelectItem>
              </SelectContent>
              </Select>
            </div>
            <Input label="Batch Concurrency" type="number" value={batchSize} onChange={(e) => setBatchSize(e.target.value)} />
          </CardContent>
        </Card>
      )}

      {/* API Keys */}
      {activeTab === "api" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Key className="h-5 w-5" /> API Keys</CardTitle>
            <CardDescription>Configure API keys for cloud translation services</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {[
              { label: "OpenAI API Key", value: openaiKey, set: setOpenaiKey, placeholder: "sk-...", doc: "Required for GPT-4o translation" },
              { label: "Anthropic API Key", value: anthropicKey, set: setAnthropicKey, placeholder: "sk-ant-...", doc: "Required for Claude translation" },
              { label: "DeepL API Key", value: deeplKey, set: setDeeplKey, placeholder: "...", doc: "Optional - High quality translation" },
              { label: "Google API Key", value: googleKey, set: setGoogleKey, placeholder: "...", doc: "Optional - Gemini translation" },
            ].map((item) => (
              <div key={item.label} className="flex items-end gap-3">
                <div className="flex-1">
                  <Input label={item.label} type="password" placeholder={item.placeholder} value={item.value} onChange={(e) => item.set(e.target.value)} />
                </div>
                <Badge variant="secondary" className="mb-1.5 text-xs h-fit">{item.doc}</Badge>
              </div>
            ))}
            <div className="pt-2">
              <Input label="Ollama URL" value={ollamaUrl} onChange={(e) => setOllamaUrl(e.target.value)} placeholder="http://localhost:11434" />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Storage */}
      {activeTab === "storage" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2"><Database className="h-5 w-5" /> Storage & Cache</CardTitle>
            <CardDescription>Manage disk usage and cached data</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-2 gap-4">
              {[
                { label: "Manga Projects", value: String(storageInfo.mangaCount), icon: Languages },
                { label: "Total Pages", value: String(storageInfo.pageCount), icon: HardDrive },
                { label: "Cache Size", value: storageInfo.cacheSize, icon: Database },
                { label: "Free Disk", value: storageInfo.diskFree, icon: Server },
              ].map((s) => (
                <div key={s.label} className="rounded-lg border p-4">
                  <p className="text-2xl font-bold">{s.value}</p>
                  <p className="text-xs text-muted-foreground mt-1">{s.label}</p>
                </div>
              ))}
            </div>

            <div className="space-y-3">
              <h4 className="text-sm font-medium">Cache Management</h4>
              <div className="flex gap-2">
                <Button variant="outline" size="sm"><RefreshCw className="h-3.5 w-3.5 mr-1" /> Clear OCR Cache</Button>
                <Button variant="outline" size="sm"><RefreshCw className="h-3.5 w-3.5 mr-1" /> Clear Translation Cache</Button>
                <Button variant="destructive" size="sm"><Trash2 className="h-3.5 w-3.5 mr-1" /> Clear All Cache</Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}


