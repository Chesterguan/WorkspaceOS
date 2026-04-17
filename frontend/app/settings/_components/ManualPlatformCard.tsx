"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "./StatusBadge";

interface ManualPlatformCardProps {
  icon: React.ReactNode;
  name: string;
  reason: string;
  description: string;
}

export function ManualPlatformCard({ icon, name, reason, description }: ManualPlatformCardProps) {
  return (
    <Card className="bg-card border-border opacity-75">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-secondary flex items-center justify-center flex-shrink-0">
              {icon}
            </div>
            <CardTitle className="text-base">{name}</CardTitle>
          </div>
          <StatusBadge status="manual" />
        </div>
      </CardHeader>
      <CardContent className="space-y-1.5">
        <p className="text-sm font-medium text-muted-foreground">{reason}</p>
        <CardDescription className="text-sm text-muted-foreground">{description}</CardDescription>
      </CardContent>
    </Card>
  );
}
