"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { CheckCircle2, Link as LinkIcon } from "lucide-react";

// Informational card for users who can't register a Microsoft Graph app
// (corporate tenant restrictions). Walks them through installing the
// local bridge that reads Outlook for Mac via AppleScript — no OAuth,
// no admin consent, no cloud roundtrip.

export function MacOutlookBridgeCard() {
  const [copied, setCopied] = useState(false);
  const installCmd = "cd scripts/outlook_bridge && ./install.sh";

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(installCmd);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Clipboard access denied");
    }
  }

  return (
    <Card className="bg-card border-border border-dashed">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center flex-shrink-0">
              <svg viewBox="0 0 16 16" className="w-4 h-4 fill-emerald-400">
                <path d="M11.182.008C11.148-.03 9.923.023 8.857 1.18c-1.066 1.156-.902 2.482-.878 2.516.024.034 1.52.087 2.475-1.258.955-1.345.762-2.391.728-2.43Zm3.314 11.733c-.048-.096-2.325-1.234-2.113-3.422.212-2.189 1.675-2.789 1.698-2.854.023-.065-.597-.79-1.254-1.157a3.692 3.692 0 0 0-1.563-.434c-.108-.003-.483-.095-1.254.116-.508.139-1.653.589-1.968.607-.316.018-1.256-.522-2.267-.665-.647-.125-1.333.131-1.824.328-.49.196-1.422.754-2.074 2.237-.652 1.482-.311 3.83-.067 4.56.244.729.625 1.924 1.273 2.796.576.984 1.34 1.667 1.659 1.899.319.232 1.219.386 1.843.067.502-.308 1.408-.485 1.766-.472.357.013 1.061.154 1.782.539.571.197 1.111.115 1.652-.105.541-.221 1.324-1.059 2.238-2.758.347-.79.505-1.217.473-1.282Z"/>
              </svg>
            </div>
            <div>
              <CardTitle className="text-base">Mac Outlook (local bridge)</CardTitle>
              <p className="text-xs text-muted-foreground mt-0.5">
                No Graph API · no admin approval · runs on your Mac
              </p>
            </div>
          </div>
          <Badge variant="outline" className="text-[10px] shrink-0">install on host</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <CardDescription className="text-sm text-muted-foreground">
          For corporate Microsoft accounts that block third-party app
          registration. A small helper script runs on your Mac every 6
          hours, reads Apple Mail + Calendar via AppleScript, and pushes
          events + messages into the backend. Teams chat is not
          supported via this path.
        </CardDescription>

        <div className="rounded-md border border-border bg-secondary/30 p-3 space-y-2">
          <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wide">
            Install (one-time)
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 text-xs font-mono bg-background/60 px-2 py-1.5 rounded border border-border/60 overflow-x-auto">
              {installCmd}
            </code>
            <Button variant="outline" size="sm" onClick={handleCopy} className="gap-1.5 shrink-0">
              {copied ? <CheckCircle2 className="w-3.5 h-3.5" /> : <LinkIcon className="w-3.5 h-3.5" />}
              {copied ? "Copied" : "Copy"}
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            Run from the project root. The installer will prompt for your
            login, write config to <code>~/.workspaceos-bridge.json</code>,
            and register a launchd agent that runs every 6 hours.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
