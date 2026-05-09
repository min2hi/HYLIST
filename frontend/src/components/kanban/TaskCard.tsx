"use client";

import { useEffect, useRef, useState } from "react";
import type { components } from "@/lib/api/types";

type Task = components["schemas"]["TaskResponse"];

// Tag color mapping
const TAG_COLORS: Record<string, string> = {
  Bug: "bg-red-500/15 text-red-400 ring-1 ring-red-500/30",
  Feature: "bg-blue-500/15 text-blue-400 ring-1 ring-blue-500/30",
  Urgent: "bg-orange-500/15 text-orange-400 ring-1 ring-orange-500/30",
  Research: "bg-violet-500/15 text-violet-400 ring-1 ring-violet-500/30",
};

const TAG_DOTS: Record<string, string> = {
  Bug: "bg-red-400",
  Feature: "bg-blue-400",
  Urgent: "bg-orange-400",
  Research: "bg-violet-400",
};

const PRIORITY_COLORS: Record<number, string> = {
  1: "text-slate-400",
  2: "text-green-400",
  3: "text-yellow-400",
  4: "text-orange-400",
  5: "text-red-400",
};

interface TaskCardProps {
  task: Task;
  isUpdating?: boolean; // True khi đang nhận SSE update
  onClick?: () => void;
}

export default function TaskCard({ task, isUpdating = false, onClick }: TaskCardProps) {
  const [flashTag, setFlashTag] = useState(false);
  const prevTagsRef = useRef(task.tags);

  // Animate khi tags được cập nhật qua SSE
  useEffect(() => {
    const prev = prevTagsRef.current ?? [];
    const curr = task.tags ?? [];
    const hasNewTags = curr.some((t) => !prev.includes(t));
    if (hasNewTags) {
      setFlashTag(true);
      const t = setTimeout(() => setFlashTag(false), 2000);
      prevTagsRef.current = curr;
      return () => clearTimeout(t);
    }
    prevTagsRef.current = curr;
  }, [task.tags]);

  return (
    <div
      onClick={onClick}
      className={[
        "group relative cursor-pointer rounded-xl border bg-white/5 p-4 shadow-sm backdrop-blur-sm",
        "transition-all duration-200 hover:bg-white/10 hover:shadow-md hover:-translate-y-0.5",
        isUpdating
          ? "border-purple-500/40 ring-2 ring-purple-500/20"
          : "border-white/10",
      ].join(" ")}
    >
      {/* Updating indicator */}
      {isUpdating && (
        <div className="absolute right-3 top-3 flex items-center gap-1.5">
          <span className="flex h-1.5 w-1.5 rounded-full bg-purple-400">
            <span className="absolute inline-flex h-1.5 w-1.5 animate-ping rounded-full bg-purple-400 opacity-75" />
          </span>
          <span className="text-[10px] text-purple-400">AI analyzing...</span>
        </div>
      )}

      {/* Title + Priority */}
      <div className="mb-3 flex items-start justify-between gap-2 pr-20">
        <h4 className="text-sm font-medium leading-snug text-slate-100 line-clamp-2">
          {task.title}
        </h4>
        <span
          className={[
            "mt-0.5 shrink-0 text-xs font-bold",
            PRIORITY_COLORS[task.priority_score ?? 3] ?? "text-slate-400",
          ].join(" ")}
        >
          P{task.priority_score}
        </span>
      </div>

      {/* NLP Tags */}
      {task.tags && task.tags.length > 0 && (
        <div
          className={[
            "mb-3 flex flex-wrap gap-1.5 transition-all duration-500",
            flashTag ? "scale-105" : "scale-100",
          ].join(" ")}
        >
          {task.tags.map((tag) => (
            <span
              key={tag}
              className={[
                "flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
                TAG_COLORS[tag] ?? "bg-slate-500/15 text-slate-400 ring-1 ring-slate-500/30",
              ].join(" ")}
            >
              <span
                className={[
                  "h-1.5 w-1.5 rounded-full",
                  TAG_DOTS[tag] ?? "bg-slate-400",
                ].join(" ")}
              />
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Footer: estimated time + ML prediction */}
      <div className="flex items-center justify-between text-xs text-slate-500">
        {/* Estimated time */}
        <div className="flex items-center gap-1">
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>{task.estimated_time ?? "?"}h est.</span>
        </div>

        {/* Assignee avatar placeholder */}
        {task.assignee_id && (
          <div className="flex h-5 w-5 items-center justify-center rounded-full bg-purple-500/30 text-[9px] font-bold text-purple-300">
            {task.assignee_id.slice(0, 2).toUpperCase()}
          </div>
        )}
      </div>
    </div>
  );
}
