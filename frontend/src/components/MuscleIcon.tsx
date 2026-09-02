import type { CSSProperties, ReactElement } from "react";

const PATHS: Record<string, ReactElement> = {
  Chest: (
    <>
      <path d="M24 14c-3-4-9-5-12-1-2.7 3.4-2 8.6 1.5 13 3 3.7 7.4 6.3 10.5 8 3.1-1.7 7.5-4.3 10.5-8 3.5-4.4 4.2-9.6 1.5-13-3-4-9-3-12 1Z" />
      <path d="M24 14v21" />
    </>
  ),
  Back: (
    <>
      <path d="M24 8v32" />
      <path d="M24 12c-6 2-12 6-15 11l6 3c2.5-4 5.5-6.5 9-8" />
      <path d="M24 12c6 2 12 6 15 11l-6 3c-2.5-4-5.5-6.5-9-8" />
      <path d="M15 26c-1.5 4-2 8-1.5 12" />
      <path d="M33 26c1.5 4 2 8 1.5 12" />
    </>
  ),
  Shoulders: (
    <>
      <circle cx="13" cy="18" r="6" />
      <circle cx="35" cy="18" r="6" />
      <path d="M13 24c2 6 7 9 11 9s9-3 11-9" />
    </>
  ),
  Biceps: (
    <>
      <path d="M14 32c-2-8-1-16 5-21 4-3.4 9-2.6 10 2 .8 3.8-1.6 6-5 6.5" />
      <path d="M24 19.5c5-1 9 1.5 9 7 0 6-4 10-10 10.5" />
      <path d="M14 32c1.5 3.5 5 5.5 9 5" />
    </>
  ),
  Triceps: (
    <>
      <path d="M16 12c-4 3-6 9-4 15 1.6 4.8 5.5 8 10 8.5" />
      <path d="M16 12c3-2.5 7-2.5 9 .5" />
      <path d="M12 24c3 1.5 5 1.8 8 1.2" />
      <path d="M12 24c-1 3 0 6.5 2 9" />
    </>
  ),
  Legs: (
    <>
      <path d="M18 8h5v15l1 17h-4l-2-14-2 14h-4l1-19Z" />
      <path d="M25 8h5l3 13-1 19h-4l-2-16-3 12" />
      <path d="M18 23h8" />
    </>
  ),
  Abs: (
    <>
      <rect x="16" y="10" width="7" height="7" rx="1.5" />
      <rect x="25" y="10" width="7" height="7" rx="1.5" />
      <rect x="16" y="19.5" width="7" height="7" rx="1.5" />
      <rect x="25" y="19.5" width="7" height="7" rx="1.5" />
      <rect x="16" y="29" width="7" height="7" rx="1.5" />
      <rect x="25" y="29" width="7" height="7" rx="1.5" />
    </>
  ),
};

export default function MuscleIcon({
  muscle,
  className,
  style,
}: {
  muscle: string;
  className?: string;
  style?: CSSProperties;
}) {
  const path = PATHS[muscle];
  return (
    <svg
      viewBox="0 0 48 48"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={style}
    >
      {path ?? <circle cx="24" cy="24" r="10" />}
    </svg>
  );
}
