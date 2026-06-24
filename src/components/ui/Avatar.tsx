import React, { useState } from "react";
import styles from "./Avatar.module.css";
import clsx from "clsx";

interface AvatarProps {
  src?: string;
  name: string;
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  presence?: "online" | "offline" | "busy" | "none";
  className?: string;
}

const getInitials = (name: string): string => {
  const parts = name.trim().split(" ");
  if (parts.length === 0 || !parts[0]) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
};

const getAvatarColor = (name: string): string => {
  const colors = [
    "#ef4444", // red
    "#f59e0b", // amber
    "#10b981", // emerald
    "#3b82f6", // blue
    "#6366f1", // indigo
    "#8b5cf6", // purple
    "#ec4899", // pink
    "#14b8a6", // teal
  ];
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const index = Math.abs(hash) % colors.length;
  return colors[index];
};

export const Avatar: React.FC<AvatarProps> = ({
  src,
  name,
  size = "md",
  presence = "none",
  className,
}) => {
  const [imgError, setImgError] = useState(false);
  const initials = getInitials(name);
  const bgColor = getAvatarColor(name);

  return (
    <div className={clsx(styles.avatarContainer, styles[size], className)}>
      {src && !imgError ? (
        <img
          src={src}
          alt={name}
          className={styles.avatarImage}
          onError={() => setImgError(true)}
        />
      ) : (
        <div
          className={styles.avatarFallback}
          style={{ backgroundColor: bgColor }}
        >
          {initials}
        </div>
      )}
      {presence !== "none" && (
        <span className={clsx(styles.presenceIndicator, styles[presence])} />
      )}
    </div>
  );
};
