"use client";

import { use } from "react";
import { ResearchChatWindow } from "@/components/research/ResearchChatWindow";

interface ResearchPageProps {
  params: Promise<{ projectId: string }>;
}

export default function ResearchPage({ params }: ResearchPageProps) {
  // params is a Promise in Next.js 15+ — unwrap with use()
  const { projectId } = use(params);

  return (
    // h-full fills the layout's flex column so ResearchChatWindow can manage
    // its own internal scroll rather than the page scrolling.
    <div className="h-full flex flex-col">
      <ResearchChatWindow projectId={projectId} />
    </div>
  );
}
