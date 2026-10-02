/**
 * @globaltalk/ui — cross-app design-system primitives.
 * The web app's full component set lives in apps/web/src/components/ui.tsx and
 * consumes these tokens/helpers; this package keeps identity constants shared
 * (future mobile app reuses them without importing the web app).
 */
export const tokens = {
  colors: {
    iris: { 500: '#6d5fe6', 600: '#5b43d6', 700: '#4d35bd' },
    lagoon: { 400: '#1ddfcc', 500: '#06c3b3', 600: '#029e94' },
  },
  radius: { card: '1rem', control: '0.875rem' },
  fontStack: "Inter, system-ui, -apple-system, 'Segoe UI', Roboto, 'Noto Sans', 'Noto Sans Devanagari', sans-serif",
} as const;

export const AUDIO_MODES = ['original', 'translated', 'mixed', 'captions_only'] as const;
export type AudioMode = (typeof AUDIO_MODES)[number];

export const QUALITY_STATUSES = ['EXPERIMENTAL', 'BETA', 'SUPPORTED', 'PRODUCTION'] as const;
export type QualityStatus = (typeof QUALITY_STATUSES)[number];
