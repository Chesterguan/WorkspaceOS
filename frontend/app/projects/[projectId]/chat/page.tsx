"use client";

import { use } from "react";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { useProjectContext } from "@/components/ProjectContext";

interface ChatPageProps {
  params: Promise<{ projectId: string }>;
}

export default function ChatPage({ params }: ChatPageProps) {
  // params is a Promise in Next.js 15+ — unwrap with use()
  use(params);

  // projectId is available via the layout's ProjectContext; we access the
  // project object here for type safety, but ChatWindow only needs the ID.
  const { project } = useProjectContext();

  return (
    // The layout's <main> is flex-1 overflow-y-auto inside a flex overflow-hidden
    // container, so h-full fills that column exactly and lets ChatWindow manage
    // its own internal scroll rather than the page scrolling.
    <div className="h-full flex flex-col">
      <ChatWindow projectId={project.id} />
    </div>
  );
}
