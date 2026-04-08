"use client";

import { useState } from "react";
import type { WeeklyData } from "@/lib/types";

interface ActivityChartProps {
  data: WeeklyData[];
  height?: number;
}

const COLORS = {
  commits: "#10B981",
  papers: "#8B5CF6",
  drafts: "#F59E0B",
  memory: "#EC4899",
};

const LABELS: Record<string, string> = {
  commits: "Commits",
  papers: "Papers",
  drafts: "Drafts",
  memory: "Memory",
};

function formatWeekLabel(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function ActivityChart({ data, height = 160 }: ActivityChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center text-sm text-muted-foreground" style={{ height }}>
        No activity data yet
      </div>
    );
  }

  const categories = ["commits", "papers", "drafts", "memory"] as const;
  const maxTotal = Math.max(
    ...data.map((w) => categories.reduce((sum, c) => sum + (w[c] || 0), 0)),
    1,
  );

  // Chart dimensions
  const barAreaHeight = height - 20; // leave 20px for x-axis labels inside SVG
  const svgWidth = data.length * 60; // 60px per bar for readable labels
  const barW = 36;
  const barGap = 24;

  return (
    <div className="w-full space-y-2">
      {/* Chart area — horizontally scrollable if needed */}
      <div className="relative w-full overflow-x-auto">
        <svg
          width={svgWidth}
          height={height}
          viewBox={`0 0 ${svgWidth} ${height}`}
          className="min-w-full"
          style={{ minWidth: svgWidth }}
        >
          {data.map((week, i) => {
            const x = i * 60 + (barGap / 2);
            let yOffset = barAreaHeight;
            const isHovered = hoveredIndex === i;

            return (
              <g
                key={week.week}
                onMouseEnter={() => setHoveredIndex(i)}
                onMouseLeave={() => setHoveredIndex(null)}
                style={{ cursor: "default" }}
              >
                {/* Invisible hit area */}
                <rect x={i * 60} y={0} width={60} height={height} fill="transparent" />

                {/* Hover highlight */}
                {isHovered && (
                  <rect
                    x={i * 60 + 2}
                    y={0}
                    width={56}
                    height={barAreaHeight}
                    fill="currentColor"
                    className="text-muted-foreground/5"
                    rx={4}
                  />
                )}

                {/* Stacked bar segments */}
                {categories.map((cat) => {
                  const value = week[cat] || 0;
                  if (value === 0) return null;
                  const segmentHeight = (value / maxTotal) * (barAreaHeight - 8);
                  yOffset -= segmentHeight;
                  return (
                    <rect
                      key={cat}
                      x={x}
                      y={yOffset}
                      width={barW}
                      height={segmentHeight}
                      fill={COLORS[cat]}
                      opacity={isHovered ? 1 : 0.75}
                      rx={3}
                    />
                  );
                })}

                {/* X-axis label */}
                <text
                  x={x + barW / 2}
                  y={height - 4}
                  textAnchor="middle"
                  className="fill-muted-foreground"
                  fontSize="9"
                  fontFamily="system-ui, sans-serif"
                >
                  {formatWeekLabel(week.week)}
                </text>
              </g>
            );
          })}
        </svg>

        {/* Tooltip */}
        {hoveredIndex !== null && data[hoveredIndex] && (
          <div
            className="absolute top-0 bg-popover border border-border rounded-lg shadow-lg px-3 py-2 text-xs pointer-events-none z-10"
            style={{
              left: `${((hoveredIndex + 0.5) / data.length) * 100}%`,
              transform: "translateX(-50%)",
            }}
          >
            <p className="font-semibold mb-1">{formatWeekLabel(data[hoveredIndex].week)}</p>
            {categories.map((cat) => {
              const val = data[hoveredIndex]![cat] || 0;
              if (val === 0) return null;
              return (
                <div key={cat} className="flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: COLORS[cat] }} />
                  <span className="text-muted-foreground">{LABELS[cat]}:</span>
                  <span className="font-medium">{val}</span>
                </div>
              );
            })}
            {categories.every((c) => (data[hoveredIndex]![c] || 0) === 0) && (
              <p className="text-muted-foreground">No activity</p>
            )}
          </div>
        )}
      </div>

      {/* Legend — below the chart, never overlapping */}
      <div className="flex items-center justify-end gap-4 px-1">
        {categories.map((cat) => (
          <div key={cat} className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: COLORS[cat] }} />
            <span className="text-[11px] text-muted-foreground">{LABELS[cat]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
