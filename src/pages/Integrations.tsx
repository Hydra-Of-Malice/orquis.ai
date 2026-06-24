import React, { useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../services/api";
import { PageHeader } from "../components/layout/PageHeader";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import {
  Calendar, Zap, MessageSquare, BookOpen, Settings,
  ExternalLink, CheckCircle, XCircle, AlertCircle,
} from "lucide-react";
import styles from "./Integrations.module.css";
import clsx from "clsx";

// ── Provider metadata ──────────────────────────────────────────────────────────

const PROVIDER_META: Record<string, {
  label: string;
  description: string;
  icon: React.ReactNode;
  color: string;
  what: string[];
}> = {
  google_calendar: {
    label: "Google Calendar",
    description: "Automatically join meetings from your Google Calendar and sync recordings back.",
    icon: <Calendar size={22} />,
    color: "#4285F4",
    what: ["Auto-join scheduled meetings", "Sync meeting links", "Import attendee names"],
  },
  outlook: {
    label: "Microsoft Outlook",
    description: "Sync your Outlook calendar to auto-join Teams and Zoom meetings.",
    icon: <Calendar size={22} />,
    color: "#0078D4",
    what: ["Auto-join Teams meetings", "Sync calendar events", "Import participants"],
  },
  jira: {
    label: "Jira",
    description: "Push action items extracted from meetings directly into Jira as issues.",
    icon: <Settings size={22} />,
    color: "#0052CC",
    what: ["Create issues from action items", "Set priority and assignee", "Track progress in Jira"],
  },
  linear: {
    label: "Linear",
    description: "Sync meeting action items into Linear issues automatically after every call.",
    icon: <Zap size={22} />,
    color: "#5E6AD2",
    what: ["Auto-create Linear issues", "Set team and priority", "Link back to meeting"],
  },
  slack: {
    label: "Slack",
    description: "Post meeting summaries and action items to a Slack channel when meetings end.",
    icon: <MessageSquare size={22} />,
    color: "#4A154B",
    what: ["Post meeting summaries", "List action items per channel", "Notify team on meeting end"],
  },
  notion: {
    label: "Notion",
    description: "Export meeting notes and summaries to a Notion database automatically.",
    icon: <BookOpen size={22} />,
    color: "#ffffff",
    what: ["Export meeting summaries", "Create Notion pages", "Tag and organize by project"],
  },
};

// ── Component ──────────────────────────────────────────────────────────────────

export const Integrations: React.FC = () => {
  const queryClient = useQueryClient();

  // Listen for postMessage from OAuth popup
  useEffect(() => {
    const handler = (event: MessageEvent) => {
      if (event.data?.type === "oauth_callback") {
        queryClient.invalidateQueries({ queryKey: ["integrations"] });
      }
    };
    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, [queryClient]);

  const { data: dbIntegrations = [], isLoading } = useQuery({
    queryKey: ["integrations"],
    queryFn: () => api.get("/integrations").then(r => r.data),
  });

  const disconnectMutation = useMutation({
    mutationFn: (provider: string) => api.delete(`/integrations/${provider}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["integrations"] }),
  });

  // Open OAuth popup window
  const handleConnect = (provider: string) => {
    const token = localStorage.getItem("auth_token");
    const w = 620, h = 720;
    const left = window.screenX + (window.outerWidth - w) / 2;
    const top = window.screenY + (window.outerHeight - h) / 2;
    const popup = window.open(
      `/oauth/${provider}/start?token=${token}`,
      "oauth_popup",
      `width=${w},height=${h},left=${left},top=${top},resizable=yes,scrollbars=yes`
    );
    // Fallback: poll for popup close
    if (popup) {
      const timer = setInterval(() => {
        if (popup.closed) {
          clearInterval(timer);
          queryClient.invalidateQueries({ queryKey: ["integrations"] });
        }
      }, 600);
    }
  };

  const handleDisconnect = (provider: string) => {
    disconnectMutation.mutate(provider);
  };

  return (
    <div className={styles.container}>
      <PageHeader
        breadcrumbs={["Integrations", "Connected Catalog"]}
      />

      <div className={styles.content}>
        {/* Banner */}
        <div className={styles.banner}>
          <Zap size={18} className={styles.bannerIcon} />
          <div>
            <h4>Connect your tools to unlock automations</h4>
            <p>Once connected, Zapper can push action items to Jira/Linear, post summaries to Slack, and auto-join calendar meetings.</p>
          </div>
        </div>

        {isLoading ? (
          <div className={styles.loadingGrid}>
            {[...Array(6)].map((_, i) => (
              <div key={i} className={styles.skeletonCard} />
            ))}
          </div>
        ) : (
          <div className={styles.grid}>
            {dbIntegrations.map((integration: any) => {
              const meta = PROVIDER_META[integration.provider] || {};
              const isConnected = integration.connected;
              const isConfigured = integration.configured;

              return (
                <Card key={integration.provider} className={clsx(styles.card, isConnected && styles.cardConnected)}>
                  {/* Header */}
                  <div className={styles.cardHeader}>
                    <div
                      className={styles.providerIcon}
                      style={{ color: meta.color, background: `${meta.color}18` }}
                    >
                      {meta.icon || <Settings size={22} />}
                    </div>
                    <div className={styles.providerMeta}>
                      <h3>{meta.label || integration.provider}</h3>
                      <span className={styles.category}>{integration.category}</span>
                    </div>
                    {isConnected ? (
                      <Badge className="badge-emerald" style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <CheckCircle size={11} /> Connected
                      </Badge>
                    ) : isConfigured ? (
                      <Badge className="badge-gray">Not connected</Badge>
                    ) : (
                      <Badge className="badge-warning" style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <AlertCircle size={11} /> Setup needed
                      </Badge>
                    )}
                  </div>

                  {/* Description */}
                  <p className={styles.cardDesc}>{meta.description}</p>

                  {/* Feature list */}
                  {meta.what && (
                    <ul className={styles.featureList}>
                      {meta.what.map((f, i) => (
                        <li key={i}>
                          <CheckCircle size={12} className={styles.checkIcon} />
                          {f}
                        </li>
                      ))}
                    </ul>
                  )}

                  {/* Footer */}
                  <div className={styles.cardFooter}>
                    {isConnected && integration.connected_at && (
                      <span className={styles.syncTime}>
                        Connected {new Date(integration.connected_at).toLocaleDateString()}
                      </span>
                    )}

                    {!isConfigured && (
                      <span className={styles.configNote}>
                        Add {integration.provider.toUpperCase()}_CLIENT_ID to .env first
                      </span>
                    )}

                    {isConnected ? (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDisconnect(integration.provider)}
                        className={styles.disconnectBtn}
                      >
                        <XCircle size={14} /> Disconnect
                      </Button>
                    ) : (
                      <Button
                        variant="primary"
                        size="sm"
                        disabled={!isConfigured}
                        onClick={() => handleConnect(integration.provider)}
                        className={styles.connectBtn}
                      >
                        <ExternalLink size={14} /> Connect
                      </Button>
                    )}
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default Integrations;
