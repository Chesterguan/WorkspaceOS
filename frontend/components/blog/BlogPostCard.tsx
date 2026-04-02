"use client";

import Link from "next/link";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDistanceToNow } from "@/lib/utils";
import { Clock, Tag } from "lucide-react";
import type { BlogPost } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-yellow-600/20 text-yellow-400 border-yellow-600/30",
  published: "bg-green-600/20 text-green-400 border-green-600/30",
};

interface BlogPostCardProps {
  post: BlogPost;
  projectId: string;
}

export function BlogPostCard({ post, projectId }: BlogPostCardProps) {
  const excerpt = post.content
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/\*\*/g, "")
    .replace(/\*/g, "")
    .replace(/`[^`]+`/g, "")
    .slice(0, 120);

  return (
    <Link href={`/projects/${projectId}/blog/${post.id}`}>
      <Card className="group hover:border-primary/50 transition-all duration-200 cursor-pointer h-full">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge
              variant="outline"
              className={`text-xs capitalize ${STATUS_COLORS[post.status]}`}
            >
              {post.status}
            </Badge>
          </div>
          <h3 className="text-sm font-semibold leading-snug group-hover:text-primary transition-colors line-clamp-2 mt-1">
            {post.title}
          </h3>
        </CardHeader>
        <CardContent className="pt-0 space-y-3">
          {excerpt && (
            <p className="text-xs text-muted-foreground line-clamp-3 leading-relaxed">
              {excerpt}
            </p>
          )}

          {(post.tags ?? []).length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <Tag className="w-3 h-3 text-muted-foreground shrink-0" />
              {(post.tags ?? []).slice(0, 4).map((tag) => (
                <Badge
                  key={tag}
                  variant="secondary"
                  className="text-xs px-1.5 py-0"
                >
                  {tag}
                </Badge>
              ))}
              {(post.tags ?? []).length > 4 && (
                <span className="text-xs text-muted-foreground">
                  +{(post.tags ?? []).length - 4}
                </span>
              )}
            </div>
          )}

          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <span className="flex items-center gap-1 ml-auto">
              <Clock className="w-3.5 h-3.5" />
              {formatDistanceToNow(post.updated_at)}
            </span>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
