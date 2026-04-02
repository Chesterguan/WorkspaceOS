"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  BookOpen,
  RefreshCw,
  FileText,
  Brain,
  CalendarDays,
  NotebookPen,
  MessageSquare,
  LayoutGrid,
  FlaskConical,
  History,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface NavItem {
  label: string;
  href: string;
  icon: React.ElementType;
}

interface NavGroup {
  items: NavItem[];
}

function navGroups(projectId: string): NavGroup[] {
  return [
    {
      items: [
        {
          label: "Co-Founder",
          href: `/projects/${projectId}/chat`,
          icon: MessageSquare,
        },
        {
          label: "Research",
          href: `/projects/${projectId}/research`,
          icon: FlaskConical,
        },
      ],
    },
    {
      items: [
        {
          label: "Overview",
          href: `/projects/${projectId}/overview`,
          icon: LayoutDashboard,
        },
        {
          label: "Narrative",
          href: `/projects/${projectId}/narrative`,
          icon: BookOpen,
        },
        {
          label: "Blog",
          href: `/projects/${projectId}/blog`,
          icon: NotebookPen,
        },
      ],
    },
    {
      items: [
        {
          label: "Timeline",
          href: `/projects/${projectId}/timeline`,
          icon: History,
        },
        {
          label: "Sync",
          href: `/projects/${projectId}/sync`,
          icon: RefreshCw,
        },
        {
          label: "Drafts",
          href: `/projects/${projectId}/drafts`,
          icon: FileText,
        },
        {
          label: "Posting",
          href: `/projects/${projectId}/posting`,
          icon: CalendarDays,
        },
        {
          label: "Memory",
          href: `/projects/${projectId}/memory`,
          icon: Brain,
        },
      ],
    },
    {
      items: [
        {
          label: "Portfolio Post",
          href: "/portfolio",
          icon: LayoutGrid,
        },
      ],
    },
  ];
}

interface ProjectSidebarProps {
  projectId: string;
}

export function ProjectSidebar({ projectId }: ProjectSidebarProps) {
  const pathname = usePathname();
  const groups = navGroups(projectId);

  return (
    <nav className="flex flex-col py-4 px-2">
      {groups.map((group, gi) => (
        <div key={gi}>
          {gi > 0 && (
            <div className="mx-3 my-2 h-px bg-border/60" />
          )}
          <div className="flex flex-col gap-0.5">
            {group.items.map((item) => {
              const Icon = item.icon;
              const isActive = pathname.startsWith(item.href);

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "relative flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-all duration-150",
                    isActive
                      ? "bg-primary/15 text-primary"
                      : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                  )}
                >
                  {isActive && (
                    <span className="absolute left-0 inset-y-1 w-0.5 bg-primary rounded-full" />
                  )}
                  <Icon className="w-4 h-4 shrink-0" />
                  {item.label}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}
