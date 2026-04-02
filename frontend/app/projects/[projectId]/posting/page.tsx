"use client";

import { useState } from "react";
import { PostPlanner } from "@/components/posting/PostPlanner";
import { PostHistory } from "@/components/posting/PostHistory";
import { useProjectContext } from "@/components/ProjectContext";
import { CalendarDays, History } from "lucide-react";
import { cn } from "@/lib/utils";

type Tab = "planner" | "history";

export default function PostingPage() {
  const { project } = useProjectContext();
  const [activeTab, setActiveTab] = useState<Tab>("planner");

  return (
    <div className="p-8 space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-semibold">Posting</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Schedule drafts and track your publishing history.
        </p>
      </div>

      {/* Tab bar */}
      <div className="flex items-center gap-1 border-b border-border pb-0">
        <button
          type="button"
          onClick={() => setActiveTab("planner")}
          className={cn(
            "flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-all -mb-px",
            activeTab === "planner"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          <CalendarDays className="w-4 h-4" />
          Planner
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("history")}
          className={cn(
            "flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-all -mb-px",
            activeTab === "history"
              ? "border-primary text-primary"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          <History className="w-4 h-4" />
          History
        </button>
      </div>

      {activeTab === "planner" && <PostPlanner projectId={project.id} />}
      {activeTab === "history" && <PostHistory projectId={project.id} />}
    </div>
  );
}
