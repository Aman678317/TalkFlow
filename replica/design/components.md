# Component Specifications: TalkFlow Design System

Derived from recon inspection and token definitions. All components conform to WCAG 2.1 AA accessibility guidelines, full keyboard navigation, and semantic DOM elements.

---

### Button
- **variants**: `primary` (accent fill), `secondary` (surface fill, subtle border), `ghost` (transparent, hover surface), `danger` (danger fill, on-accent text)
- **sizes**:
  - `sm`: 32px height, 12px padding, font 13px/500
  - `md`: 40px height, 16px padding, font 14px/600 (default)
  - `lg`: 48px height, 20px padding, font 16px/600
- **states**: `default`, `hover`, `active`, `focus-visible` (2px offset ring, `--color-accent`), `disabled` (opacity 50%, cursor-not-allowed), `loading` (spinner replacing leading icon)
- **tokens**: `bg --color-accent`, `text --color-on-accent`, `radius --radius-md`, `motion --motion-fast`
- **a11y**: Real `<button type="button">`, visible focus indicator, loading maintains `aria-busy="true"` and accessible label for screen readers.
- **used on**: S01, S02, S04, S05, S06, S07, S08, S09, S10

---

### LanguageSelector
- **variants**: `source-mode` (includes 'Auto-detect'), `target-mode` (strict target language), `compact-pill` (icon + ISO code), `searchable-modal` (search input + 50+ languages grid)
- **sizes**:
  - `compact`: 36px height
  - `standard`: 42px height with flag icon and country name
- **states**: `closed`, `open`, `filtering`, `selected`, `disabled`
- **tokens**: `surface --color-surface`, `border --color-border`, `text --color-text`, `radius --radius-md`
- **a11y**: WAI-ARIA combobox pattern, `aria-expanded`, keyboard `ArrowUp`/`ArrowDown` navigation, `Enter` to select, `Escape` to close.
- **used on**: S04, S05, S07, S08, S09, S10

---

### AudioVisualizer
- **variants**: `waveform` (dynamic audio bar amplitudes), `circular-pulse` (breathing circle for mobile/recording), `frequency-bands` (live FFT bars)
- **states**: `idle` (low-amplitude subtle oscillation), `recording` (responsive audio level meter), `synthesizing` (flowing marquee wave), `muted` (static grey bar)
- **tokens**: `accent --color-accent`, `surface --color-surface`, `motion --motion-fast`
- **a11y**: `role="status"`, `aria-label="Microphone activity visualizer"` with live region announcements for mic state changes.
- **used on**: S04 (Voice), S08 (Meeting Room)

---

### VideoTile
- **variants**: `active-speaker` (prominent spotlight view), `grid-tile` (equal aspect ratio 16:9), `screen-share` (high priority widescreen), `local-pip` (bottom right floating window)
- **states**: `connecting`, `streaming-video`, `audio-only` (avatar fallback), `muted-audio`, `speaking` (green glowing ring indicator)
- **tokens**: `bg #0f172a`, `border --color-border`, `radius --radius-lg`, `shadow --shadow-card`
- **a11y**: `aria-label="{Participant Name} video stream"`, visible mute/unmute indicators, picture-in-picture keyboard toggles.
- **used on**: S08 (Video Room), S09 (Preflight)

---

### TranscriptStream
- **variants**: `realtime-chat` (scrolling message feed), `split-bilingual` (original text above, translated text below with speaker chip), `drawer` (collapsible side panel)
- **states**: `streaming` (cursor typing animation on current chunk), `finalized` (crisp timestamped card), `filtered` (highlighting search terms)
- **tokens**: `bg --color-surface`, `border --color-border`, `text --color-text`, `text-muted --color-text-muted`
- **a11y**: `aria-live="polite"`, `role="log"`, autoscroll pause when user manually scrolls up.
- **used on**: S04 (Voice), S08 (Meeting Room), S13 (History)

---

### DocumentDropzone
- **variants**: `full-panel` (drag over entire drop area), `compact-bar` (header attachment button)
- **states**: `idle` (dashed border, upload icon), `drag-over` (accent tint border and background), `uploading` (determinate progress percentage bar), `success`, `error`
- **tokens**: `border --color-border-input`, `surface --color-surface`, `radius --radius-lg`
- **a11y**: Hidden `<input type="file">` triggered via keyboard `Enter`/`Space` on dropzone container, format restrictions announced via `aria-describedby`.
- **used on**: S10 (Document Translation)

---

### DiffViewer
- **variants**: `inline-diff` (strikethrough red deletion, underline green addition), `side-by-side` (split comparison panes)
- **states**: `previewing` (showing proposed changes), `accepted` (resolved clean text), `rejected` (reverted)
- **tokens**: `bg-diff-del #fef2f2`, `text-diff-del #991b1b`, `bg-diff-add #f0fdf4`, `text-diff-add #166534`
- **a11y**: Clear `<del>` and `<ins>` markup with screen-reader friendly prefixes ("Removed:", "Added:").
- **used on**: S06 (AI Write)

---

### Modal
- **variants**: `standard-dialog` (centered max-w-lg card), `large-sheet` (max-w-3xl for meeting setups), `alert-dialog` (destructive confirmations)
- **states**: `entering` (scale 0.95 -> 1.0, fade-in backdrop), `open`, `exiting` (fade-out backdrop)
- **tokens**: `bg --color-bg`, `shadow --shadow-pop`, `radius --radius-xl`, `backdrop rgba(15,23,42,0.4)`
- **a11y**: Trap focus within modal, `Escape` key closes modal, return focus to trigger element upon closing, `aria-modal="true"`.
- **used on**: S02, S07, S12, S16

---

### Toaster (Sonner)
- **variants**: `success`, `info`, `warning`, `error`, `action-undo`
- **states**: `entering` (slide up 12px), `visible`, `dismissing`
- **tokens**: `bg --color-bg`, `border --color-border`, `shadow --shadow-pop`, `radius --radius-md`
- **a11y**: `role="status"` for info/success, `role="alert"` for errors; does not steal keyboard focus.
- **used on**: All screens
