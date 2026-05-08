"use client";

import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { api } from "@/lib/api/client";
import { useAuthStore } from "@/lib/auth/session";
import { useSSE } from "@/hooks/useSSE";
import TaskCard from "./TaskCard";
import type { components } from "@/lib/api/types";

type Task = components["schemas"]["TaskResponse"];

const COLUMNS = [
  { id: "todo",        title: "To Do",       accent: "from-slate-500/20 to-slate-500/5" },
  { id: "in_progress", title: "In Progress",  accent: "from-blue-500/20 to-blue-500/5" },
  { id: "review",      title: "Review",       accent: "from-yellow-500/20 to-yellow-500/5" },
  { id: "done",        title: "Done",         accent: "from-green-500/20 to-green-500/5" },
];

const createTaskSchema = z.object({
  title: z.string().min(3, "Tiêu đề tối thiểu 3 ký tự"),
  description: z.string().optional(),
  priority_score: z.number().int().min(1).max(5),
  estimated_time: z.number().positive().optional(),
});

type CreateTaskForm = z.infer<typeof createTaskSchema>;

export default function KanbanBoard() {
  const queryClient = useQueryClient();
  const token = useAuthStore((s) => s.token);
  const [updatingTaskIds, setUpdatingTaskIds] = useState<Set<string>>(new Set());
  const [showCreateModal, setShowCreateModal] = useState(false);

  // ── Fetch tasks ──────────────────────────────────────────────────────────────
  const { data: response, isLoading } = useQuery({
    queryKey: ["tasks"],
    queryFn: async () => {
      const { data, error } = await api.GET("/tasks", {});
      if (error) throw error;
      return data;
    },
    enabled: !!token,
  });
  const tasks: Task[] = (response?.data as Task[]) ?? [];

  // ── SSE Real-time ─────────────────────────────────────────────────────────────
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  useSSE(
    `/api/v1/events/stream`,
    {
      tags_updated: useCallback(
        (data: unknown) => {
          const { task_id, tags } = data as { task_id: string; tags: string[] };

          // Optimistic update: update tags trong cache ngay lập tức
          queryClient.setQueryData(["tasks"], (old: typeof response) => {
            if (!old?.data) return old;
            return {
              ...old,
              data: (old.data as Task[]).map((t) =>
                t.id === task_id ? { ...t, tags } : t
              ),
            };
          });

          // Flash "updating" state trong 2 giây
          setUpdatingTaskIds((prev) => {
            const next = new Set(prev);
            next.add(task_id);
            setTimeout(() => {
              setUpdatingTaskIds((p) => {
                const n = new Set(p);
                n.delete(task_id);
                return n;
              });
            }, 2000);
            return next;
          });
        },
        [queryClient]
      ),

      prediction_done: useCallback(
        (data: unknown) => {
          // Invalidate để refetch với ML prediction mới
          queryClient.invalidateQueries({ queryKey: ["tasks"] });
        },
        [queryClient]
      ),
    },
    !!token
  );

  // ── Create Task ───────────────────────────────────────────────────────────────
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CreateTaskForm>({
    resolver: zodResolver(createTaskSchema),
    defaultValues: { priority_score: 3 },
  });

  const createMutation = useMutation({
    mutationFn: async (values: CreateTaskForm) => {
      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const Cookies = (await import("js-cookie")).default;
      const authToken = Cookies.get("hylist_token") ?? "";
      const res = await fetch(`${apiBase}/api/v1/tasks`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${authToken}`,
          "Idempotency-Key": crypto.randomUUID(),
        },
        body: JSON.stringify({
          title: values.title,
          description: values.description ?? "",
          priority_score: values.priority_score,
          estimated_time: values.estimated_time ?? 2,
          status: "todo",
        }),
      });
      if (!res.ok) throw new Error("Failed to create task");
      return res.json();
    },

    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      setShowCreateModal(false);
      reset();
    },
  });

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-purple-500/30 border-t-purple-500" />
          <p className="text-sm text-slate-500">Loading tasks...</p>
        </div>
      </div>
    );
  }

  const inputClass =
    "w-full rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-slate-500 outline-none transition focus:border-purple-500/50 focus:ring-2 focus:ring-purple-500/20";

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Kanban Board</h2>
          <p className="mt-0.5 text-sm text-slate-500">
            {tasks.length} tasks · AI tagging enabled
            <span className="ml-2 inline-flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-green-400" />
              <span className="text-green-400 text-xs">Live</span>
            </span>
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-purple-500 to-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-purple-500/25 transition hover:opacity-90"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Task
        </button>
      </div>

      {/* Columns */}
      <div className="flex flex-1 gap-4 overflow-x-auto pb-4">
        {COLUMNS.map((col) => {
          const colTasks = tasks.filter((t) => t.status === col.id);
          return (
            <div
              key={col.id}
              className="flex h-full min-w-[280px] max-w-[320px] flex-1 flex-col rounded-2xl border border-white/5 bg-white/[0.02] p-3"
            >
              {/* Column header */}
              <div className={`mb-3 flex items-center justify-between rounded-xl bg-gradient-to-r p-3 ${col.accent}`}>
                <span className="text-sm font-semibold text-white">{col.title}</span>
                <span className="flex h-5 min-w-[20px] items-center justify-center rounded-full bg-white/10 px-1.5 text-xs font-bold text-white">
                  {colTasks.length}
                </span>
              </div>

              {/* Task cards */}
              <div className="flex flex-1 flex-col gap-2 overflow-y-auto">
                {colTasks.map((task) => (
                  <TaskCard
                    key={task.id}
                    task={task}
                    isUpdating={updatingTaskIds.has(task.id)}
                  />
                ))}

                {colTasks.length === 0 && (
                  <div className="flex flex-1 items-center justify-center rounded-xl border-2 border-dashed border-white/5 p-6 text-center">
                    <p className="text-xs text-slate-600">Drop tasks here</p>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Create Task Modal */}
      {showCreateModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={() => setShowCreateModal(false)}
        >
          <div
            className="w-full max-w-md rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="mb-5 text-lg font-semibold text-white">Create Task</h3>
            <p className="mb-5 text-xs text-slate-500">
              🤖 AI sẽ tự động gán tag (Bug/Feature/Urgent/Research) sau khi tạo
            </p>

            <form
              onSubmit={handleSubmit((v) => createMutation.mutate(v))}
              className="space-y-4"
            >
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">Title *</label>
                <input {...register("title")} placeholder="Fix crash on login screen" className={inputClass} />
                {errors.title && <p className="mt-1 text-xs text-red-400">{errors.title.message}</p>}
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-300">Description</label>
                <textarea
                  {...register("description")}
                  placeholder="Describe the task..."
                  rows={3}
                  className={`${inputClass} resize-none`}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-300">Priority (1–5)</label>
                  <input
                    {...register("priority_score", { valueAsNumber: true })}
                    type="number"
                    min={1}
                    max={5}
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-300">Est. Hours</label>
                  <input
                    {...register("estimated_time", { valueAsNumber: true })}
                    type="number"
                    min={0.5}
                    step={0.5}
                    placeholder="2"
                    className={inputClass}
                  />
                </div>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="flex-1 rounded-xl border border-white/10 py-2.5 text-sm text-slate-400 hover:text-white transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting || createMutation.isPending}
                  className="flex-1 rounded-xl bg-gradient-to-r from-purple-500 to-indigo-600 py-2.5 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-60"
                >
                  {createMutation.isPending ? "Creating..." : "Create Task"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
