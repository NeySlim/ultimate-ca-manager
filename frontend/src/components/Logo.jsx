/**
 * UCM Logo Component
 * Certificate Chain logo with gradient
 */

export function Logo({ className = "", size = "md" }) {
  const sizes = {
    sm: "h-6",
    md: "h-8",
    lg: "h-12",
    xl: "h-16"
  };

  return (
    <svg 
      viewBox="0 0 200 60" 
      className={`${sizes[size]} ${className}`}
      fill="none" 
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Gradient definitions */}
      <defs>
        <linearGradient id="logoGradient" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" style={{ stopColor: '#8B7355', stopOpacity: 1 }} />
          <stop offset="100%" style={{ stopColor: '#A0826D', stopOpacity: 1 }} />
        </linearGradient>
      </defs>
      
      {/* Chain links */}
      <g stroke="url(#logoGradient)" strokeWidth="2.5" fill="none">
        {/* Link 1 */}
        <ellipse cx="20" cy="30" rx="12" ry="16" transform="rotate(-20 20 30)" />
        {/* Link 2 */}
        <ellipse cx="45" cy="30" rx="12" ry="16" transform="rotate(20 45 30)" />
        {/* Link 3 */}
        <ellipse cx="70" cy="30" rx="12" ry="16" transform="rotate(-20 70 30)" />
      </g>
      
      {/* Text */}
      <text 
        x="90" 
        y="40" 
        fontFamily="Inter, system-ui, sans-serif" 
        fontSize="24" 
        fontWeight="600" 
        fill="url(#logoGradient)"
      >
        Certificate Chain
      </text>
    </svg>
  );
}
