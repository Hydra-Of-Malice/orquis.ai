import React, { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../services/api";
import { PageHeader } from "../components/layout/PageHeader";
import { Card } from "../components/ui/Card";
import { Switch } from "../components/ui/Switch";
import { Button } from "../components/ui/Button";
import { Modal } from "../components/ui/Modal";
import { Input } from "../components/ui/Input";
import {
  Cpu, Plus, Sparkles, ArrowRight, Zap, CheckCircle,
  Loader, AlertCircle, Trash2
} from "lucide-react";
import styles from "./Automations.module.css";

const TRIGGER_LABELS: Record<string, string> = {
  "meeting.ended": "When meeting ends",
  "action_item.created": "When action item is detected",
  "decision.detected": "When decision is confirmed",
};

const ACTION_LABELS: Record<string, string> = {
  "create_jira_ticket": "Create Jira issue",
  "create_linear_issue": "Create Linear issue",
  "send_slack_message": "Post to Slack channel",
  "send_email": "Email summary to attendees",
};

const ACTION_ICONS: Record<string, string> = {
  "create_jira_ticket": "🎯",
  "create_linear_issue": "⚡",
  "send_slack_message": "💬",
  "send_email": "📧",
};

export const Automations: React.FC = () => {
  const queryClient = useQueryClient();
  const [isBuilderOpen, setIsBuilderOpen] = useState(false);
  const [newRuleName, setNewRuleName] = useState("");
  const [newRuleTrigger, setNewRuleTrigger] = useState("meeting.ended");
  const [newRuleAction, setNewRuleAction] = useState("send_slack_message");
  const [newRuleChannel, setNewRuleChannel] = useState("general");
  const [newRuleProject, setNewRuleProject] = useState("");

  const { data: automations = [], isLoading } = useQuery({
    queryKey: ["automations"],
    queryFn: () => api.get("/automations").then(r => r.data),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      api.patch(`/automations/${id}`, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["automations"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/automations/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["automations"] }),
  });

  const createMutation = useMutation({
    mutationFn: (payload: any) => api.post("/automations", payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["automations"] });
      setIsBuilderOpen(false);
      setNewRuleName("");
    },
  });

  const handleCreateRule = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newRuleName) return;

    const config: Record<string, string> = {};
    if (newRuleAction === "send_slack_message" && newRuleChannel) {
      config.channel = newRuleChannel;
    }
    if ((newRuleAction === "create_jira_ticket") && newRuleProject) {
      config.project = newRuleProject;
    }

    createMutation.mutate({
      name: newRuleName,
      trigger: newRuleTrigger,
      conditions: {},
      actions: [{ type: newRuleAction, config }],
      is_active: true,
    });
  };

  return (
    <div className={styles.container}>
      <PageHeader
        breadcrumbs={["Automations", "Workflow Builder"]}
        actions={
          <Button variant="primary" size="sm" icon={<Plus size={16} />} onClick={() => setIsBuilderOpen(true)}>
            Create Workflow
          </Button>
        }
      />

      <div className={styles.content}>
        {/* Banner */}
        <div className={styles.alertBanner}>
          <Sparkles size={18} className={styles.alertIcon} />
          <div className={styles.alertMeta}>
            <h4>Automations run automatically after every meeting</h4>
            <p>Create a rule and it will fire for all future meetings — push to Jira, Linear, Slack, and more.</p>
          </div>
        </div>

        {isLoading ? (
          <div className={styles.loadingState}>
            <Loader size={20} className={styles.spinner} />
            <span>Loading automations...</span>
          </div>
        ) : automations.length === 0 ? (
          <div className={styles.emptyState}>
            <Zap size={40} className={styles.emptyIcon} />
            <h3>No automations yet</h3>
            <p>Create your first workflow to auto-sync meetings with Jira, Linear, or Slack.</p>
            <Button variant="primary" size="sm" onClick={() => setIsBuilderOpen(true)}>
              <Plus size={16} /> Create first workflow
            </Button>
          </div>
        ) : (
          <div className={styles.grid}>
            {automations.map((rule: any) => (
              <Card key={rule.id} className={`${styles.ruleCard} ${!rule.is_active ? styles.ruleCardInactive : ""}`}>
                <div className={styles.ruleHeader}>
                  <div className={styles.ruleTitleBlock}>
                    <Cpu size={18} className={styles.cpuIcon} />
                    <h3>{rule.name}</h3>
                  </div>
                  <div className={styles.ruleHeaderActions}>
                    <Switch
                      checked={rule.is_active}
                      onChange={() => toggleMutation.mutate({ id: rule.id, is_active: !rule.is_active })}
                    />
                    <button
                      className={styles.deleteBtn}
                      onClick={() => deleteMutation.mutate(rule.id)}
                      title="Delete automation"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>

                <div className={styles.ruleBody}>
                  {/* Trigger */}
                  <div className={styles.stepRow}>
                    <span className={styles.stepLabel}>Trigger</span>
                    <div className={styles.stepBlock}>
                      <strong>⚡ {TRIGGER_LABELS[rule.trigger] || rule.trigger}</strong>
                    </div>
                  </div>

                  <div className={styles.arrowRow}>
                    <ArrowRight size={14} className={styles.stepArrow} />
                  </div>

                  {/* Actions */}
                  <div className={styles.stepRow}>
                    <span className={styles.stepLabel}>Actions</span>
                    <div className={styles.stepBlock}>
                      {(Array.isArray(rule.actions) ? rule.actions : []).map((act: any, idx: number) => (
                        <div key={idx} className={styles.actionItem}>
                          <span className={styles.actionIcon}>{ACTION_ICONS[act.type] || "🔧"}</span>
                          <strong>{ACTION_LABELS[act.type] || act.type}</strong>
                          {act.config?.channel && <span className={styles.actionConfig}>→ #{act.config.channel}</span>}
                          {act.config?.project && <span className={styles.actionConfig}>→ {act.config.project}</span>}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                <div className={styles.ruleFooter}>
                  {rule.is_active ? (
                    <span className={styles.activeLabel}><CheckCircle size={12} /> Active</span>
                  ) : (
                    <span className={styles.inactiveLabel}><AlertCircle size={12} /> Paused</span>
                  )}
                  {rule.created_at && (
                    <span className={styles.createdAt}>
                      Created {new Date(rule.created_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Workflow Builder Modal */}
      <Modal isOpen={isBuilderOpen} onClose={() => setIsBuilderOpen(false)} title="Create New Workflow">
        <form onSubmit={handleCreateRule} className={styles.modalForm}>
          <div className={styles.formGroup}>
            <label>Workflow Name</label>
            <Input
              required
              placeholder="e.g. Sync Action Items to Linear"
              value={newRuleName}
              onChange={(e) => setNewRuleName(e.target.value)}
            />
          </div>

          <div className={styles.formGroup}>
            <label>Select Trigger</label>
            <select
              value={newRuleTrigger}
              onChange={(e) => setNewRuleTrigger(e.target.value)}
              className={styles.dropdownSelect}
            >
              <option value="meeting.ended">When meeting ends</option>
              <option value="action_item.created">When new Action Item detected</option>
              <option value="decision.detected">When Decision is confirmed</option>
            </select>
          </div>

          <div className={styles.formGroup}>
            <label>Select Action</label>
            <select
              value={newRuleAction}
              onChange={(e) => setNewRuleAction(e.target.value)}
              className={styles.dropdownSelect}
            >
              <option value="send_slack_message">💬 Post to Slack channel</option>
              <option value="create_jira_ticket">🎯 Create Jira issue</option>
              <option value="create_linear_issue">⚡ Create Linear issue</option>
              <option value="send_email">📧 Email summary to attendees</option>
            </select>
          </div>

          {newRuleAction === "send_slack_message" && (
            <div className={styles.formGroup}>
              <label>Slack Channel (without #)</label>
              <Input
                placeholder="general"
                value={newRuleChannel}
                onChange={(e) => setNewRuleChannel(e.target.value)}
              />
            </div>
          )}

          {newRuleAction === "create_jira_ticket" && (
            <div className={styles.formGroup}>
              <label>Jira Project Key</label>
              <Input
                placeholder="e.g. ZAP or PROJ"
                value={newRuleProject}
                onChange={(e) => setNewRuleProject(e.target.value.toUpperCase())}
              />
            </div>
          )}

          <div className={styles.modalActions}>
            <Button variant="outline" type="button" onClick={() => setIsBuilderOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Saving..." : "Save Workflow"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
export default Automations;
