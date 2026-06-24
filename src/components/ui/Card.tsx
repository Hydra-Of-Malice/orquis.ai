import React from "react";
import styles from "./Card.module.css";
import clsx from "clsx";

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "glass" | "outline";
  interactive?: boolean;
}

export const Card: React.FC<CardProps> = ({
  children,
  className,
  variant = "default",
  interactive = false,
  ...props
}) => {
  return (
    <div
      className={clsx(
        styles.card,
        styles[variant],
        interactive && styles.interactive,
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
};
