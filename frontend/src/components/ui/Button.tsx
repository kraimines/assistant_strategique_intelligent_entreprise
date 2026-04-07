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

const variants = {
  primary: `
    bg-gradient-to-r from-cyber-cyan to-cyber-violet text-white
    hover:shadow-[0_0_20px_rgba(0,212,255,0.4)]
    disabled:opacity-50 disabled:cursor-not-allowed
  `,
  secondary: `
    glass border border-cyber-cyan/30 text-cyber-cyan
    hover:border-cyber-cyan/70 hover:shadow-[0_0_15px_rgba(0,212,255,0.2)]
    disabled:opacity-50 disabled:cursor-not-allowed
  `,
  ghost: `
    text-white/70 hover:text-white hover:bg-white/8
    disabled:opacity-50 disabled:cursor-not-allowed
  `,
  danger: `
    bg-red-500/20 border border-red-500/40 text-red-400
    hover:bg-red-500/30 hover:border-red-500/60
    disabled:opacity-50 disabled:cursor-not-allowed
  `,
};

const sizes = {
  sm: 'px-3 py-1.5 text-sm rounded-lg',
  md: 'px-5 py-2.5 text-sm rounded-xl',
  lg: 'px-7 py-3.5 text-base rounded-xl',
};

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
      whileTap={{ scale: 0.97 }}
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      className={`
        inline-flex items-center justify-center gap-2 font-medium
        transition-all duration-200
        ${variants[variant]}
        ${sizes[size]}
        ${fullWidth ? 'w-full' : ''}
        ${className}
      `}
    >
      {loading ? <Spinner size="sm" /> : icon}
      {children}
    </motion.button>
  );
}
