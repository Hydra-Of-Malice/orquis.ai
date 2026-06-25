import React from "react";
import clsx from "clsx";

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  children: React.ReactNode;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({ children, className, ...props }) => {
  return (
    <span className={clsx("badge", className)} {...props}>
      {children}
    </span>
  );
};

export default Badge;
