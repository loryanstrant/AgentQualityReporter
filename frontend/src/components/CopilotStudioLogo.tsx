import { useEffect, useState } from "react";

/**
 * Product mark for the app header and login screen.
 *
 * By default this renders an original, gradient "ribbon" mark (our own artwork,
 * not Microsoft's proprietary logo file). If you have the rights to use the
 * official Copilot Studio logo, drop an SVG/PNG at `public/copilot-studio.svg`
 * and it will be used automatically instead of the built-in mark.
 */
export default function CopilotStudioLogo({
  size = 28,
  className = "",
}: {
  size?: number;
  className?: string;
}) {
  const [customOk, setCustomOk] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    const img = new Image();
    img.onload = () => alive && setCustomOk(true);
    img.onerror = () => alive && setCustomOk(false);
    img.src = "/copilot-studio.svg";
    return () => {
      alive = false;
    };
  }, []);

  if (customOk) {
    return (
      <img
        src="/copilot-studio.svg"
        alt="Copilot Studio"
        width={size}
        height={size}
        className={className}
        style={{ display: "block" }}
      />
    );
  }

  // Built-in original mark: a gradient rounded-square badge with a stylised swoosh.
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label="Copilot Studio"
      className={className}
      style={{ display: "block" }}
    >
      <defs>
        <linearGradient id="csg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#2aa5f2" />
          <stop offset="0.5" stopColor="#2ac0b6" />
          <stop offset="1" stopColor="#7a5cff" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="30" height="30" rx="8" fill="url(#csg)" />
      <path
        d="M10.5 20.2c-1.9 0-3.2-1.5-3.2-3.4 0-2.6 1.9-4.9 4.9-4.9 2.1 0 3.3 1.1 4 2.9.6 1.6 1.2 2.3 2.2 2.3 1.1 0 1.8-.9 1.8-2 0-1.5-1.1-2.8-3-2.8-.7 0-1.3.1-1.9.4.5-1.7 2.1-3 4.2-3 2.7 0 4.6 2 4.6 4.7 0 2.8-2 4.8-4.7 4.8-2.2 0-3.4-1.1-4.1-2.9-.6-1.6-1.1-2.3-2.1-2.3-1 0-1.7.8-1.7 1.9 0 1.4 1 2.6 2.8 2.6.6 0 1.2-.1 1.7-.3-.5 1.6-2 2.7-3.5 2.7z"
        fill="#ffffff"
        opacity="0.95"
      />
    </svg>
  );
}
