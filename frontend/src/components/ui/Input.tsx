import React from "react";
import styles from "./Input.module.css";
import clsx from "clsx";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  icon?: React.ReactNode;
  suffix?: React.ReactNode;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, icon, suffix, ...props }, ref) => {
    return (
      <div className={styles.container}>
        {icon && <span className={styles.icon}>{icon}</span>}
        <input
          ref={ref}
          className={clsx(
            styles.input,
            icon && styles.hasIcon,
            suffix && styles.hasSuffix,
            className
          )}
          {...props}
        />
        {suffix && <span className={styles.suffix}>{suffix}</span>}
      </div>
    );
  }
);

Input.displayName = "Input";
