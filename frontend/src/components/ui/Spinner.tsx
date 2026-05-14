interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  color?: string;
}

const sizes = {
  sm: 'w-4 h-4 border-2',
  md: 'w-6 h-6 border-2',
  lg: 'w-10 h-10 border-3',
};

export default function Spinner({ size = 'md', color = 'border-primary' }: SpinnerProps) {
  return (
    <div
      className={`${sizes[size]} ${color} border-t-transparent rounded-full animate-spin`}
    />
  );
}
