import React, { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { useTheme } from "../context/ThemeContext";
import {
  Sparkles,
  ArrowRight,
  Play,
  Check,
  Zap,
  Shield,
  Clock,
  TrendingUp,
  MessageSquare,
  Users,
  Search,
  CheckCircle,
  Menu,
  X,
  FileText,
  Sliders,
  Database,
  Moon,
  Sun
} from "lucide-react";
import styles from "./Landing.module.css";
import clsx from "clsx";

// Types for sandbox
interface SandboxPreset {
  name: string;
  transcript: string;
  summary: string;
  actions: string[];
}

const presets: SandboxPreset[] = [
  {
    name: "Engineering Sync",
    transcript: "Rahul: I will finalize the database schema migration by Tuesday. Priya, can you review my pull request? Priya: Sure, I will do it tomorrow morning. Also, we need to schedule the load testing for the API next Thursday. Rahul: Perfect, let's target 2 PM next Thursday for the test.",
    summary: "Engineering team aligned on schema migration and load testing. Priya is reviewing the PR tomorrow, and load testing is scheduled for next Thursday afternoon.",
    actions: [
      "Rahul: Finalize database schema migration by Tuesday",
      "Priya: Review Rahul's schema PR tomorrow morning",
      "Rahul & Priya: Execute API load testing on Thursday at 2:00 PM"
    ]
  },
  {
    name: "Sales Demo",
    transcript: "Marc (Client): We are looking for something that integrates directly with Salesforce and Jira. Security is a major concern for our IT team. Sarah (Zapper): We support full OAuth integrations and are SOC2 Type II compliant. I can send over our security package. Marc: That sounds great. Let's set up a follow-up call with our tech lead next Monday.",
    summary: "Sales discovery call with client Marc. Key requirements are Salesforce/Jira sync and SOC2 compliance. Sarah is sharing security credentials ahead of a follow-up technical meeting next Monday.",
    actions: [
      "Sarah: Email SOC2 Type II security package to Marc",
      "Sarah: Send calendar invitation for follow-up call on Monday"
    ]
  },
  {
    name: "Product Brainstorm",
    transcript: "Alex: We need to redesign the homepage. The conversion rate is currently 2.1%, and we should aim for 4%. Maya: I think a dark-mode interactive playground will capture attention. Let's make a mock dashboard that users can interact with. Alex: I love that idea. Maya, can you wireframe that by Friday? Maya: Yes, I will share Figma links on Friday.",
    summary: "Product design meeting discussing conversion optimization. The team approved Maya's idea to build an interactive dashboard playground on the homepage. Maya is wireframing this week.",
    actions: [
      "Maya: Create and share Figma wireframes for interactive landing playground by Friday",
      "Alex: Coordinate benchmarking conversion stats"
    ]
  }
];

export const Landing: React.FC = () => {
  const navigate = useNavigate();
  const { isAuthenticated } = useAuthStore();

  // States
  const [billingCycle, setBillingCycle] = useState<"monthly" | "yearly">("yearly");
  const [activePreset, setActivePreset] = useState<number>(0);
  const [sandboxOutput, setSandboxOutput] = useState<{ summary: string; actions: string[] } | null>(null);
  const [sandboxLoading, setSandboxLoading] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [activeFaq, setActiveFaq] = useState<number | null>(null);

  const { theme, toggleTheme } = useTheme();

  // Run mock AI summarizer
  useEffect(() => {
    setSandboxLoading(true);
    const timer = setTimeout(() => {
      setSandboxOutput({
        summary: presets[activePreset].summary,
        actions: presets[activePreset].actions
      });
      setSandboxLoading(false);
    }, 1200);

    return () => clearTimeout(timer);
  }, [activePreset]);

  // Pricing values
  const getProPrice = () => (billingCycle === "yearly" ? 15 : 19);
  const getEnterprisePrice = () => (billingCycle === "yearly" ? 49 : 59);

  // Scroll to section helper
  const scrollToSection = (id: string) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth" });
      setIsMenuOpen(false);
    }
  };

  return (
    <div className={styles.landingContainer}>
      {/* Navigation Header */}
      <header className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.logo} onClick={() => navigate("/")}>
            <Zap size={22} className={styles.logoIcon} />
            <span>Zapper</span>
          </div>
          <nav className={styles.navMenu}>
            <button onClick={() => scrollToSection("features")}>Features</button>
            <button onClick={() => scrollToSection("sandbox")}>AI Sandbox</button>
            <button onClick={() => scrollToSection("compare")}>Compare</button>
            <button onClick={() => scrollToSection("pricing")}>Pricing</button>
            <button onClick={() => scrollToSection("faq")}>FAQ</button>
          </nav>
        </div>

        <div className={styles.headerRight}>
          <button className={styles.themeToggle} onClick={toggleTheme} title="Switch theme">
            {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          {isAuthenticated ? (
            <button className={styles.btnPrimary} onClick={() => navigate("/dashboard")}>
              Go to Dashboard <ArrowRight size={15} />
            </button>
          ) : (
            <>
              <button className={styles.btnSecondary} onClick={() => navigate("/login")}>
                Login
              </button>
              <button className={styles.btnPrimary} onClick={() => navigate("/login")}>
                Go to App <ArrowRight size={15} />
              </button>
            </>
          )}

          {/* Mobile menu trigger */}
          <button className={styles.mobileTrigger} onClick={() => setIsMenuOpen(!isMenuOpen)}>
            {isMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>
      </header>

      {/* Mobile Drawer */}
      {isMenuOpen && (
        <div className={styles.mobileDrawer}>
          <button onClick={() => scrollToSection("features")}>Features</button>
          <button onClick={() => scrollToSection("sandbox")}>AI Sandbox</button>
          <button onClick={() => scrollToSection("compare")}>Compare</button>
          <button onClick={() => scrollToSection("pricing")}>Pricing</button>
          <button onClick={() => scrollToSection("faq")}>FAQ</button>
          <hr className={styles.drawerDivider} />
          {isAuthenticated ? (
            <button className={styles.btnPrimary} onClick={() => navigate("/dashboard")} style={{ width: "100%" }}>
              Go to Dashboard <ArrowRight size={15} />
            </button>
          ) : (
            <>
              <button className={styles.btnSecondary} onClick={() => navigate("/login")}>
                Login
              </button>
              <button className={styles.btnPrimary} onClick={() => navigate("/login")} style={{ width: "100%" }}>
                Go to App <ArrowRight size={15} />
              </button>
            </>
          )}
        </div>
      )}

      {/* Hero Section */}
      <section className={styles.heroSection}>
        <div className={styles.heroRadialGlow} />

        <div className={styles.heroContent}>
          <div className={styles.announcementBadge}>
            <Sparkles size={13} className={styles.sparkleIcon} />
            <span>Zapper 2.0 is now live</span>
          </div>

          <h1 className={clsx(styles.heroTitle, "gradient-text")}>
            Your AI Chief of Staff <br />
            <span>for Every Conversation</span>
          </h1>

          <p className={styles.heroSubtitle}>
            Zapper joins, records, transcribes, and details every meeting. 
            Automatically generates rich notes, assigns Jira/Linear tasks, and keeps your team aligned.
          </p>

          <div className={styles.heroActions}>
            <button className={styles.btnHeroPrimary} onClick={() => navigate(isAuthenticated ? "/dashboard" : "/login")}>
              {isAuthenticated ? "Go to Dashboard" : "Start for Free"} <ArrowRight size={16} />
            </button>
            <button className={styles.btnHeroSecondary} onClick={() => scrollToSection("sandbox")}>
              Try AI Sandbox <Play size={14} style={{ fill: "currentColor" }} />
            </button>
          </div>

          <div className={styles.socialProof}>
            <p>Trusted by engineering & product squads at</p>
            <div className={styles.logoRow}>
              <span>Linear</span>
              <span>Vercel</span>
              <span>OpenAI</span>
              <span>Stripe</span>
              <span>Ramp</span>
              <span>Notion</span>
            </div>
          </div>
        </div>

        {/* Floating App Mockup */}
        <div className={styles.mockupContainer}>
          <div className={styles.mockupGlow} />
          <div className={styles.mockupFrame}>
            <div className={styles.mockupHeader}>
              <div className={styles.mockupDots}>
                <span />
                <span />
                <span />
              </div>
              <div className={styles.mockupUrl}>zapper.ai/meetings/engineering-sync</div>
            </div>
            <div className={styles.mockupBody}>
              {/* Mini App UI Mockup */}
              <div className={styles.miniSidebar}>
                <div className={styles.miniLogo} />
                <div className={styles.miniNavLines}>
                  <div style={{ width: "80%" }} />
                  <div style={{ width: "60%" }} />
                  <div style={{ width: "70%" }} />
                  <div style={{ width: "50%" }} />
                </div>
              </div>
              <div className={styles.miniMain}>
                <div className={styles.miniHeader}>
                  <div className={styles.miniTitle} />
                  <div className={styles.miniActions} />
                </div>
                <div className={styles.miniGrid}>
                  <div className={styles.miniCard}>
                    <div className={styles.miniCardLine} style={{ width: "40%", height: "12px", background: "var(--indigo)" }} />
                    <div className={styles.miniCardLine} style={{ width: "90%" }} />
                    <div className={styles.miniCardLine} style={{ width: "75%" }} />
                  </div>
                  <div className={styles.miniCard}>
                    <div className={styles.miniCardLine} style={{ width: "30%", height: "12px", background: "var(--emerald)" }} />
                    <div className={styles.miniCardLine} style={{ width: "80%" }} />
                    <div className={styles.miniCardLine} style={{ width: "85%" }} />
                  </div>
                </div>
                <div className={styles.miniWideCard}>
                  <div className={styles.miniCardLine} style={{ width: "20%", height: "12px", background: "var(--amber)" }} />
                  <div className={styles.miniCardLine} style={{ width: "95%" }} />
                  <div className={styles.miniCardLine} style={{ width: "90%" }} />
                  <div className={styles.miniCardLine} style={{ width: "85%" }} />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Grid Section */}
      <section id="features" className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2>Engineered for High-Velocity Teams</h2>
          <p>Ditch the manual note-taking and let AI catalog your organization's memory.</p>
        </div>

        <div className={styles.featuresGrid}>
          <div className={styles.featureCard}>
            <div className={styles.featureIconContainer} style={{ background: "rgba(99, 102, 241, 0.15)", color: "var(--indigo)" }}>
              <Zap size={22} />
            </div>
            <h3>Autopilot Calendar Integration</h3>
            <p>Connects to Google Calendar or Microsoft Outlook. Zapper Bot automatically enters, records, and leaves meetings.</p>
          </div>

          <div className={styles.featureCard}>
            <div className={styles.featureIconContainer} style={{ background: "rgba(16, 185, 129, 0.15)", color: "var(--emerald)" }}>
              <TrendingUp size={22} />
            </div>
            <h3>Radical Meeting Analytics</h3>
            <p>Track talk-to-listen ratios, speaking speed, filler words frequency, and real-time sentiment timelines.</p>
          </div>

          <div className={styles.featureCard}>
            <div className={styles.featureIconContainer} style={{ background: "rgba(245, 158, 11, 0.15)", color: "var(--amber)" }}>
              <MessageSquare size={22} />
            </div>
            <h3>Zapper Copilot & Chat</h3>
            <p>Query your entire database of recordings. Ask questions like "What did Priya say our database migration timeline was?"</p>
          </div>

          <div className={styles.featureCard}>
            <div className={styles.featureIconContainer} style={{ background: "rgba(168, 85, 247, 0.15)", color: "purple" }}>
              <Sliders size={22} />
            </div>
            <h3>Bespoke Summaries</h3>
            <p>Generate summary notes optimized specifically for your audience (Executive TL;DR, technical specs, or sales details).</p>
          </div>

          <div className={styles.featureCard}>
            <div className={styles.featureIconContainer} style={{ background: "rgba(236, 72, 153, 0.15)", color: "pink" }}>
              <Database size={22} />
            </div>
            <h3>Linear & Jira Integration</h3>
            <p>Tasks recognized by AI are compiled instantly. Confirm with one click to push them into Jira, Slack, or Linear rails.</p>
          </div>

          <div className={styles.featureCard}>
            <div className={styles.featureIconContainer} style={{ background: "rgba(59, 130, 246, 0.15)", color: "#3b82f6" }}>
              <Shield size={22} />
            </div>
            <h3>Enterprise Security</h3>
            <p>SOC2 Type II security compliance, end-to-end data encryption, and options to delete transcript data instantly.</p>
          </div>
        </div>
      </section>

      {/* How It Works Section */}
      <section className={styles.section} style={{ background: "var(--bg-subtle)", borderRadius: "var(--radius-2xl)" }}>
        <div className={styles.sectionHeader}>
          <h2>Three Steps to Absolute Alignment</h2>
          <p>Integrate Zapper in seconds and transform how your company records discussions.</p>
        </div>

        <div className={styles.howItWorksSteps}>
          <div className={styles.step}>
            <div className={styles.stepNumber}>1</div>
            <h3>Sync Your Calendars</h3>
            <p>Authorize access once. Zapper watches for calendar links and sends a silent bot to capture audio and screen share.</p>
          </div>
          <div className={styles.step}>
            <div className={styles.stepNumber}>2</div>
            <h3>Talk Comfortably</h3>
            <p>No changes to your flow. Run meetings as usual on Zoom, Google Meet, or Microsoft Teams.</p>
          </div>
          <div className={styles.step}>
            <div className={styles.stepNumber}>3</div>
            <h3>Review & Automate</h3>
            <p>Within minutes, access notes, task grids, transcript highlight links, and push updates directly to engineering boards.</p>
          </div>
        </div>
      </section>

      {/* AI Sandbox Interactive Playground */}
      <section id="sandbox" className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2>Test Our AI Summarizer Live</h2>
          <p>Choose a meeting preset below to see how Zapper analyzes real discussions instantly.</p>
        </div>

        <div className={styles.sandboxWrapper}>
          <div className={styles.sandboxLeft}>
            <div className={styles.presetSelectors}>
              {presets.map((p, idx) => (
                <button
                  key={idx}
                  className={clsx(styles.presetBtn, activePreset === idx && styles.presetBtnActive)}
                  onClick={() => !sandboxLoading && setActivePreset(idx)}
                >
                  {p.name}
                </button>
              ))}
            </div>

            <div className={styles.transcriptBox}>
              <div className={styles.boxHeader}>Meeting Transcript Excerpt</div>
              <textarea
                className={styles.transcriptTextarea}
                readOnly
                value={presets[activePreset].transcript}
              />
            </div>
          </div>

          <div className={styles.sandboxRight}>
            <div className={styles.boxHeader}>
              <Sparkles size={14} className={styles.sparkleIcon} />
              <span>Zapper AI Analysis</span>
            </div>

            <div className={styles.outputBox}>
              {sandboxLoading ? (
                <div className={styles.sandboxLoader}>
                  <div className={styles.loadingPulse} />
                  <p>Running Zapper LLM Summarizer...</p>
                </div>
              ) : (
                sandboxOutput && (
                  <div className={styles.sandboxResults}>
                    <div className={styles.resultGroup}>
                      <h4>Executive Summary</h4>
                      <p className={styles.resultSummaryText}>{sandboxOutput.summary}</p>
                    </div>

                    <div className={styles.resultGroup}>
                      <h4>Detected Action Items</h4>
                      <ul className={styles.resultActionsList}>
                        {sandboxOutput.actions.map((act, index) => (
                          <li key={index}>
                            <CheckCircle size={14} className={styles.actionCheckIcon} />
                            <span>{act}</span>
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div className={styles.sandboxMetrics}>
                      <span className={styles.sandboxMetricItem}>
                        <Clock size={12} /> Diarization: Done
                      </span>
                      <span className={styles.sandboxMetricItem}>
                        <TrendingUp size={12} /> Sentiments: Clean
                      </span>
                    </div>
                  </div>
                )
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Metrics Stat Counter */}
      <section className={styles.metricsSection}>
        <div className={styles.metricItem}>
          <div className={styles.metricNumber}>4.8 hrs</div>
          <div className={styles.metricLabel}>Time Saved / Person / Week</div>
        </div>
        <div className={styles.metricItem}>
          <div className={styles.metricNumber}>94%</div>
          <div className={styles.metricLabel}>Task Action Completion Rate</div>
        </div>
        <div className={styles.metricItem}>
          <div className={styles.metricNumber}>380k+</div>
          <div className={styles.metricLabel}>Meeting Minutes Cataloged</div>
        </div>
      </section>

      {/* Comparison Grid Section */}
      <section id="compare" className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2>Why Teams Switch to Zapper</h2>
          <p>A side-by-side comparison of features compared to traditional assistants.</p>
        </div>

        <div className={styles.comparisonTableContainer}>
          <table className={styles.comparisonTable}>
            <thead>
              <tr>
                <th>Capabilities</th>
                <th className={styles.zapperHeader}>Zapper AI</th>
                <th>Otter.ai</th>
                <th>Read.ai</th>
                <th>Fireflies.ai</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className={styles.featureTitle}>Full Diarization & Monologue Alerts</td>
                <td className={styles.zapperCheck}><Check size={18} /></td>
                <td><Check size={16} /></td>
                <td><Check size={16} /></td>
                <td><Check size={16} /></td>
              </tr>
              <tr>
                <td className={styles.featureTitle}>Differentiated Summaries (Technical/Sales)</td>
                <td className={styles.zapperCheck}><Check size={18} /></td>
                <td>—</td>
                <td>—</td>
                <td>—</td>
              </tr>
              <tr>
                <td className={styles.featureTitle}>Direct Jira & Linear Project Sync</td>
                <td className={styles.zapperCheck}><Check size={18} /></td>
                <td>—</td>
                <td>—</td>
                <td><Check size={16} /></td>
              </tr>
              <tr>
                <td className={styles.featureTitle}>Private Speaking Pace & Coaching Checklists</td>
                <td className={styles.zapperCheck}><Check size={18} /></td>
                <td>—</td>
                <td><Check size={16} /></td>
                <td>—</td>
              </tr>
              <tr>
                <td className={styles.featureTitle}>Cross-Meeting Global AI Search</td>
                <td className={styles.zapperCheck}><Check size={18} /></td>
                <td>—</td>
                <td>—</td>
                <td><Check size={16} /></td>
              </tr>
              <tr>
                <td className={styles.featureTitle}>Trigger-Condition-Action Builder</td>
                <td className={styles.zapperCheck}><Check size={18} /></td>
                <td>—</td>
                <td>—</td>
                <td>—</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      {/* Pricing Section */}
      <section id="pricing" className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2>Simple, Transparent Pricing</h2>
          <p>Find the plan that matches your team's velocity.</p>

          <div className={styles.pricingToggleContainer}>
            <button
              className={clsx(styles.toggleBtn, billingCycle === "monthly" && styles.toggleBtnActive)}
              onClick={() => setBillingCycle("monthly")}
            >
              Monthly
            </button>
            <button
              className={clsx(styles.toggleBtn, billingCycle === "yearly" && styles.toggleBtnActive)}
              onClick={() => setBillingCycle("yearly")}
            >
              Yearly <span className={styles.discountBadge}>-20%</span>
            </button>
          </div>
        </div>

        <div className={styles.pricingCardsGrid}>
          <div className={styles.pricingCard}>
            <div className={styles.priceHeader}>
              <h3>Starter</h3>
              <p>For individuals starting out.</p>
              <div className={styles.priceNum}>$0</div>
              <span className={styles.priceSub}>Free Forever</span>
            </div>
            <ul className={styles.priceFeatures}>
              <li><Check size={14} /> 3 meetings analyzed per month</li>
              <li><Check size={14} /> Basic text-only transcripts</li>
              <li><Check size={14} /> Executive summaries</li>
              <li><Check size={14} /> 7-day retention limit</li>
            </ul>
            <button className={styles.pricingBtn} onClick={() => navigate(isAuthenticated ? "/dashboard" : "/login")}>
              {isAuthenticated ? "Go to Dashboard" : "Get Started Free"}
            </button>
          </div>

          <div className={clsx(styles.pricingCard, styles.proCard)}>
            <div className={styles.proGlow} />
            <div className={styles.popularBadge}>Most Popular</div>
            <div className={styles.priceHeader}>
              <h3>Pro</h3>
              <p>For high-performing teams.</p>
              <div className={styles.priceNum}>
                ${getProPrice()}
                <span className={styles.priceCycle}>/mo</span>
              </div>
              <span className={styles.priceSub}>billed {billingCycle}</span>
            </div>
            <ul className={styles.priceFeatures}>
              <li><Check size={14} /> Unlimited meetings & recordings</li>
              <li><Check size={14} /> Full audio/video processing</li>
              <li><Check size={14} /> Jira, Linear & Slack Sync integrations</li>
              <li><Check size={14} /> Conversational RAG Copilot Q&A</li>
              <li><Check size={14} /> Speaker coaching & metrics</li>
              <li><Check size={14} /> Infinite archive storage</li>
            </ul>
            <button className={clsx(styles.pricingBtn, styles.proPricingBtn)} onClick={() => navigate(isAuthenticated ? "/dashboard" : "/login")}>
              {isAuthenticated ? "Go to Dashboard" : "Start 14-Day Free Trial"}
            </button>
          </div>

          <div className={styles.pricingCard}>
            <div className={styles.priceHeader}>
              <h3>Enterprise</h3>
              <p>For security-focused organizations.</p>
              <div className={styles.priceNum}>
                ${getEnterprisePrice()}
                <span className={styles.priceCycle}>/mo</span>
              </div>
              <span className={styles.priceSub}>per user, billed {billingCycle}</span>
            </div>
            <ul className={styles.priceFeatures}>
              <li><Check size={14} /> Custom API & webhook integrations</li>
              <li><Check size={14} /> SOC2 compliance reports & logs</li>
              <li><Check size={14} /> Dedicated custom domain hosting</li>
              <li><Check size={14} /> Private vector tenant configurations</li>
              <li><Check size={14} /> Dedicated support architect</li>
            </ul>
            <button className={styles.pricingBtn} onClick={() => navigate(isAuthenticated ? "/dashboard" : "/login")}>
              {isAuthenticated ? "Go to Dashboard" : "Contact Sales"}
            </button>
          </div>
        </div>
      </section>

      {/* FAQ Section */}
      <section id="faq" className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2>Frequently Asked Questions</h2>
          <p>Got questions? We have answers.</p>
        </div>

        <div className={styles.faqList}>
          {[
            {
              q: "How does the calendar bot join my meetings?",
              a: "Once you connect your calendar via OAuth, Zapper scans the titles and descriptions of your events. If it finds a link from Zoom, Microsoft Teams, or Google Meet, a silent bot named 'Zapper Assistant' joins at the scheduled time to capture audio and any shared screen content."
            },
            {
              q: "Can I customize the generated AI summaries?",
              a: "Absolutely. Zapper provides template styles: Executive (brief high-level overview), Technical (contains code links, structural changes, database designs), and Sales (focuses on client needs, objection checklists, follow-up dates). You can toggle these dynamically from the Meeting Detail view."
            },
            {
              q: "Is my meeting data private and secure?",
              a: "Security is our highest priority. All recorded video and audio streams are encrypted end-to-end both in transit and at rest. We never sell your data or train external foundational models on your discussions. You also have the option to configure strict auto-deletion parameters in Settings."
            },
            {
              q: "Does Zapper support languages other than English?",
              a: "Yes. Zapper uses advanced multi-language recognition models that support over 40 languages, automatically identifying speakers' dialects and writing translation highlights alongside the original transcripts."
            }
          ].map((faq, index) => (
            <div key={index} className={styles.faqItem} onClick={() => setActiveFaq(activeFaq === index ? null : index)}>
              <div className={styles.faqQuestion}>
                <span>{faq.q}</span>
                <span className={styles.faqToggleSymbol}>{activeFaq === index ? "−" : "+"}</span>
              </div>
              <div className={clsx(styles.faqAnswer, activeFaq === index && styles.faqAnswerVisible)}>
                <p>{faq.a}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* CTA Footer banner */}
      <section className={styles.ctaBanner}>
        <div className={styles.ctaGlow} />
        <h2>Ready to Put Your Meetings on Autopilot?</h2>
        <p>Join thousands of product managers, developers, and sales leads using Zapper.</p>
        <button className={styles.btnHeroPrimary} onClick={() => navigate(isAuthenticated ? "/dashboard" : "/login")} style={{ margin: "24px auto 0" }}>
          {isAuthenticated ? "Go to Dashboard" : "Get Started in 60 Seconds"} <ArrowRight size={16} />
        </button>
      </section>

      {/* Footer */}
      <footer className={styles.footer}>
        <div className={styles.footerTop}>
          <div className={styles.footerColBrand}>
            <div className={styles.logo}>
              <Zap size={20} className={styles.logoIcon} />
              <span>Zapper</span>
            </div>
            <p>Capturing organization memory and syncing tasks so your team can focus on execution.</p>
          </div>
          <div className={styles.footerCol}>
            <h4>Product</h4>
            <button onClick={() => scrollToSection("features")}>Features</button>
            <button onClick={() => scrollToSection("sandbox")}>AI Sandbox</button>
            <button onClick={() => scrollToSection("pricing")}>Pricing</button>
          </div>
          <div className={styles.footerCol}>
            <h4>Resources</h4>
            <button onClick={() => scrollToSection("faq")}>FAQ</button>
            <button onClick={() => navigate("/")}>Privacy Policy</button>
            <button onClick={() => navigate("/")}>Terms of Service</button>
          </div>
          <div className={styles.footerCol}>
            <h4>Compare</h4>
            <button onClick={() => scrollToSection("compare")}>vs Otter.ai</button>
            <button onClick={() => scrollToSection("compare")}>vs Read.ai</button>
            <button onClick={() => scrollToSection("compare")}>vs Fireflies.ai</button>
          </div>
        </div>
        <div className={styles.footerBottom}>
          <p>© 2026 Zapper Inc. All rights reserved. Built with pride for modern builders.</p>
        </div>
      </footer>
    </div>
  );
};

export default Landing;
