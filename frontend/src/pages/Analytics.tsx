import React, { useState, useEffect } from "react";
import { useLocation } from "react-router-dom";
import { PageHeader } from "../components/layout/PageHeader";
import { Card } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { AreaChart } from "../components/charts/AreaChart";
import { BarChart } from "../components/charts/BarChart";
import { ContributionGrid } from "../components/charts/ContributionGrid";
import { HeatmapGrid } from "../components/charts/HeatmapGrid";
import { SparkLine } from "../components/charts/SparkLine";
import { RadarChart } from "../components/charts/RadarChart";
import { StatCard } from "../components/ui/StatCard";
import { ProgressRing } from "../components/ui/ProgressRing";
import { Avatar } from "../components/ui/Avatar";
import { Button } from "../components/ui/Button";
import {
  Calendar,
  Users,
  Target,
  Shield,
  Clock,
  TrendingUp,
  Sparkles,
  UserCheck,
  Brain,
  Lock,
  ArrowRight,
  TrendingDown,
  Info,
  CheckCircle,
  Activity
} from "lucide-react";
import styles from "./Analytics.module.css";
import clsx from "clsx";

export const Analytics: React.FC = () => {
  const location = useLocation();

  const getInitialTab = () => {
    if (location.pathname.includes("/team")) return "team";
    if (location.pathname.includes("/coaching")) return "coaching";
    return "overview";
  };

  const [activeSubTab, setActiveSubTab] = useState<"overview" | "team" | "coaching">(getInitialTab);

  useEffect(() => {
    setActiveSubTab(getInitialTab());
  }, [location.pathname]);



  // Mocks
  const sentimentTrendData = [
    { name: "Week 1", value: 68 },
    { name: "Week 2", value: 74 },
    { name: "Week 3", value: 72 },
    { name: "Week 4", value: 81 },
    { name: "Week 5", value: 85 },
  ];

  const departmentHoursData = [
    { name: "Engineering", value: 42 },
    { name: "Product Design", value: 28 },
    { name: "Sales / Deals", value: 55 },
    { name: "Recruiting", value: 15 },
  ];

  const teamCoachingGoals = [
    { id: "goal_1", name: "Pace Target", val: 88, target: 80, isPos: true, spark: [75, 78, 80, 84, 88] },
    { id: "goal_2", name: "Filler Limit", val: 65, target: 80, isPos: false, spark: [40, 50, 55, 60, 65] },
    { id: "goal_3", name: "Monologue Cap", val: 92, target: 90, isPos: true, spark: [80, 85, 87, 90, 92] }
  ];

  const [completedExercises, setCompletedExercises] = useState<string[]>([]);
  const toggleExercise = (id: string) => {
    setCompletedExercises(prev =>
      prev.includes(id) ? prev.filter(e => e !== id) : [...prev, id]
    );
  };

  return (
    <div className={styles.container}>
      <PageHeader
        breadcrumbs={["Analytics", activeSubTab.charAt(0).toUpperCase() + activeSubTab.slice(1)]}
      />

      {/* Sub tabs bar */}
      <div className={styles.subTabBar}>
        <button
          className={clsx(styles.subTabBtn, activeSubTab === "overview" && styles.subTabActive)}
          onClick={() => setActiveSubTab("overview")}
        >
          Overview
        </button>
        <button
          className={clsx(styles.subTabBtn, activeSubTab === "team" && styles.subTabActive)}
          onClick={() => setActiveSubTab("team")}
        >
          Team Insights
        </button>
        <button
          className={clsx(styles.subTabBtn, activeSubTab === "coaching" && styles.subTabActive)}
          onClick={() => setActiveSubTab("coaching")}
        >
          My Private Coaching
        </button>
      </div>

      <div className={styles.content}>
        {/* ================= OVERVIEW SUBPAGE ================= */}
        {activeSubTab === "overview" && (
          <div className={styles.overview}>
            
            {/* Stat Cards Strip */}
            <div className={styles.kpiStrip}>
              <StatCard
                title="Total Meetings"
                value={38}
                icon={<Calendar size={20} />}
                iconColor="indigo"
                trend={{ value: 8, isPositive: true, label: "vs last month" }}
                sparklineData={[20, 24, 28, 30, 32, 35, 38]}
              />

              <StatCard
                title="Meeting Hours"
                value={24.5}
                formatter={(v) => `${v}h`}
                icon={<Clock size={20} />}
                iconColor="emerald"
                trend={{ value: 8, isPositive: false, label: "vs last month" }}
                sparklineData={[30, 29, 28, 26, 25.5, 25, 24.5]}
              />

              <StatCard
                title="Avg Health Score"
                value={86}
                formatter={(v) => `${v}%`}
                icon={<Shield size={20} />}
                iconColor="amber"
                trend={{ value: 4, isPositive: true, label: "vs org average" }}
                sparklineData={[80, 81, 83, 82, 85, 84, 86]}
              />

              <div className={`${styles.timeReclaimedCard} glass-card`}>
                <div className={styles.timeReclaimedMeta}>
                  <span className={styles.reclaimedLabel}>Time Reclaimed</span>
                  <span className={styles.reclaimedValue}>14.2 hrs</span>
                  <span className={styles.reclaimedSub}>Saved via async reports</span>
                </div>
                <div className={styles.reclaimedIconBox}>
                  <Clock size={24} className={styles.clockAnim} />
                </div>
              </div>
            </div>

            {/* Radar and Sentiment Row */}
            <div className={styles.chartsGrid}>
              <Card className={styles.chartCard}>
                <div className={styles.chartHeaderRow}>
                  <div>
                    <h3>Sentiment Index Trend</h3>
                    <p className={styles.chartSub}>Average meeting mood score progression (last 5 weeks)</p>
                  </div>
                  <Badge className="badge-emerald">+12% Gain</Badge>
                </div>
                <div className={styles.chartWrapper}>
                  <AreaChart data={sentimentTrendData} color="var(--indigo)" />
                </div>
              </Card>

              <Card className={`${styles.chartCard} ${styles.radarMetricCard}`}>
                <h3>Org Meeting Quality Dimensions</h3>
                <p className={styles.chartSub}>Weekly aggregate metrics across 6 vectors</p>
                <div className={styles.radarContainer}>
                  <RadarChart
                    data={[
                      { subject: "Engagement",   value: 88, fullMark: 100 },
                      { subject: "Spk. Balance", value: 75, fullMark: 100 },
                      { subject: "Topic Focus",  value: 92, fullMark: 100 },
                      { subject: "Decision",     value: 84, fullMark: 100 },
                      { subject: "Sentiment",    value: 86, fullMark: 100 },
                      { subject: "Punctuality",  value: 95, fullMark: 100 },
                    ]}
                  />
                </div>
              </Card>
            </div>

            {/* AI Insights & Department Split */}
            <div className={styles.splitRowGrid}>
              <Card className={styles.aiInsightsCard}>
                <div className={styles.aiInsightsHeader}>
                  <Brain size={18} className={styles.brainIcon} />
                  <h3>Weekly Organizational Insights</h3>
                </div>
                <div className={styles.insightsList}>
                  <div className={styles.insightItem}>
                    <Sparkles size={14} className={styles.insightSpark} />
                    <p>AI detected <strong>3 recurring topics</strong> (Faster-Whisper, pgvector, Redis) across 12 different syncs this week.</p>
                  </div>
                  <div className={styles.insightItem}>
                    <Sparkles size={14} className={styles.insightSpark} />
                    <p>Team engagement index was <strong>8% higher</strong> during meetings scheduled before 12:00 PM local time.</p>
                  </div>
                  <div className={styles.insightItem}>
                    <Sparkles size={14} className={styles.insightSpark} />
                    <p>Monologue alerts decreased by <strong>22%</strong> following the rollout of the Leadership coaching tips.</p>
                  </div>
                </div>
              </Card>

              <Card className={styles.chartCard}>
                <h3>Speaking Allocation by Team</h3>
                <p className={styles.chartSub}>Total speaking hours across groups</p>
                <div className={styles.chartWrapper}>
                  <BarChart data={departmentHoursData} />
                </div>
              </Card>
            </div>

            {/* Heatmap Grid / Contribution Graph */}
            <ContributionGrid defaultTimeframe="month" />
          </div>
        )}

        {/* ================= TEAM INSIGHTS ================= */}
        {activeSubTab === "team" && (
          <div className={styles.teamTab}>
            {/* Department Leaderboard & Hours */}
            <div className={styles.teamGrid}>
              
              {/* Member cards layout */}
              <div className={styles.membersColumn}>
                <h3 className={styles.subHeading}>Team Member Analytics</h3>
                
                <div className={styles.memberCards}>
                  {/* Card 1 */}
                  <div className={`${styles.memberCard} glass-card`}>
                    <div className={styles.memberHeader}>
                      <Avatar name="Rahul Patel" size="md" />
                      <div className={styles.memberTitleGroup}>
                        <span className={styles.memberName}>Rahul Patel</span>
                        <span className={styles.memberRole}>Engineering Lead</span>
                      </div>
                      <Badge className="badge-emerald">Top Speaking</Badge>
                    </div>
                    
                    <div className={styles.memberMetrics}>
                      <div className={styles.memberMetric}>
                        <span className={styles.mLabel}>Avg Health</span>
                        <span className={styles.mValue}>88%</span>
                      </div>
                      <div className={styles.memberMetric}>
                        <span className={styles.mLabel}>Hours Spoken</span>
                        <span className={styles.mValue}>12.4h</span>
                      </div>
                      <div className={styles.memberMetric}>
                        <span className={styles.mLabel}>Tasks Synced</span>
                        <span className={styles.mValue}>14</span>
                      </div>
                    </div>

                    <div className={styles.memberProgressGroup}>
                      <div className={styles.progressText}>
                        <span>Action Item Resolution</span>
                        <span>80%</span>
                      </div>
                      <div className={styles.progressRail}>
                        <div className={styles.progressFill} style={{ width: "80%" }} />
                      </div>
                    </div>
                  </div>

                  {/* Card 2 */}
                  <div className={`${styles.memberCard} glass-card`}>
                    <div className={styles.memberHeader}>
                      <Avatar name="Mia Wong" size="md" />
                      <div className={styles.memberTitleGroup}>
                        <span className={styles.memberName}>Mia Wong</span>
                        <span className={styles.memberRole}>Senior Core Dev</span>
                      </div>
                      <Badge className="badge-indigo">Highest Health</Badge>
                    </div>

                    <div className={styles.memberMetrics}>
                      <div className={styles.memberMetric}>
                        <span className={styles.mLabel}>Avg Health</span>
                        <span className={styles.mValue}>91%</span>
                      </div>
                      <div className={styles.memberMetric}>
                        <span className={styles.mLabel}>Hours Spoken</span>
                        <span className={styles.mValue}>8.2h</span>
                      </div>
                      <div className={styles.memberMetric}>
                        <span className={styles.mLabel}>Tasks Synced</span>
                        <span className={styles.mValue}>12</span>
                      </div>
                    </div>

                    <div className={styles.memberProgressGroup}>
                      <div className={styles.progressText}>
                        <span>Action Item Resolution</span>
                        <span>92%</span>
                      </div>
                      <div className={styles.progressRail}>
                        <div className={styles.progressFill} style={{ width: "92%" }} />
                      </div>
                    </div>
                  </div>

                  {/* Card 3 */}
                  <div className={`${styles.memberCard} glass-card`}>
                    <div className={styles.memberHeader}>
                      <Avatar name="Jay Shah" size="md" />
                      <div className={styles.memberTitleGroup}>
                        <span className={styles.memberName}>Jay Shah</span>
                        <span className={styles.memberRole}>Devops Architect</span>
                      </div>
                      <Badge className="badge-gray">Focused Speaker</Badge>
                    </div>

                    <div className={styles.memberMetrics}>
                      <div className={styles.memberMetric}>
                        <span className={styles.mLabel}>Avg Health</span>
                        <span className={styles.mValue}>82%</span>
                      </div>
                      <div className={styles.memberMetric}>
                        <span className={styles.mLabel}>Hours Spoken</span>
                        <span className={styles.mValue}>4.5h</span>
                      </div>
                      <div className={styles.memberMetric}>
                        <span className={styles.mLabel}>Tasks Synced</span>
                        <span className={styles.mValue}>8</span>
                      </div>
                    </div>

                    <div className={styles.memberProgressGroup}>
                      <div className={styles.progressText}>
                        <span>Action Item Resolution</span>
                        <span>75%</span>
                      </div>
                      <div className={styles.progressRail}>
                        <div className={styles.progressFill} style={{ width: "75%" }} />
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Leaderboard Chart comparison */}
              <div className={styles.leaderboardColumn}>
                <Card className={styles.leaderboardCard}>
                  <h3>Peer Contribution Index</h3>
                  <p className={styles.chartSub}>Speaking hours vs items assigned</p>
                  <div className={styles.leaderboardChartWrapper}>
                    <BarChart
                      data={[
                        { name: "Rahul Patel", value: 12 },
                        { name: "Mia Wong", value: 8 },
                        { name: "Jay Shah", value: 5 },
                      ]}
                    />
                  </div>
                </Card>
                
                {/* Meeting Load Map */}
                <Card className={styles.heatmapCard}>
                  <h3>Weekly Team Meeting load</h3>
                  <p className={styles.chartSub}>Average load distribution map by hour</p>
                  <HeatmapGrid weeksCount={12} />
                </Card>
              </div>
            </div>
          </div>
        )}

        {/* ================= MY COACHING ================= */}
        {activeSubTab === "coaching" && (
          <div className={styles.coachingTab}>
            <div className={`${styles.coachingAlert} glass-card`}>
              <UserCheck size={20} className={styles.alertIcon} />
              <div className={styles.alertText}>
                <div className={styles.coachingTitleRow}>
                  <h4>Private Coaching Dashboard</h4>
                  <Badge className="badge-gray">
                    <Lock size={10} style={{ marginRight: 4 }} />
                    Lock Synced
                  </Badge>
                </div>
                <p>This page is private and only visible to you (Rahul Patel). Use these statistics to refine your speaking pacing and communication styles.</p>
              </div>
            </div>

            {/* Weekly Goal Progress Rings */}
            <div className={styles.coachingGoalsRow}>
              {teamCoachingGoals.map((g) => (
                <div key={g.id} className={`${styles.goalProgressCard} glass-card`}>
                  <div className={styles.goalMeta}>
                    <span className={styles.goalName}>{g.name}</span>
                    <span className={styles.goalMetricVal}>{g.val}%</span>
                    <span className={styles.goalTargetText}>Weekly Target: {g.target}%</span>
                  </div>

                  <div className={styles.goalRight}>
                    <ProgressRing
                      value={g.val}
                      size={60}
                      strokeWidth={5}
                      color={g.isPos ? "var(--emerald)" : "var(--amber)"}
                      showValue={false}
                    />
                    <div className={styles.goalSpark}>
                      <SparkLine data={g.spark} color={g.isPos ? "var(--emerald)" : "var(--amber)"} />
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Expandable Exercise list with Mark Complete checkbox states */}
            <Card className={styles.tipsCard}>
              <h3>🎯 Leadership Speaking Micro-Exercises</h3>
              <p className={styles.chartSub}>Select and apply these interactive exercises during your next live sync</p>
              
              <div className={styles.exerciseList}>
                <div className={clsx(styles.exerciseRow, completedExercises.includes("ex_1") && styles.exerciseCompleted)}>
                  <div className={styles.exerciseHeaderRow}>
                    <div className={styles.exerciseMainInfo}>
                      <span className={styles.exerciseNumber}>1</span>
                      <div>
                        <strong>The Three-Second Pause</strong>
                        <p>Before answering a question or transitioning topics, count to 3 silently. This reduces immediate filler word triggers and raises executive presence.</p>
                      </div>
                    </div>
                    <button
                      className={clsx(styles.completeExBtn, completedExercises.includes("ex_1") && styles.completeExBtnActive)}
                      onClick={() => toggleExercise("ex_1")}
                    >
                      {completedExercises.includes("ex_1") ? "Completed ✓" : "Mark Complete"}
                    </button>
                  </div>
                </div>

                <div className={clsx(styles.exerciseRow, completedExercises.includes("ex_2") && styles.exerciseCompleted)}>
                  <div className={styles.exerciseHeaderRow}>
                    <div className={styles.exerciseMainInfo}>
                      <span className={styles.exerciseNumber}>2</span>
                      <div>
                        <strong>Active Solicitation</strong>
                        <p>Ensure you pause speaking at least once every 3 minutes to ask: "Mia, how does this layout match our token draft?" to decrease monologue indexes.</p>
                      </div>
                    </div>
                    <button
                      className={clsx(styles.completeExBtn, completedExercises.includes("ex_2") && styles.completeExBtnActive)}
                      onClick={() => toggleExercise("ex_2")}
                    >
                      {completedExercises.includes("ex_2") ? "Completed ✓" : "Mark Complete"}
                    </button>
                  </div>
                </div>
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
};

export default Analytics;
