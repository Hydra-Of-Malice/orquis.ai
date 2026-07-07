import React, { useState } from "react";
import { Modal } from "../ui/Modal";
import { Input } from "../ui/Input";
import { Button } from "../ui/Button";
import { Loader2 } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { meetingsApi } from "../../services/meetings";
import { useNavigate } from "react-router-dom";
import styles from "./JoinMeetingModal.module.css";

interface JoinMeetingModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const JoinMeetingModal: React.FC<JoinMeetingModalProps> = ({ isOpen, onClose }) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [meetingTitleInput, setMeetingTitleInput] = useState("");
  const [meetingUrlInput, setMeetingUrlInput] = useState("");
  const [botError, setBotError] = useState("");

  const startBotMutation = useMutation({
    mutationFn: meetingsApi.startBot,
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ["meetings"] });
      onClose();
      setMeetingTitleInput("");
      setMeetingUrlInput("");
      navigate(`/live/${response.meeting_id}`);
    },
    onError: (err: any) => {
      setBotError(err?.response?.data?.detail || "Failed to start bot");
    },
  });

  const handleJoinSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setBotError("");
    if (!meetingUrlInput) {
      setBotError("Meeting URL is required");
      return;
    }
    startBotMutation.mutate({
      meeting_url: meetingUrlInput,
      title: meetingTitleInput || undefined,
    });
  };

  const handleClose = () => {
    onClose();
    setBotError("");
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Join Meeting & Call Bot">
      <form onSubmit={handleJoinSubmit} className={styles.modalForm}>
        <div className={styles.formGroup}>
          <label>
            Meeting Title <span style={{ color: "var(--text-tertiary)", fontWeight: 400 }}>(optional)</span>
          </label>
          <Input
            placeholder="e.g. Q3 Design Review"
            value={meetingTitleInput}
            onChange={(e) => setMeetingTitleInput(e.target.value)}
          />
        </div>
        <div className={styles.formGroup}>
          <label>
            Meeting URL <span style={{ color: "var(--rose)", fontSize: "0.75rem" }}>*</span>
          </label>
          <Input
            required
            placeholder="https://meet.google.com/xxx-yyyy-zzz"
            value={meetingUrlInput}
            onChange={(e) => {
              setMeetingUrlInput(e.target.value);
              setBotError("");
            }}
          />
          <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginTop: "0.25rem", display: "block" }}>
            Supports Google Meet and Microsoft Teams
          </span>
        </div>
        {botError && (
          <div style={{ color: "var(--rose)", fontSize: "0.8125rem", marginBottom: "0.5rem" }}>{botError}</div>
        )}
        <div className={styles.modalActions}>
          <Button variant="outline" type="button" onClick={handleClose} disabled={startBotMutation.isPending}>
            Cancel
          </Button>
          <Button
            variant="primary"
            type="submit"
            disabled={startBotMutation.isPending}
            icon={startBotMutation.isPending ? <Loader2 size={14} className="spin" /> : undefined}
          >
            {startBotMutation.isPending ? "Calling Bot..." : "Call Zapper Bot"}
          </Button>
        </div>
      </form>
    </Modal>
  );
};
