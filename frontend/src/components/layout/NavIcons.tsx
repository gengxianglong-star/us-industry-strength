type NavIconProps = {
  className?: string;
};

/** Market breadth — three ascending bars */
export function NavIconBreadth({ className = "top-nav-item-icon" }: NavIconProps) {
  return (
    <span className={className} aria-hidden="true">
      <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="1.5" y="9" width="3" height="5.5" rx="0.75" fill="currentColor" opacity="0.45" />
        <rect x="6.5" y="5.5" width="3" height="9" rx="0.75" fill="currentColor" opacity="0.7" />
        <rect x="11.5" y="2" width="3" height="12.5" rx="0.75" fill="currentColor" />
      </svg>
    </span>
  );
}

/** Strong industry — layered rank chevrons */
export function NavIconStrong({ className = "top-nav-item-icon" }: NavIconProps) {
  return (
    <span className={className} aria-hidden="true">
      <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path
          d="M2 11.5 6.5 7 11 9.5 14 4"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M11 4h3v3"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="M2 13.5h12"
          stroke="currentColor"
          strokeWidth="1.25"
          strokeLinecap="round"
          opacity="0.35"
        />
      </svg>
    </span>
  );
}
