import React, { useState } from "react";
import { PageHeader } from "../components/layout/PageHeader";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Switch } from "../components/ui/Switch";
import { User, Bell, Shield, Key, Globe, Sparkles, Lock, Camera, Mail, LogOut } from "lucide-react";
import styles from "./Settings.module.css";
import clsx from "clsx";
import { useAuthStore } from "../store/authStore";

export const Settings: React.FC = () => {
  const { user, logout } = useAuthStore();
  const [activeTab, setActiveTab] = useState<"account" | "notifications" | "security">("account");
  
  // Notification states
  const [notifyEmail, setNotifyEmail] = useState(true);
  const [notifySlack, setNotifySlack] = useState(true);
  const [notifyLive, setNotifyLive] = useState(false);

  // Preference states
  const [selectedLanguage, setSelectedLanguage] = useState("english");
  const [defaultModel, setDefaultModel] = useState("whisper-v3");

  const [isSaved, setIsSaved] = useState(false);
  const [apiKeyRevealed, setApiKeyRevealed] = useState(false);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2000);
  };

  const displayName = user?.display_name || "Rahul Patel";
  const email = user?.email || "rahul.patel@zapper.ai";
  const orgName = user?.org_id ? "Your Workspace" : "Zapper Inc.";
  const initials = displayName
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);


  return (
    <div className={styles.container}>
      <PageHeader breadcrumbs={["Settings", "User Preferences"]} />

      <div className={styles.wrapper}>
        {/* Left Side Settings Navigation */}
        <aside className={styles.sidebar}>
          <button
            className={clsx(styles.subTabBtn, activeTab === "account" && styles.subTabActive)}
            onClick={() => setActiveTab("account")}
          >
            <User size={16} />
            <span>Profile Details</span>
          </button>
          <button
            className={clsx(styles.subTabBtn, activeTab === "notifications" && styles.subTabActive)}
            onClick={() => setActiveTab("notifications")}
          >
            <Bell size={16} />
            <span>Notifications</span>
          </button>
          <button
            className={clsx(styles.subTabBtn, activeTab === "security" && styles.subTabActive)}
            onClick={() => setActiveTab("security")}
          >
            <Shield size={16} />
            <span>API & Webhooks</span>
          </button>

          <button
            className={clsx(styles.subTabBtn)}
            onClick={() => {
              if (window.confirm("Are you sure you want to log out?")) {
                logout();
              }
            }}
            style={{ marginTop: "auto", color: "var(--color-error)" }}
          >
            <LogOut size={16} />
            <span>Logout</span>
          </button>
        </aside>

        {/* Right Side Settings Forms Panel */}
        <main className={styles.pane}>
          {activeTab === "account" && (
            <Card className={styles.card}>
              <div className={styles.sectionTitleRow}>
                <h3>Profile Settings</h3>
                <p className={styles.descText}>Manage your public profile and workspace configuration.</p>
              </div>

              {/* Profile Avatar Upload Mock */}
              <div className={styles.avatarUploadContainer}>
                <div className={styles.avatarPreviewRing}>
                  <div className={styles.avatarPreview}>
                    <span>{initials}</span>
                  </div>
                  <button className={styles.cameraIconBtn} title="Upload custom avatar">
                    <Camera size={12} />
                  </button>
                </div>
                <div className={styles.avatarMeta}>
                  <strong>{displayName}</strong>
                  <span>{user?.role === "admin" ? "Admin" : "Member"} • {orgName}</span>
                </div>
              </div>

              <form className={styles.form} onSubmit={handleSave}>
                <div className={styles.formGrid}>
                  <div className={styles.formGroup}>
                    <label>Full Name</label>
                    <Input defaultValue={displayName} required />
                  </div>
                  <div className={styles.formGroup}>
                    <label>Email Address</label>
                    <Input defaultValue={email} disabled />
                  </div>
                  <div className={styles.formGroup}>
                    <label>Organization Domain</label>
                    <Input defaultValue={email.split("@")[1] || "zapper.ai"} disabled />
                  </div>
                  
                  <div className={styles.formGroup}>
                    <label>Workspace Language</label>
                    <select
                      value={selectedLanguage}
                      onChange={(e) => setSelectedLanguage(e.target.value)}
                      className={styles.settingsSelect}
                    >
                      <option value="english">English (US)</option>
                      <option value="spanish">Spanish (ES)</option>
                      <option value="french">French (FR)</option>
                      <option value="german">German (DE)</option>
                    </select>
                  </div>

                  <div className={styles.formGroup}>
                    <label>Default AI Model</label>
                    <select
                      value={defaultModel}
                      onChange={(e) => setDefaultModel(e.target.value)}
                      className={styles.settingsSelect}
                    >
                      <option value="whisper-v3">Faster-Whisper v3 (Default)</option>
                      <option value="whisper-v2">Whisper Large v2</option>
                      <option value="assembly">AssemblyAI Core</option>
                    </select>
                  </div>
                </div>

                <div className={styles.saveBtnGroup}>
                  <Button variant="primary" size="sm" type="submit">
                    {isSaved ? "Saved Successfully ✓" : "Save Changes"}
                  </Button>
                </div>
              </form>
            </Card>
          )}

          {activeTab === "notifications" && (
            <Card className={styles.card}>
              <div className={styles.sectionTitleRow}>
                <h3>Notification Preferences</h3>
                <p className={styles.descText}>Choose when and how Zapper sends summaries and action alerts.</p>
              </div>

              <div className={styles.switchList}>
                <div className={styles.switchRow}>
                  <div className={styles.switchMeta}>
                    <div className={styles.metaTitleGroup}>
                      <Mail size={16} className={styles.metaIcon} />
                      <strong>Email Summaries</strong>
                    </div>
                    <p>Send me the AI executive summary immediately after the bot leaves the meeting.</p>
                  </div>
                  <Switch checked={notifyEmail} onChange={setNotifyEmail} />
                </div>
                
                <div className={styles.switchRow}>
                  <div className={styles.switchMeta}>
                    <div className={styles.metaTitleGroup}>
                      <Sparkles size={16} className={styles.metaIcon} />
                      <strong>Slack Inbound Ping</strong>
                    </div>
                    <p>Ping Zapper bot alerts inside Slack when overdue tasks are assigned to me.</p>
                  </div>
                  <Switch checked={notifySlack} onChange={setNotifySlack} />
                </div>

                <div className={styles.switchRow}>
                  <div className={styles.switchMeta}>
                    <div className={styles.metaTitleGroup}>
                      <Bell size={16} className={styles.metaIcon} />
                      <strong>Live Tickers</strong>
                    </div>
                    <p>Show toast notifications inside active meetings when action items are detected in real time.</p>
                  </div>
                  <Switch checked={notifyLive} onChange={setNotifyLive} />
                </div>
              </div>
            </Card>
          )}

          {activeTab === "security" && (
            <Card className={styles.card}>
              <div className={styles.sectionTitleRow}>
                <h3>API & Webhooks Keys</h3>
                <p className={styles.descText}>Use these API tokens to fetch transcript data or program webhooks triggered on meeting ends.</p>
              </div>

              <div className={styles.apiKeySection}>
                <div className={styles.apiKeyRow}>
                  <Input
                    value={apiKeyRevealed ? "zp_live_45a7b8c8d2347ebca092" : "••••••••••••••••••••••••••••"}
                    disabled
                    type="text"
                  />
                  <Button variant="outline" size="sm" onClick={() => setApiKeyRevealed(!apiKeyRevealed)}>
                    {apiKeyRevealed ? "Hide Key" : "Reveal Key"}
                  </Button>
                </div>
                <div className={styles.webhookDisclaimer}>
                  <Lock size={12} className={styles.lockIcon} />
                  <span>Never share your API keys in public repositories or client-side packages.</span>
                </div>
              </div>
            </Card>
          )}
        </main>
      </div>
    </div>
  );
};

export default Settings;
