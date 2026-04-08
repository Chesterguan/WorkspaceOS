"use client";

import { use, useState, useRef } from "react";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useProjectContext } from "@/components/ProjectContext";
import { files as filesApi } from "@/lib/api";
import { toast } from "sonner";
import { formatDistanceToNow } from "@/lib/utils";
import type { FileListResponse } from "@/lib/types";
import {
  Upload,
  Link as LinkIcon,
  File,
  FileText,
  Code,
  Trash2,
  Loader2,
  ArrowLeft,
  Tag,
} from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";

interface FilesPageProps {
  params: Promise<{ projectId: string }>;
}

function fileIcon(mime: string) {
  if (mime.includes("pdf")) return <FileText className="w-4 h-4 text-red-400" />;
  if (mime.includes("markdown") || mime.includes("text")) return <FileText className="w-4 h-4 text-blue-400" />;
  if (mime.includes("javascript") || mime.includes("python") || mime.includes("json"))
    return <Code className="w-4 h-4 text-green-400" />;
  return <File className="w-4 h-4 text-muted-foreground" />;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function FilesPage({ params }: FilesPageProps) {
  const { projectId } = use(params);
  const { project } = useProjectContext();

  const { data, mutate, isLoading } = useSWR<FileListResponse>(
    `/projects/${projectId}/files`,
    () => filesApi.list(projectId),
  );

  const [isUploading, setIsUploading] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [importUrl, setImportUrl] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleUpload(fileList: FileList) {
    setIsUploading(true);
    let uploaded = 0;
    for (const file of Array.from(fileList)) {
      try {
        await filesApi.upload(projectId, file);
        uploaded++;
      } catch (err) {
        toast.error(`Failed to upload ${file.name}`, {
          description: err instanceof Error ? err.message : "Unknown error",
        });
      }
    }
    if (uploaded > 0) {
      toast.success(`${uploaded} file${uploaded > 1 ? "s" : ""} uploaded`);
      await mutate();
    }
    setIsUploading(false);
  }

  async function handleImportUrl() {
    if (!importUrl.trim()) return;
    setIsImporting(true);
    try {
      await filesApi.importUrl(projectId, { url: importUrl.trim() });
      toast.success("URL imported");
      setImportUrl("");
      await mutate();
    } catch (err) {
      toast.error("Import failed", {
        description: err instanceof Error ? err.message : "Unknown error",
      });
    } finally {
      setIsImporting(false);
    }
  }

  async function handleDelete(id: string, filename: string) {
    try {
      await filesApi.delete(projectId, id);
      toast.success(`Deleted ${filename}`);
      await mutate();
    } catch {
      toast.error("Failed to delete file");
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      handleUpload(e.dataTransfer.files);
    }
  }

  const fileList = data?.files ?? [];

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-3 px-6 py-3 border-b border-border bg-card shrink-0">
        <Link href={`/projects/${project.id}`}>
          <Button variant="ghost" size="sm" className="gap-1.5 text-muted-foreground h-8">
            <ArrowLeft className="w-3.5 h-3.5" />
            {project.name}
          </Button>
        </Link>
        <span className="text-muted-foreground text-sm">/</span>
        <div className="flex items-center gap-2">
          <Upload className="w-4 h-4 text-primary" />
          <span className="text-sm font-semibold">Files</span>
          <Badge variant="outline" className="text-xs">{fileList.length}</Badge>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6 space-y-6 max-w-4xl mx-auto w-full">
        {/* Upload zone */}
        <div
          className={cn(
            "border-2 border-dashed rounded-lg p-8 text-center transition-colors cursor-pointer",
            isDragOver
              ? "border-primary bg-primary/5"
              : "border-border hover:border-primary/50",
          )}
          onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="hidden"
            accept=".pdf,.md,.txt,.py,.js,.ts,.json,.yaml,.yml,.xml,.html,.csv,.tex"
            onChange={(e) => e.target.files && handleUpload(e.target.files)}
          />
          {isUploading ? (
            <Loader2 className="w-8 h-8 mx-auto text-primary animate-spin" />
          ) : (
            <Upload className="w-8 h-8 mx-auto text-muted-foreground" />
          )}
          <p className="mt-2 text-sm font-medium">
            {isUploading ? "Uploading..." : "Drop files here or click to upload"}
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            PDF, Markdown, Text, Code files. Max 10MB each.
          </p>
        </div>

        {/* URL import */}
        <div className="flex gap-2">
          <div className="relative flex-1">
            <LinkIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              value={importUrl}
              onChange={(e) => setImportUrl(e.target.value)}
              placeholder="Import from URL (arXiv, blog post, documentation...)"
              className="pl-9"
              onKeyDown={(e) => e.key === "Enter" && handleImportUrl()}
            />
          </div>
          <Button
            onClick={handleImportUrl}
            disabled={isImporting || !importUrl.trim()}
          >
            {isImporting ? <Loader2 className="w-4 h-4 animate-spin" /> : "Import"}
          </Button>
        </div>

        {/* File list */}
        {isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
          </div>
        ) : fileList.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <File className="w-10 h-10 mx-auto mb-3 opacity-40" />
            <p className="text-sm">No files yet. Upload a PDF or import a URL to get started.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {fileList.map((f) => (
              <Card key={f.id} className="border-border/50 hover:border-border transition-colors">
                <CardContent className="flex items-center gap-3 p-3">
                  {fileIcon(f.mime_type)}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium truncate">{f.filename}</p>
                      <Badge variant="outline" className="text-[10px] shrink-0">
                        {f.source}
                      </Badge>
                      <span className="text-[11px] text-muted-foreground shrink-0">
                        {formatSize(f.file_size)}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground truncate mt-0.5">{f.summary}</p>
                    {f.tags.length > 0 && (
                      <div className="flex gap-1 mt-1 flex-wrap">
                        {f.tags.map((t) => (
                          <span key={t} className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] bg-secondary text-muted-foreground">
                            <Tag className="w-2.5 h-2.5" />
                            {t}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <span className="text-[11px] text-muted-foreground shrink-0">
                    {formatDistanceToNow(f.created_at)}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive shrink-0"
                    onClick={() => handleDelete(f.id, f.filename)}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
