"use client";

// Settings page — thin composition root. Each card owns its own state,
// data fetching, and UI. Previously this file was 1,188 lines with
// every card inlined; now each lives under `_components/` and this
// file just arranges them into two sections.

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ArrowLeft } from "lucide-react";

import { ApiKeysCard } from "./_components/ApiKeysCard";
import { UsageCard } from "./_components/UsageCard";
import { BackupCard } from "./_components/BackupCard";
import { MacOutlookBridgeCard } from "./_components/MacOutlookBridgeCard";
import { MicrosoftCard } from "./_components/MicrosoftCard";
import { GoogleCard } from "./_components/GoogleCard";
import { LinkedInCard } from "./_components/LinkedInCard";
import { GitHubCard } from "./_components/GitHubCard";
import { ManualPlatformCard } from "./_components/ManualPlatformCard";

export default function SettingsPage() {
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b border-border px-8 py-4">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/projects">
              <Button variant="ghost" size="icon" className="w-8 h-8 text-muted-foreground hover:text-foreground">
                <ArrowLeft className="w-4 h-4" />
              </Button>
            </Link>
            <div>
              <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
              <p className="text-xs text-muted-foreground mt-0.5">
                Platform connections and global configuration
              </p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-8 py-8 space-y-8">
        {/* AI & API Keys section */}
        <section className="space-y-4">
          <div>
            <h2 className="text-sm font-semibold text-foreground">AI & API Keys</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Keys are encrypted and stored in the database. DB values override .env defaults.
            </p>
          </div>
          <Separator className="bg-border" />
          <ApiKeysCard />
          <UsageCard />
          <BackupCard />
        </section>

        {/* Platform Connections section */}
        <section className="space-y-4">
          <div>
            <h2 className="text-sm font-semibold text-foreground">Platform Connections</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Configure once here — connected platforms are available across all projects.
            </p>
          </div>
          <Separator className="bg-border" />

          {/* Connected platforms */}
          <div className="grid gap-4">
            <MacOutlookBridgeCard />
            <MicrosoftCard />
            <GoogleCard />
            <LinkedInCard />
            <GitHubCard />
          </div>

          {/* Manual-only platforms */}
          <div className="space-y-2 pt-2">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Manual publishing only
            </p>
            <div className="grid gap-3">
              <ManualPlatformCard
                icon={
                  // X / Twitter — no official lucide icon; use a clean SVG
                  <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-foreground">
                    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.746l7.73-8.835L1.254 2.25H8.08l4.259 5.631ZM17.083 20.13h1.832L7.084 4.126H5.117Z" />
                  </svg>
                }
                name="Twitter / X"
                reason="Manual only — API requires paid tier"
                description="The Twitter/X API v2 write access requires a paid developer plan. Copy your draft and post it manually, then mark it as posted."
              />
              <ManualPlatformCard
                icon={
                  <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-foreground">
                    <path d="M13.54 12a6.8 6.8 0 01-6.77 6.82A6.8 6.8 0 010 12a6.8 6.8 0 016.77-6.82A6.8 6.8 0 0113.54 12zM20.96 12c0 3.54-1.51 6.42-3.38 6.42-1.87 0-3.39-2.88-3.39-6.42s1.52-6.42 3.39-6.42 3.38 2.88 3.38 6.42M24 12c0 3.17-.53 5.75-1.19 5.75-.66 0-1.19-2.58-1.19-5.75s.53-5.75 1.19-5.75C23.47 6.25 24 8.83 24 12z" />
                  </svg>
                }
                name="Medium"
                reason="Manual only — API closed January 2025"
                description="Medium deprecated and closed their public API in January 2025. Copy your draft and publish it via the Medium editor."
              />
              <ManualPlatformCard
                icon={
                  <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-red-400">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14H9V8h2v8zm4 0h-2V8h2v8z" />
                  </svg>
                }
                name="Xiaohongshu (小红书)"
                reason="Manual only — no public API"
                description="Xiaohongshu does not provide a public posting API. Copy your draft and post it manually via the app or web editor."
              />
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
