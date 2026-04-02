"use client";

import { createContext, useContext } from "react";
import type { Project } from "@/lib/types";

interface ProjectContextValue {
  project: Project;
  mutate: () => void;
}

export const ProjectContext = createContext<ProjectContextValue | null>(null);

export function useProjectContext(): ProjectContextValue {
  const ctx = useContext(ProjectContext);
  if (!ctx) {
    throw new Error("useProjectContext must be used within ProjectContext.Provider");
  }
  return ctx;
}
