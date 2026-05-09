"use client";

/**
 * ProjectContext — Global project selector
 *
 * Giải quyết vấn đề: task CRUD cần project_id.
 * Pattern: mỗi user có "default project" tự động tạo khi register.
 * Nếu chưa có → show onboarding màn hình tạo project đầu tiên.
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  type ReactNode,
} from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/lib/auth/session";

interface Project {
  id: string;
  name: string;
  description?: string;
  color?: string;
}

interface ProjectContextType {
  currentProject: Project | null;
  projects: Project[];
  isLoading: boolean;
  setCurrentProject: (p: Project) => void;
  needsOnboarding: boolean;
}

const ProjectContext = createContext<ProjectContextType | null>(null);

export function useProject(): ProjectContextType {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error("useProject must be used within ProjectProvider");
  return ctx;
}

export function ProjectProvider({ children }: { children: ReactNode }) {
  const token = useAuthStore((s) => s.token);
  const [currentProject, setCurrentProjectState] = useState<Project | null>(null);
  const queryClient = useQueryClient();
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  // Fetch projects
  const { data: projects = [], isLoading } = useQuery<Project[]>({
    queryKey: ["projects"],
    queryFn: async () => {
      const res = await fetch(`${apiBase}/api/v1/projects`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return [];
      const json = await res.json();
      return (json.data ?? []) as Project[];
    },
    enabled: !!token,
  });

  // Auto-create default project nếu user chưa có project nào
  const createDefaultMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch(`${apiBase}/api/v1/projects`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
          "Idempotency-Key": "default-project-creation",
        },
        body: JSON.stringify({
          name: "My First Workspace",
          description: "Default project — rename to get started",
          color: "#a855f7",
        }),
      });
      if (!res.ok) throw new Error("Failed to create default project");
      const json = await res.json();
      return json.data as Project;
    },
    onSuccess: (project) => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setCurrentProjectState(project);
    },
  });

  // Set current project từ localStorage or first project
  useEffect(() => {
    if (projects.length === 0) return;
    const saved = localStorage.getItem("hylist_current_project");
    if (saved) {
      const found = projects.find((p) => p.id === saved);
      if (found) {
        setCurrentProjectState(found);
        return;
      }
    }
    setCurrentProjectState(projects[0]);
  }, [projects]);

  const setCurrentProject = (p: Project) => {
    setCurrentProjectState(p);
    localStorage.setItem("hylist_current_project", p.id);
  };

  const needsOnboarding =
    !isLoading && projects.length === 0 && !!token && !createDefaultMutation.isPending;

  // Auto-create default project when user has none
  useEffect(() => {
    if (needsOnboarding) {
      createDefaultMutation.mutate();
    }
  }, [needsOnboarding]); // eslint-disable-line

  return (
    <ProjectContext.Provider
      value={{
        currentProject,
        projects,
        isLoading,
        setCurrentProject,
        needsOnboarding,
      }}
    >
      {children}
    </ProjectContext.Provider>
  );
}
