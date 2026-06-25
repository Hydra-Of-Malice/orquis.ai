import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../services/api";
import { PageHeader } from "../components/layout/PageHeader";
import { Card } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Avatar } from "../components/ui/Avatar";
import { Button } from "../components/ui/Button";
import {
  CheckSquare, Grid, List as ListIcon, Calendar,
  Plus, Filter, Users, FolderOpen, ArrowUpRight, Loader2
} from "lucide-react";
import styles from "./Tasks.module.css";
import clsx from "clsx";

const STATUS_CYCLE: Record<string, string> = {
  todo: "in_progress",
  in_progress: "done",
  done: "todo",
};

const STATUS_LABEL: Record<string, string> = {
  todo: "Todo",
  in_progress: "In Progress",
  done: "Done",
};

export const Tasks: React.FC = () => {
  const queryClient = useQueryClient();
  const [view, setView] = useState<"board" | "list">("board");
  const [filter, setFilter] = useState<"all" | "mine" | "overdue">("all");
  const [priorityFilter, setPriorityFilter] = useState("all");
  const [isAddingTask, setIsAddingTask] = useState(false);
  const [newTaskTitle, setNewTaskTitle] = useState("");
  const [newTaskAssignee, setNewTaskAssignee] = useState("");
  const [newTaskPriority, setNewTaskPriority] = useState<"low" | "medium" | "high" | "urgent">("medium");
  const [newTaskDueDate, setNewTaskDueDate] = useState("");

  // ── Real API queries ────────────────────────────────────────────────────────
  const { data: items = [], isLoading } = useQuery({
    queryKey: ["action-items"],
    queryFn: () => api.get("/action-items?limit=200").then(r => r.data),
    refetchInterval: 15000,
  });

  const { data: stats } = useQuery({
    queryKey: ["action-items-stats"],
    queryFn: () => api.get("/action-items/stats").then(r => r.data),
  });

  // ── Mutations ──────────────────────────────────────────────────────────────
  const createMutation = useMutation({
    mutationFn: (payload: any) => api.post("/action-items", payload).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["action-items"] });
      queryClient.invalidateQueries({ queryKey: ["action-items-stats"] });
      setIsAddingTask(false);
      setNewTaskTitle("");
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, ...payload }: any) =>
      api.patch(`/action-items/${id}`, payload).then(r => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["action-items"] });
      queryClient.invalidateQueries({ queryKey: ["action-items-stats"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/action-items/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["action-items"] }),
  });

  // ── Derived / filtering ────────────────────────────────────────────────────
  const today = new Date().toISOString().slice(0, 10);

  const filteredItems = items.filter((item: any) => {
    let basic = true;
    if (filter === "overdue") basic = item.status !== "done" && !!item.due_date && item.due_date < today;
    let priorityMatch = priorityFilter === "all" || item.priority === priorityFilter;
    return basic && priorityMatch;
  });

  // Get unique assignees from real data
  const assignees = [...new Set(items.map((i: any) => i.assignee_name).filter(Boolean))];

  const handleAddTask = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTaskTitle.trim()) return;
    createMutation.mutate({
      title: newTaskTitle,
      assignee_name: newTaskAssignee || undefined,
      priority: newTaskPriority,
      status: "todo",
      due_date: newTaskDueDate || undefined,
      source: "manual",
    });
  };

  const handleCycleStatus = (item: any) => {
    updateMutation.mutate({ id: item.id, status: STATUS_CYCLE[item.status] || "todo" });
  };

  const getPriorityClass = (p: string) => {
    if (p === "urgent") return styles.priorityUrgent;
    if (p === "high") return styles.priorityHigh;
    if (p === "medium") return styles.priorityMedium;
    return styles.priorityLow;
  };

  const totalCount = stats?.total_open ?? items.filter((i: any) => i.status !== "done").length;
  const overdueCount = stats?.overdue ?? 0;
  const completedCount = stats?.completed_this_week ?? items.filter((i: any) => i.status === "done").length;

  return (
    <div className={styles.container}>
      <PageHeader
        breadcrumbs={["Tasks", "Action Items Board"]}
        actions={
          <div className={styles.headerRightActions}>
            <Button variant="outline" size="sm" icon={<Plus size={14} />} onClick={() => setIsAddingTask(!isAddingTask)}>
              New Task
            </Button>
            <div className={styles.viewToggles}>
              <button className={clsx(styles.toggleBtn, view === "board" && styles.toggleActive)} onClick={() => setView("board")} title="Board View">
                <Grid size={16} />
              </button>
              <button className={clsx(styles.toggleBtn, view === "list" && styles.toggleActive)} onClick={() => setView("list")} title="List View">
                <ListIcon size={16} />
              </button>
            </div>
          </div>
        }
      />

      <div className={styles.content}>
        {/* Summary Strip */}
        <div className={styles.summaryStrip}>
          <div className={`${styles.stripCard} glass-card`}>
            <span className={styles.stripLabel}>Open Tasks</span>
            <span className={styles.stripValue}>{totalCount}</span>
          </div>
          <div className={`${styles.stripCard} glass-card`}>
            <span className={styles.stripLabel} style={{ color: "var(--red)" }}>Overdue</span>
            <span className={styles.stripValue} style={{ color: "var(--red)" }}>{overdueCount}</span>
          </div>
          <div className={`${styles.stripCard} glass-card`}>
            <span className={styles.stripLabel} style={{ color: "var(--emerald)" }}>Done This Week</span>
            <span className={styles.stripValue} style={{ color: "var(--emerald)" }}>{completedCount}</span>
          </div>
        </div>

        {/* Filter Bar */}
        <div className={`${styles.filterBar} glass-card`}>
          <div className={styles.filterTabs}>
            {(["all", "mine", "overdue"] as const).map((tab) => (
              <button key={tab} className={clsx(styles.filterTabBtn, filter === tab && styles.filterTabActive)} onClick={() => setFilter(tab)}>
                {tab === "all" ? "All Tasks" : tab === "mine" ? "Assigned to Me" : "Overdue"}
              </button>
            ))}
          </div>
          <div className={styles.dropdownFilters}>
            <div className={styles.filterGroup}>
              <Filter size={12} className={styles.filterIcon} />
              <select className={styles.filterSelect} value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)}>
                <option value="all">All Priorities</option>
                <option value="urgent">Urgent</option>
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
            </div>
          </div>
        </div>

        {/* Add Task Form */}
        {isAddingTask && (
          <div className={`${styles.addTaskRowForm} glass-card animate-slide-up`}>
            <form onSubmit={handleAddTask} className={styles.addForm}>
              <div className={styles.formCol}>
                <label>Task Description</label>
                <input type="text" placeholder="What needs to be done?" value={newTaskTitle}
                  onChange={(e) => setNewTaskTitle(e.target.value)} className={styles.formInput} required />
              </div>
              <div className={styles.formColSmall}>
                <label>Assignee</label>
                <input type="text" placeholder="Name" value={newTaskAssignee}
                  onChange={(e) => setNewTaskAssignee(e.target.value)} className={styles.formInput} />
              </div>
              <div className={styles.formColSmall}>
                <label>Priority</label>
                <select value={newTaskPriority} onChange={(e) => setNewTaskPriority(e.target.value as any)} className={styles.formSelect}>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="urgent">Urgent</option>
                </select>
              </div>
              <div className={styles.formColSmall}>
                <label>Due Date</label>
                <input type="date" value={newTaskDueDate} onChange={(e) => setNewTaskDueDate(e.target.value)} className={styles.formInput} />
              </div>
              <div className={styles.formButtons}>
                <Button type="button" variant="outline" size="sm" onClick={() => setIsAddingTask(false)}>Cancel</Button>
                <Button type="submit" variant="primary" size="sm" disabled={createMutation.isPending}>
                  {createMutation.isPending ? "Saving..." : "Add Task"}
                </Button>
              </div>
            </form>
          </div>
        )}

        {isLoading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "3rem", color: "var(--text-muted)" }}>
            <Loader2 size={24} style={{ animation: "spin 1s linear infinite" }} />
          </div>
        ) : view === "board" ? (
          <div className={styles.board}>
            {(["todo", "in_progress", "done"] as const).map((col) => {
              const colItems = filteredItems.filter((i: any) => i.status === col);
              const headerColorClass = col === "todo" ? styles.headerPending : col === "in_progress" ? styles.headerProgress : styles.headerDone;
              return (
                <div key={col} className={styles.column}>
                  <div className={clsx(styles.columnHeader, headerColorClass)}>
                    <h3>{STATUS_LABEL[col]}</h3>
                    <Badge className="badge-gray">{colItems.length}</Badge>
                  </div>
                  <div className={styles.cardsList}>
                    {colItems.map((item: any) => (
                      <Card key={item.id} className={clsx(styles.card, styles[`border-${item.priority}`])}>
                        <div className={styles.cardHeader}>
                          <span className={clsx(styles.priorityBadgeText, getPriorityClass(item.priority))}>{item.priority}</span>
                          <span className={styles.cardTitle}>{item.title}</span>
                        </div>

                        {/* Integration badges */}
                        {(item.jira_id || item.linear_id) && (
                          <div style={{ display: "flex", gap: "4px", marginTop: "4px" }}>
                            {item.jira_id && <Badge className="badge-indigo" style={{ fontSize: "0.68rem" }}>Jira: {item.jira_id}</Badge>}
                            {item.linear_id && <Badge className="badge-gray" style={{ fontSize: "0.68rem" }}>Linear: {item.linear_id}</Badge>}
                          </div>
                        )}

                        <div className={styles.cardMeta}>
                          <div className={clsx(styles.dueMeta, item.status !== "done" && item.due_date && item.due_date < today && styles.overdueDue)}>
                            <Calendar size={11} />
                            <span>{item.due_date || "No due date"}</span>
                          </div>
                        </div>

                        <div className={styles.cardFooter}>
                          <div className={styles.assigneeMeta}>
                            {item.assignee_name && <><Avatar name={item.assignee_name} size="xs" /><span>{item.assignee_name}</span></>}
                          </div>
                          <button className={col !== "done" ? styles.statusActionBtn : styles.reopenBtn} onClick={() => handleCycleStatus(item)}>
                            {col === "todo" ? "Start" : col === "in_progress" ? "Complete" : "Reopen"}
                          </button>
                        </div>
                      </Card>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <Card className={styles.tableCard}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Assignee</th>
                  <th>Due Date</th>
                  <th>Priority</th>
                  <th>Integrations</th>
                  <th>Status</th>
                  <th style={{ textAlign: "right" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.map((item: any) => (
                  <tr key={item.id} className={clsx(item.status === "done" && styles.rowCompleted, styles.tableRowItem)}>
                    <td className={styles.titleCol}>
                      <span className={clsx(styles.tableTitle, item.status === "done" && styles.lineThroughTitle)}>{item.title}</span>
                    </td>
                    <td>
                      {item.assignee_name && (
                        <div className={styles.tableAssignee}>
                          <Avatar name={item.assignee_name} size="xs" />
                          <span>{item.assignee_name}</span>
                        </div>
                      )}
                    </td>
                    <td>
                      <span className={clsx(item.status !== "done" && item.due_date && item.due_date < today && styles.overdueText)}>
                        {item.due_date || "—"}
                      </span>
                    </td>
                    <td>
                      <span className={clsx(styles.tablePriority, getPriorityClass(item.priority))}>{item.priority}</span>
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: "4px" }}>
                        {item.jira_id && <Badge className="badge-indigo" style={{ fontSize: "0.68rem" }}>Jira ✓</Badge>}
                        {item.linear_id && <Badge className="badge-gray" style={{ fontSize: "0.68rem" }}>Linear ✓</Badge>}
                      </div>
                    </td>
                    <td>
                      <Badge className={item.status === "done" ? "badge-emerald" : item.status === "in_progress" ? "badge-indigo" : "badge-gray"}>
                        {STATUS_LABEL[item.status] || item.status}
                      </Badge>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <Button variant="ghost" size="sm" onClick={() => handleCycleStatus(item)}>
                        {item.status === "todo" ? "Start" : item.status === "in_progress" ? "Complete" : "Reopen"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </div>
  );
};

export default Tasks;
