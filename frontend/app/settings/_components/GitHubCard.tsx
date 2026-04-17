"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { github_status as githubStatusApi } from "@/lib/api";
import { GitFork } from "lucide-react";
import { StatusBadge, type ConnectionStatus } from "./StatusBadge";

export function GitHubCard() {
  const [status, setStatus] = useState<ConnectionStatus>("loading");
  const [username, setUsername] = useState<string>("");

  useEffect(() => {
    githubStatusApi
      .check()
      .then((res) => {
        setStatus(res.connected ? "connected" : "disconnected");
        setUsername(res.username);
      })
      .catch(() => {
        setStatus("disconnected");
      });
  }, []);

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-secondary flex items-center justify-center flex-shrink-0">
              <GitFork className="w-5 h-5 text-foreground" />
            </div>
            <div>
              <CardTitle className="text-base">GitHub</CardTitle>
              {username && status === "connected" && (
                <p className="text-xs text-muted-foreground mt-0.5">@{username}</p>
              )}
            </div>
          </div>
          <StatusBadge status={status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <CardDescription className="text-sm text-muted-foreground">
          Connected via <code className="text-xs bg-secondary/60 px-1 py-0.5 rounded">GITHUB_TOKEN</code> environment
          variable. Used to sync commits, create GitHub Releases, and import repos.
        </CardDescription>
        <p className="text-xs text-muted-foreground">
          To change accounts, update <code className="bg-secondary/60 px-1 py-0.5 rounded">GITHUB_TOKEN</code> in your
          environment and restart the server.
        </p>
      </CardContent>
    </Card>
  );
}
