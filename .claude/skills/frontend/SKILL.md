# Frontend Development Rules — HYLIST

> **Stack:** Next.js 15 (App Router) + TypeScript + React Query v5 + Zustand + SSE
> **Đọc khi:** viết page, component, hook, API call

---

## File Structure

```
frontend/src/
├── app/
│   ├── (auth)/
│   │   ├── login/page.tsx
│   │   └── register/page.tsx
│   ├── (dashboard)/
│   │   ├── layout.tsx              ← Auth guard + sidebar
│   │   ├── board/page.tsx          ← Kanban Board (Phase 1)
│   │   ├── projects/page.tsx
│   │   └── tasks/[id]/page.tsx     ← Task detail + prediction card
│   └── layout.tsx                  ← Root layout + QueryProvider
├── components/
│   ├── ui/                         ← Base: Button, Input, Badge, Modal
│   ├── kanban/
│   │   ├── KanbanBoard.tsx         ← Kéo thả tasks giữa cột
│   │   ├── TaskCard.tsx            ← Hiển thị tags + predicted time
│   │   └── Column.tsx
│   ├── task/
│   │   ├── TaskForm.tsx            ← Create/Edit task
│   │   ├── PredictionCard.tsx      ← Predicted time + SHAP explanation
│   │   └── TagBadge.tsx            ← NLP-generated tags
│   └── agent/
│       ├── AgentComment.tsx        ← Agent-generated comments
│       └── HITLReviewCard.tsx      ← Pending review với approve/reject
├── hooks/
│   ├── useTasks.ts                 ← React Query CRUD hooks
│   ├── useProjects.ts
│   ├── useSSE.ts                   ← SSE hook cho real-time NLP tags
│   └── usePrediction.ts            ← Hook gọi /api/v1/predict
├── lib/
│   └── api/                        ← Auto-generated từ openapi.yaml
│       └── index.ts                ← KHÔNG sửa tay — chạy codegen
├── stores/
│   └── ui.store.ts                 ← Zustand: modal open, selected task
└── types/
    └── index.ts                    ← Types bổ sung (không có trong auto-gen)
```

---

## API Client — Auto-generated (KHÔNG viết tay)

```bash
# Chạy lại khi openapi.yaml thay đổi
npx openapi-typescript-codegen \
  --input ../openapi.yaml \
  --output src/lib/api \
  --client fetch

# Dùng trong code:
import { TasksService } from "@/lib/api"

const task = await TasksService.createTask({
  title: "...",
  priority: 3,
  estimatedHours: 4,
})
```

> **Rule:** KHÔNG gọi `fetch("/api/v1/...")` trực tiếp. Luôn dùng generated client.

---

## React Query Hooks Pattern

```typescript
// hooks/useTasks.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { TasksService } from "@/lib/api"

// Query keys — centralized để invalidate chính xác
const TASK_KEYS = {
  all:     (projectId: string) => ["tasks", projectId] as const,
  detail:  (taskId: string)    => ["task", taskId] as const,
}

export function useTasks(projectId: string) {
  return useQuery({
    queryKey: TASK_KEYS.all(projectId),
    queryFn:  () => TasksService.getTasks(projectId),
    staleTime: 30_000,   // Cache 30s — không refetch liên tục
  })
}

export function useCreateTask() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: TasksService.createTask,
    onSuccess: (newTask, vars) => {
      // Optimistic: add task vào cache ngay không cần refetch
      qc.setQueryData(TASK_KEYS.all(vars.projectId), (old: Task[] = []) =>
        [...old, newTask.data]
      )
    },
  })
}

export function useUpdateTaskStatus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ taskId, status }: { taskId: string; status: string }) =>
      TasksService.updateTask(taskId, { status }),
    onSettled: (_, __, { taskId }) => {
      qc.invalidateQueries({ queryKey: TASK_KEYS.detail(taskId) })
    },
  })
}
```

---

## SSE Hook — Real-time NLP Tag Updates (Phase 3)

```typescript
// hooks/useSSE.ts
export function useTaskTagUpdates(taskId: string) {
  const qc = useQueryClient()

  useEffect(() => {
    const source = new EventSource(
      `${process.env.NEXT_PUBLIC_API_URL}/api/v1/tasks/${taskId}/tag-stream`,
      { withCredentials: true }
    )

    source.onmessage = (e) => {
      const { tags, confidence }: { tags: string[]; confidence: number } = JSON.parse(e.data)
      // Optimistic update — không refetch
      qc.setQueryData(["task", taskId], (old: Task | undefined) =>
        old ? { ...old, tags, nlpConfidence: confidence } : old
      )
    }

    source.onerror = () => {
      source.close()  // Auto-close on error — component re-mount sẽ reconnect
    }

    return () => source.close()   // ⚠️ BẮT BUỘC cleanup
  }, [taskId, qc])
}

// FastAPI endpoint tương ứng (backend):
// GET /api/v1/tasks/{task_id}/tag-stream → EventSourceResponse (sse-starlette)
```

---

## SHAP Explanation Display (Phase 2)

```typescript
// components/task/PredictionCard.tsx
interface SHAPExplanation {
  [factor: string]: string  // e.g. { "high_dependency": "+2.1h", "short_title": "-0.5h" }
}

interface PredictionCardProps {
  predictedHours: number
  explanation: SHAPExplanation
  confidence: "high" | "medium" | "low"
}

export function PredictionCard({ predictedHours, explanation, confidence }: PredictionCardProps) {
  return (
    <div className="prediction-card">
      <div className="predicted-time">
        <span className="label">AI Estimate</span>
        <span className="value">{predictedHours}h</span>
        <ConfidenceBadge confidence={confidence} />
      </div>
      <div className="explanation">
        <p className="explanation-title">Factors:</p>
        {Object.entries(explanation).map(([factor, impact]) => (
          <div key={factor} className={`factor ${impact.startsWith("+") ? "positive" : "negative"}`}>
            <span>{factor.replace(/_/g, " ")}</span>
            <span className="impact">{impact}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
```

---

## HITL Review Component (Phase 4)

```typescript
// components/agent/HITLReviewCard.tsx
export function HITLReviewCard({ agentAction }: { agentAction: AgentAction }) {
  const { mutate: approve } = useMutation({
    mutationFn: () => AgentActionsService.approveAction(agentAction.id),
  })
  const { mutate: reject } = useMutation({
    mutationFn: () => AgentActionsService.rejectAction(agentAction.id),
  })

  return (
    <div className="hitl-card pending">
      <span className="badge">AI Suggestion — Needs Review</span>
      <p className="confidence">Confidence: {(agentAction.confidence * 100).toFixed(0)}%</p>
      <div className="content">{agentAction.proposedContent}</div>
      <div className="actions">
        <button onClick={() => approve()} className="btn-approve">✓ Apply</button>
        <button onClick={() => reject()} className="btn-reject">✗ Reject</button>
      </div>
    </div>
  )
}
```

---

## Zustand UI Store

```typescript
// stores/ui.store.ts
interface UIStore {
  selectedTaskId: string | null
  isTaskModalOpen: boolean
  kanbanView: "board" | "list"
  selectTask: (id: string | null) => void
  openTaskModal: () => void
  closeTaskModal: () => void
  setView: (view: "board" | "list") => void
}

export const useUIStore = create<UIStore>((set) => ({
  selectedTaskId: null,
  isTaskModalOpen: false,
  kanbanView: "board",
  selectTask: (id) => set({ selectedTaskId: id }),
  openTaskModal: () => set({ isTaskModalOpen: true }),
  closeTaskModal: () => set({ isTaskModalOpen: false, selectedTaskId: null }),
  setView: (view) => set({ kanbanView: view }),
}))

// Nguyên tắc Zustand:
// ✅ UI state: modal open, selected item, view mode
// ✅ Server state: React Query (useTasks, useProjects)
// ❌ KHÔNG dùng Zustand cho server data
```

---

## Environment Variables

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000      # Backend URL
NEXT_PUBLIC_APP_NAME=HYLIST
# KHÔNG prefix NEXT_PUBLIC_ cho secrets → sẽ bị expose ra client
```

---

## Self-Check

```
[ ] KHÔNG gọi fetch/axios trực tiếp — dùng generated API client
[ ] KHÔNG hardcode URL — dùng process.env.NEXT_PUBLIC_API_URL
[ ] Loading state và error state đã xử lý (skeleton/spinner/error boundary)
[ ] SSE hook có cleanup: return () => source.close()
[ ] KHÔNG dùng any/unknown type không cần thiết
[ ] Server state dùng React Query — UI state dùng Zustand (không trộn lẫn)
[ ] PredictionCard hiển thị SHAP explanation cùng predicted hours
[ ] HITLReviewCard có approve/reject buttons
[ ] KHÔNG có console.log debug
[ ] KHÔNG hardcode credentials hay secrets
```
