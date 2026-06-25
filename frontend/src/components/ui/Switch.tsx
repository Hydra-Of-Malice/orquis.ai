import React from "react";
import styles from "./Switch.module.css";
import clsx from "clsx";

interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  disabled?: boolean;
  className?: string;
}

export const Switch: React.FC<SwitchProps> = ({
  checked,
  onChange,
  label,
  disabled = false,
  className,
}) => {
  return (
    <label className={clsx(styles.container, disabled && styles.disabled, className)}>
      <span className={styles.switchWrapper}>
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          disabled={disabled}
          className={styles.hiddenInput}
        />
        <span className={clsx(styles.slider, checked && styles.checked)} />
      </span>
      {label && <span className={styles.label}>{label}</span>}
    </label>
  );
};
