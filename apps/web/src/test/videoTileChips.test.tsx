/**
 * Per-seat language chips — plan §306 parity close-out (B3).
 *
 * The meeting tile advertises each participant's speak/hear languages, so
 * seat routing and caption modes are legible in the room (frontend side of
 * the translated-calls parity that the backend leg fan-out implements).
 */
import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { VideoTile } from '@/components/meeting/VideoTile';

describe('VideoTile — per-seat language chips', () => {
  it('renders the speaks/hears chip for a participant seat', () => {
    const { container } = render(<VideoTile name="Aman" lang="en" hear="hi" />);
    expect(container.textContent).toMatch(/speaks\s*en\s*·\s*hears\s*hi/);
    expect(container.textContent).toContain('Aman');
  });

  it('reflects a seat language change (mid-call re-route)', () => {
    const { container, rerender } = render(
      <VideoTile name="Riya" lang="en" hear="hi" />,
    );
    rerender(<VideoTile name="Riya" lang="hi" hear="ja" />);
    expect(container.textContent).toMatch(/speaks\s*hi\s*·\s*hears\s*ja/);
    expect(container.textContent).not.toMatch(/hears\s*hi\b/);
  });

  it('keeps the name overlay for a self seat', () => {
    const { container } = render(
      <VideoTile name="Me" lang="en" hear="en" self />,
    );
    expect(container.textContent).toContain('Me (you)');
    expect(container.textContent).toMatch(/speaks\s*en\s*·\s*hears\s*en/);
  });

  it('renders live in-tile subtitle when subtitle prop is provided', () => {
    const { getByTestId, queryByTestId, rerender } = render(
      <VideoTile name="Carlos" lang="es" hear="en" speaking />
    );
    expect(queryByTestId('tile-subtitle')).toBeNull();

    rerender(
      <VideoTile name="Carlos" lang="es" hear="en" speaking subtitle="Hola, buenas tardes a todos" />
    );
    const subtitleEl = getByTestId('tile-subtitle');
    expect(subtitleEl).toBeDefined();
    expect(subtitleEl.textContent).toContain('Hola, buenas tardes a todos');
  });
});

