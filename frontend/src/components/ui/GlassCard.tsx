import { motion } from 'framer-motion';
import { type ReactNode } from 'react';

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
  onClick?: () => void;
  animate?: boolean;
}

export default function GlassCard({
  children,
  className = '',
  hover = false,
  onClick,
  animate = false,
}: GlassCardProps) {
  const hoverClass = hover || onClick ? 'cursor-pointer glass-hover' : '';

  const inner = (
    <div
      onClick={onClick}
      className={`card ${hoverClass} ${className}`}
    >
      {children}
    </div>
  );

  if (animate) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.38, ease: 'easeOut' }}
      >
        {inner}
      </motion.div>
    );
  }

  return inner;
}
