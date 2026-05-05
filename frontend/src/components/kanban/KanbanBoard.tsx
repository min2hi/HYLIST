"use client";

import React, { useState } from "react";
import type { components } from "@/lib/api/types";

type Task = components["schemas"]["TaskResponse"];

const COLUMNS = [
  { id: "todo", title: "To Do" },
  { id: "in_progress", title: "In Progress" },
  { id: "review", title: "Review" },
  { id: "done", title: "Done" },
];

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api/client";

export default function KanbanBoard() {
  const { data: response, isLoading, error } = useQuery({
    queryKey: ["tasks"],
    queryFn: async () => {
      // NOTE: This assumes the API returns a standard Response structure.
      // Adjust the endpoint path if it differs in openapi.yaml
      const { data, error } = await api.GET("/tasks", {});
      if (error) throw error;
      return data;
    },
  });

  const tasks = response?.data || [];

  if (isLoading) return <div className="p-4 text-gray-500">Loading tasks...</div>;
  if (error) return <div className="p-4 text-red-500">Error loading tasks: {(error as Error).message}</div>;

  return (
    <div className="flex h-full w-full gap-4 overflow-x-auto p-4">
      {COLUMNS.map((col) => (
        <div
          key={col.id}
          className="flex h-full min-w-[300px] flex-col rounded-xl bg-gray-100/50 p-4 dark:bg-gray-800/50"
        >
          <div className="mb-4 flex items-center justify-between">
            <h3 className="font-semibold text-gray-700 dark:text-gray-300">
              {col.title}
            </h3>
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-gray-200 text-xs font-medium text-gray-600 dark:bg-gray-700 dark:text-gray-400">
              {tasks.filter((t) => t.status === col.id).length}
            </span>
          </div>

          <div className="flex flex-1 flex-col gap-3 overflow-y-auto">
            {tasks
              .filter((t) => t.status === col.id)
              .map((task) => (
                <div
                  key={task.id}
                  className="group relative rounded-lg border border-gray-200 bg-white p-4 shadow-sm transition-all hover:shadow-md dark:border-gray-700 dark:bg-gray-800"
                >
                  <div className="mb-2 flex items-start justify-between gap-2">
                    <h4 className="font-medium text-gray-900 dark:text-gray-100">
                      {task.title}
                    </h4>
                    {task.priority_score >= 4 && (
                      <span className="flex h-5 items-center rounded bg-red-100 px-2 text-xs font-medium text-red-700 dark:bg-red-900/30 dark:text-red-400">
                        P{task.priority_score}
                      </span>
                    )}
                  </div>
                  
                  {task.tags && task.tags.length > 0 && (
                    <div className="mb-3 flex flex-wrap gap-1">
                      {task.tags.map((tag) => (
                        <span
                          key={tag}
                          className="rounded-full bg-blue-100 px-2.5 py-0.5 text-[10px] font-medium text-blue-800 dark:bg-blue-900/30 dark:text-blue-300"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="mt-4 flex items-center justify-between text-xs text-gray-500 dark:text-gray-400">
                    <div className="flex items-center gap-1">
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <span>{task.estimated_time}h</span>
                    </div>
                  </div>
                </div>
              ))}
              
            {tasks.filter((t) => t.status === col.id).length === 0 && (
              <div className="flex flex-1 items-center justify-center rounded-lg border-2 border-dashed border-gray-200 p-8 text-center dark:border-gray-700">
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  No tasks
                </p>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
