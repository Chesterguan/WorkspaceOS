'use client';

// Renders a persona avatar with deterministic initials fallback.
//
// When a persona's `avatar` field is empty (the case for framework-generated
// personas from the onboarding wizard), we draw an SVG circle filled with the
// persona's accent color and overlay 1–2 letters of initials. No external
// fetch, no `next/image` domain whitelist, no flash of nothing.
//
// When `avatar` is a path or URL, we render it as a plain <img> for the
// same reasons — and so deployments behind tunnels / different ports don't
// trip the Next.js `Image` host allowlist. Slight CLS in exchange for
// zero setup cost; acceptable for ~32px chat avatars.

import { useMemo } from 'react';

interface Props {
  name: string;
  color: string;
  avatar?: string;
  size?: number;
  className?: string;
}

export function PersonaAvatar({
  name,
  color,
  avatar,
  size = 32,
  className = '',
}: Props) {
  const initials = useMemo(() => deriveInitials(name), [name]);

  if (avatar && avatar.length > 0) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={avatar}
        alt={name}
        width={size}
        height={size}
        style={{ width: size, height: size }}
        className={`rounded-full object-cover ${className}`}
      />
    );
  }

  // SVG initials fallback. Color the disc with the persona's accent at
  // ~20% opacity, draw the initials in the same accent at full opacity
  // — matches the visual language of the rail / surface chips.
  return (
    <svg
      role="img"
      aria-label={name}
      width={size}
      height={size}
      viewBox="0 0 40 40"
      className={`rounded-full ${className}`}
      style={{ width: size, height: size }}
    >
      <circle cx="20" cy="20" r="20" fill={color} fillOpacity="0.18" />
      <circle
        cx="20" cy="20" r="19"
        fill="none"
        stroke={color}
        strokeOpacity="0.55"
        strokeWidth="1.2"
      />
      <text
        x="20" y="20"
        textAnchor="middle"
        dominantBaseline="central"
        fontSize="14"
        fontWeight="600"
        fontFamily="ui-sans-serif, system-ui, -apple-system, sans-serif"
        fill={color}
      >
        {initials}
      </text>
    </svg>
  );
}

function deriveInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0][0]?.toUpperCase() ?? '?';
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
