import React, { useState, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { chatApi, streamChat } from "../services/chat";
import { PageHeader } from "../components/layout/PageHeader";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Avatar } from "../components/ui/Avatar";
import { Badge } from "../components/ui/Badge";
import {
  MessageSquare,
  Plus,
  Send,
  RefreshCw,
  Calendar,
  Tag,
  Shield,
  ExternalLink,
  Search,
  ChevronDown,
  Sparkles,
  PlayCircle,
  HelpCircle,
  FileText
} from "lucide-react";
import styles from "./AIChat.module.css";
import clsx from "clsx";

const formatTimeMs = (ms: number) => {
  const mins = Math.floor(ms / 60000);
  const secs = Math.floor((ms % 60000) / 1000);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
};

export const AIChat: React.FC = () => {
  const queryClient = useQueryClient();
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);

  const { data: dbSessions = [] } = useQuery({
    queryKey: ["chat-sessions"],
    queryFn: chatApi.listSessions,
  });

  const { data: sessionData } = useQuery({
    queryKey: ["chat-session-messages", activeConversationId],
    queryFn: () => chatApi.getSession(activeConversationId!),
    enabled: !!activeConversationId,
  });

  const conversations = dbSessions.map((s: any) => ({
    id: s.id,
    title: s.title || "New Chat Session",
    createdAt: s.created_at || new Date().toISOString(),
  }));

  const dbMessages = sessionData?.messages || [];
  const [streamingContent, setStreamingContent] = useState<string | null>(null);

  const activeConversation = activeConversationId
    ? {
        id: activeConversationId,
        title: conversations.find((c) => c.id === activeConversationId)?.title || "Chat Session",
        messages: dbMessages.map((msg: any) => ({
          id: msg.id,
          role: msg.role,
          content: msg.content,
          timestamp: msg.created_at || new Date().toISOString(),
          citations: (msg.citations || []).map((c: any) => ({
            meetingTitle: c.meeting_title || "Meeting Source",
            timestamp: c.start_ms ? formatTimeMs(c.start_ms) : "00:00",
            snippet: c.text || c.snippet,
            speaker: c.speaker_name || c.speaker || "Speaker",
          })),
          suggestedQuestions: (msg as any).suggested_questions || undefined,
        })),
      }
    : null;

  if (activeConversation && streamingContent !== null) {
    activeConversation.messages.push({
      id: "msg_streaming",
      role: "assistant",
      content: streamingContent,
      timestamp: new Date().toISOString(),
      citations: [],
      suggestedQuestions: [],
    });
  }

  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [model, setModel] = useState("gpt-4o");
  const [historySearch, setHistorySearch] = useState("");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll chats
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeConversation?.messages, isTyping]);

  // Adjust textarea height on input change
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "40px";
      textareaRef.current.style.height = `${Math.min(140, textareaRef.current.scrollHeight)}px`;
    }
  }, [input]);

  const handleSendMessage = (textToSend: string) => {
    if (!textToSend.trim()) return;

    setIsTyping(true);
    setStreamingContent("");
    setInput("");

    // Setup temporary message or fetch stream
    streamChat({
      message: textToSend,
      sessionId: activeConversationId || undefined,
      onChunk: (chunk) => {
        setStreamingContent((prev) => (prev || "") + chunk);
      },
      onDone: (finalMessage, finalSessionId) => {
        setStreamingContent(null);
        setIsTyping(false);
        if (!activeConversationId && finalSessionId) {
          setActiveConversationId(finalSessionId);
        }
        queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
        queryClient.invalidateQueries({ queryKey: ["chat-session-messages", finalSessionId] });
      },
      onError: (err) => {
        setStreamingContent(null);
        setIsTyping(false);
        console.error("[chat] Stream error:", err);
      }
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage(input);
    }
  };

  const handleNewChat = () => {
    setActiveConversationId(null);
  };

  // Group threads by date categories
  const getGroupedConversations = () => {
    const today: typeof conversations = [];
    const yesterday: typeof conversations = [];
    const older: typeof conversations = [];

    const now = new Date();
    const searchFiltered = conversations.filter(c => 
      c.title.toLowerCase().includes(historySearch.toLowerCase())
    );

    searchFiltered.forEach((c) => {
      const diffTime = Math.abs(now.getTime() - new Date(c.createdAt).getTime());
      const diffDays = diffTime / (1000 * 60 * 60 * 24);
      if (diffDays < 1) {
        today.push(c);
      } else if (diffDays < 2) {
        yesterday.push(c);
      } else {
        older.push(c);
      }
    });

    return { today, yesterday, older };
  };

  const { today, yesterday, older } = getGroupedConversations();

  // Helper to render inlined bold formatting
  const renderInlineText = (text: string) => {
    const boldRegex = /\*\*(.*?)\*\*/g;
    const parts = text.split(boldRegex);
    return parts.map((part, index) => {
      return index % 2 === 1 ? <strong key={index}>{part}</strong> : part;
    });
  };

  // Enhanced parser for lists and paragraphs
  const renderMessageContent = (content: string) => {
    const paragraphs = content.split("\n\n");
    return paragraphs.map((para, pIdx) => {
      if (para.trim().match(/^\d+\.\s/)) {
        const items = para.split("\n");
        return (
          <ol key={pIdx} className={styles.orderedList}>
            {items.map((item, iIdx) => {
              const cleanItem = item.replace(/^\d+\.\s/, "");
              return <li key={iIdx}>{renderInlineText(cleanItem)}</li>;
            })}
          </ol>
        );
      }
      
      const lines = para.split("\n");
      return (
        <p key={pIdx}>
          {lines.map((line, lIdx) => (
            <React.Fragment key={lIdx}>
              {lIdx > 0 && <br />}
              {renderInlineText(line)}
            </React.Fragment>
          ))}
        </p>
      );
    });
  };

  return (
    <div className={styles.container}>
      <PageHeader
        breadcrumbs={["AI Assistant", "Zapper AI Chat"]}
        actions={
          <div className={styles.headerActions}>
            <select
              className={styles.modelSelect}
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              <option value="gpt-4o">🤖 Zapper AI (GPT-4o)</option>
              <option value="gpt-35">⚡ Quick Mode (GPT-3.5)</option>
              <option value="research">🔬 Deep Research Mode</option>
            </select>
          </div>
        }
      />

      <div className={styles.wrapper}>
        {/* Sidebar History Panel */}
        <aside className={styles.historyPanel}>
          <div className={styles.sidebarSearch}>
            <Search size={14} className={styles.searchIcon} />
            <input
              type="text"
              placeholder="Search chat history..."
              value={historySearch}
              onChange={(e) => setHistorySearch(e.target.value)}
              className={styles.searchField}
            />
          </div>

          <Button
            variant="outline"
            className={styles.newChatBtn}
            icon={<Plus size={14} />}
            onClick={handleNewChat}
          >
            New Thread
          </Button>

          <div className={styles.scrollableHistory}>
            {today.length > 0 && (
              <div className={styles.historyGroup}>
                <span className={styles.groupLabel}>Today</span>
                {today.map((c) => renderHistoryItem(c))}
              </div>
            )}

            {yesterday.length > 0 && (
              <div className={styles.historyGroup}>
                <span className={styles.groupLabel}>Yesterday</span>
                {yesterday.map((c) => renderHistoryItem(c))}
              </div>
            )}

            {older.length > 0 && (
              <div className={styles.historyGroup}>
                <span className={styles.groupLabel}>Previous Threads</span>
                {older.map((c) => renderHistoryItem(c))}
              </div>
            )}
          </div>
        </aside>

        {/* Conversation Thread */}
        <main className={styles.chatThread}>
          <div className={styles.messagesList}>
            {activeConversation && activeConversation.messages.length > 0 ? (
              activeConversation.messages.map((msg) => (
                <div
                  key={msg.id}
                  className={clsx(
                    styles.messageRow,
                    msg.role === "user" ? styles.userRow : styles.assistantRow
                  )}
                >
                  {msg.role === "assistant" && (
                    <div className={styles.assistantAvatar}>
                      <span className={styles.botAvatarGlow} />
                      <Sparkles size={14} />
                    </div>
                  )}
                  
                  <div className={`${styles.messageCard} glass-card`}>
                    <div className={styles.messageHeader}>
                      <span className={styles.senderName}>
                        {msg.role === "user" ? "You" : "Zapper AI"}
                      </span>
                      <span className={styles.messageTime}>
                        {new Date(msg.timestamp).toLocaleTimeString(undefined, {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>
                    
                    <div className={styles.messageContent}>
                      {renderMessageContent(msg.content)}
                    </div>

                    {/* Citations Card */}
                    {msg.citations && msg.citations.length > 0 && (
                      <div className={styles.citations}>
                        <span className={styles.citationLabel}>Referenced Syncs:</span>
                        <div className={styles.citationsGrid}>
                          {msg.citations.map((cite: any, index: number) => (
                            <div key={index} className={styles.citationCard}>
                              <div className={styles.citationCardHeader}>
                                <div className={styles.citeLeft}>
                                  <Badge className="badge-indigo">Zoom</Badge>
                                  <span className={styles.citeMeetingTitle}>{cite.meetingTitle}</span>
                                </div>
                                <span className={styles.citeTime}>{cite.timestamp}</span>
                              </div>
                              <p className={styles.citeSnippet}>"{cite.snippet}"</p>
                              <div className={styles.citeFooter}>
                                <Avatar name={cite.speaker} size="xs" />
                                <span>{cite.speaker}</span>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Suggested follow ups */}
                    {msg.suggestedQuestions && msg.suggestedQuestions.length > 0 && (
                      <div className={styles.suggestedQuestions}>
                        {msg.suggestedQuestions.map((q: any, index: number) => (
                          <button
                            key={index}
                            className={styles.suggestedBtn}
                            onClick={() => handleSendMessage(q)}
                          >
                            {q}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))
            ) : (
              /* Premium Empty State */
              <div className={`${styles.emptyChatHero} animate-fade-in`}>
                <div className={styles.aiLogoContainer}>
                  <div className={styles.aiLogoRing} />
                  <Sparkles size={32} className={styles.logoIcon} />
                </div>
                <h2>What can Zapper compile for you today?</h2>
                <p>Query details, meeting choices, task assignees, or design specs from any call.</p>
                
                <div className={styles.introSuggestions}>
                  <button
                    className={`${styles.introBtn} glass-card`}
                    onClick={() => handleSendMessage("What decisions were made about Azure?")}
                  >
                    <HelpCircle size={14} className={styles.introIcon} />
                    <span>What decisions were made about Azure?</span>
                  </button>
                  <button
                    className={`${styles.introBtn} glass-card`}
                    onClick={() => handleSendMessage("Show Faster-Whisper benchmark results?")}
                  >
                    <FileText size={14} className={styles.introIcon} />
                    <span>Show Faster-Whisper benchmark results?</span>
                  </button>
                  <button
                    className={`${styles.introBtn} glass-card`}
                    onClick={() => handleSendMessage("Why are we using Redis Streams?")}
                  >
                    <PlayCircle size={14} className={styles.introIcon} />
                    <span>Why are we using Redis Streams?</span>
                  </button>
                </div>
              </div>
            )}

            {isTyping && (
              <div className={styles.messageRow}>
                <div className={styles.assistantAvatar}>
                  <span className={styles.botAvatarGlow} />
                  <Sparkles size={14} />
                </div>
                <div className={`${styles.typingBubble} glass-card`}>
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Form input with auto-growing textarea */}
          <form onSubmit={(e) => { e.preventDefault(); handleSendMessage(input); }} className={styles.inputArea}>
            <div className={styles.inputContainer}>
              <textarea
                ref={textareaRef}
                placeholder="Ask Zapper Copilot (e.g., '@Rahul, decisions made regarding Azure #benchmarks')"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                className={styles.textarea}
                rows={1}
              />
              <button type="submit" className={styles.sendButton} disabled={!input.trim()}>
                <Send size={16} />
              </button>
            </div>
            <div className={styles.inputHelp}>
              <span>Press Enter to send, Shift+Enter for new line. Use @ to tag people, # for keywords.</span>
            </div>
          </form>
        </main>
      </div>
    </div>
  );

  function renderHistoryItem(conv: any) {
    return (
      <div
        key={conv.id}
        className={clsx(
          styles.chatItem,
          conv.id === activeConversationId && styles.activeChatItem
        )}
        onClick={() => setActiveConversationId(conv.id)}
      >
        <MessageSquare size={14} className={styles.chatIcon} />
        <span className={styles.chatTitle}>{conv.title}</span>
      </div>
    );
  }
};

export default AIChat;
