export default function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div className={`glass rounded-xl border border-white/8 overflow-hidden ${className}`}>
      <div className="p-6 space-y-4">
        <div className="shimmer h-4 rounded-lg w-2/3" />
        <div className="shimmer h-8 rounded-lg w-1/2" />
        <div className="shimmer h-3 rounded-lg w-full" />
        <div className="shimmer h-3 rounded-lg w-4/5" />
      </div>
    </div>
  );
}

export function SkeletonLine({ width = 'w-full', height = 'h-4' }: { width?: string; height?: string }) {
  return <div className={`shimmer ${height} ${width} rounded-lg`} />;
}
