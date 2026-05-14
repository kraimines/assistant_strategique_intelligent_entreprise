import { motion } from 'framer-motion';
import { type ReactNode } from 'react';
import Spinner from './Spinner';

interface ButtonProps {
  children: ReactNode;
  onClick?: () => void;
  type?: 'button' | 'submit' | 'reset';
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  disabled?: boolean;
  className?: string;
  icon?: ReactNode;
  fullWidth?: boolean;
}

/* ── Variant styles ─────────────────────────────────────────────────────── */
const variantStyles: Record<string, React.CSSProperties> = {};  // handled inline for theme vars

const variantClasses: Record<string, string> = {
  primary: `
    text-white font-semibold
    disabled:opacity-50 disabled:cursor-not-allowed
  `,
  secondary: `
    font-medium
    disabled:opacity-50 disabled:cursor-not-allowed
  `,
  ghost: `
    font-medium
    disabled:opacity-50 disabled:cursor-not-allowed
  `,
  danger: `
    font-medium
    disabled:opacity-50 disabled:cursor-not-allowed
  `,
};

const sizes: Record<string, string> = {
  sm: 'px-3 py-1.5 text-xs rounded-lg gap-1.5',
  md: 'px-4 py-2.5 text-sm rounded-[10px] gap-2',
  lg: 'px-6 py-3 text-sm rounded-xl gap-2',
};

function getInlineStyle(variant: string, disabled: boolean): React.CSSProperties {
  if (disabled) return { opacity: 0.5, cursor: 'not-allowed' };
  switch (variant) {
    case 'primary':
      return {
        background: 'linear-gradient(135deg, #3B82F6, #2563EB)',
        boxShadow: '0 2px 8px rgba(37,99,235,0.25)',
      };
    case 'secondary':
      return {
        background: 'var(--primary-subtle)',
        border: '1px solid var(--primary-muted)',
        color: 'var(--primary-dark)',
      };
    case 'ghost':
      return {
        background: 'transparent',
        color: 'var(--text-secondary)',
      };
    case 'danger':
      return {
        background: 'var(--danger-subtle)',
        border: '1px solid rgba(239,68,68,0.3)',
        color: 'var(--danger)',
      };
    default:
      return {};
  }
}

export default function Button({
  children,
  onClick,
  type = 'button',
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  className = '',
  icon,
  fullWidth = false,
}: ButtonProps) {
  return (
    <motion.button
      whileTap={{ scale: disabled || loading ? 1 : 0.97 }}
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      className={`
        inline-flex items-center justify-center transition-all duration-200
        ${variantClasses[variant]}
        ${sizes[size]}
        ${fullWidth ? 'w-full' : ''}
        ${className}
      `}
      style={getInlineStyle(variant, disabled || loading)}
    >
      {loading ? <Spinner size="sm" /> : icon}
      {children}
    </motion.button>
  );
}
