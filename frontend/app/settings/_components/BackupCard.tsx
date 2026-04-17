"use client";

import { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { appSettings } from "@/lib/api";
import { Loader2, Shield } from "lucide-react";

type BackupSummary = { filename: string; size_human: string; created_at: string };

export function BackupCard() {
  const [backups, setBackups] = useState<BackupSummary[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isBacking, setIsBacking] = useState(false);

  const fetchBackups = useCallback(async () => {
    try {
      const res = await appSettings.listBackups();
      setBackups(res.backups);
    } catch {}
    finally { setIsLoading(false); }
  }, []);

  useEffect(() => { fetchBackups(); }, [fetchBackups]);

  async function handleBackup() {
    setIsBacking(true);
    try {
      const res = await appSettings.triggerBackup();
      if (res.success) {
        toast.success(res.message || "Backup complete");
        await fetchBackups();
      } else {
        toast.error("Backup failed", { description: res.error });
      }
    } catch { toast.error("Backup failed"); }
    finally { setIsBacking(false); }
  }

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-blue-500/15 flex items-center justify-center flex-shrink-0">
              <Shield className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <CardTitle className="text-base">Database Backups</CardTitle>
              <CardDescription className="text-xs mt-0.5">
                Automatic daily backups. Stored in the Docker volume.
              </CardDescription>
            </div>
          </div>
          <Button variant="outline" size="sm" className="gap-1.5" onClick={handleBackup} disabled={isBacking}>
            {isBacking ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Shield className="w-3.5 h-3.5" />}
            Backup Now
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-xs text-muted-foreground">Loading...</p>
        ) : backups.length === 0 ? (
          <p className="text-xs text-muted-foreground">No backups yet. Click &quot;Backup Now&quot; to create one.</p>
        ) : (
          <div className="space-y-1">
            {backups.slice(0, 5).map((b) => (
              <div key={b.filename} className="flex items-center justify-between text-xs py-1">
                <span className="font-mono text-muted-foreground">{b.filename}</span>
                <span className="text-muted-foreground">{b.size_human}</span>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
