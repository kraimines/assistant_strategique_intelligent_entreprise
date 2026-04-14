import { motion } from 'framer-motion';
import { type ReactNode } from 'react';

interface GlassCardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
  glow?: 'cyan' | 'violet' | 'emerald' | 'amber' | 'pink';
  onClick?: () => void;
  animate?: boolean;
}

const glowColors = {
  cyan: 'hover:shadow-[0_0_20px_rgba(0,212,255,0.3)] hover:border-cyber-cyan/40',
  violet: 'hover:shadow-[0_0_20px_rgba(124,58,237,0.3)] hover:border-cyber-violet/40',
  emerald: 'hover:shadow-[0_0_20px_rgba(16,185,129,0.3)] hover:border-cyber-emerald/40',
  amber: 'hover:shadow-[0_0_20px_rgba(245,158,11,0.3)] hover:border-cyber-amber/40',
  pink: 'hover:shadow-[0_0_20px_rgba(236,72,153,0.3)] hover:border-cyber-pink/40',
};

export default function GlassCard({
  children,
  className = '',
  hover = false,
  glow,
  onClick,
  animate = false,
}: GlassCardProps) {
  const glowClass = glow ? glowColors[glow] : '';
  const hoverClass = hover ? 'transition-all duration-300 cursor-pointer' : '';

  const content = (
    <div
      onClick={onClick}
      className={`glass rounded-xl ${hoverClass} ${glowClass} ${className}`}
      style={{ border: '1px solid var(--border-subtle)' }}
    >
      {children}
    </div>
  );

  if (animate) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: 'easeOut' }}
      >
        {content}
      </motion.div>
    );
  }

  return content;
}
