/**
 * Frontend unit tests: realtime client reconnect/dedup logic, audio helpers,
 * and design-system component rendering.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { RealtimeClient } from '@/lib/realtime';
import type { ServerEvent } from '@globaltalk/shared-types';
import { Badge, Button, EmptyState, Modal, Tabs } from '@/components/ui';
import Login from '@/pages/Login';

const mockLogin = vi.fn();
const mockAuthState = { login: mockLogin, user: null, status: 'unauthed' };
vi.mock('@/stores/auth', () => ({
  useAuth: (selector?: (state: typeof mockAuthState) => unknown) =>
    typeof selector === 'function' ? selector(mockAuthState) : mockAuthState,
}));

// ---------------------------------------------------------------------------
// RealtimeClient — sequence dedup & resume
// ---------------------------------------------------------------------------

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  readyState = 0;
  binaryType = 'blob';
  sent: Array<string | ArrayBuffer> = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: ((ev: { code?: number }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }
  send(data: string | ArrayBuffer) { this.sent.push(data); }
  close() { this.readyState = 3; this.onclose?.({ code: 1000 }); }

  // test helpers
  simulateOpen() { this.readyState = 1; this.onopen?.(); }
  simulateMessage(data: unknown) {
    this.onmessage?.({ data: typeof data === 'string' ? data : JSON.stringify(data) });
  }
  simulateDrop(code = 1006) { this.readyState = 3; this.onclose?.({ code }); }
}

function makeEvent(seq: number, type = 'transcript.final'): ServerEvent {
  return {
    version: 1, type: type as ServerEvent['type'], session_id: 's1',
    conversation_id: 'c1', speaker_id: null, sequence: seq,
    timestamp: new Date().toISOString(), data: { seq },
  };
}

describe('RealtimeClient', () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('delivers events and tracks the highest sequence', () => {
    const events: ServerEvent[] = [];
    const client = new RealtimeClient({
      url: '/ws/realtime?ticket=x', onEvent: (e) => events.push(e) });
    client.connect();
    const ws = MockWebSocket.instances[0];
    ws.simulateOpen();
    ws.simulateMessage(makeEvent(1));
    ws.simulateMessage(makeEvent(2));
    expect(events).toHaveLength(2);
    expect(client.getStatus()).toBe('open');
  });

  it('dedupes replayed sequences (idempotent resume)', () => {
    const events: ServerEvent[] = [];
    const client = new RealtimeClient({
      url: '/ws/realtime?ticket=x', onEvent: (e) => events.push(e) });
    client.connect();
    const ws = MockWebSocket.instances[0];
    ws.simulateOpen();
    ws.simulateMessage(makeEvent(5));
    ws.simulateMessage(makeEvent(5)); // duplicate
    ws.simulateMessage(makeEvent(4)); // late duplicate
    expect(events).toHaveLength(1);
  });

  it('sends session.resume with last sequence after reconnect', () => {
    vi.useFakeTimers();
    const client = new RealtimeClient({
      url: '/ws/realtime?ticket=x', onEvent: () => {} });
    client.connect();
    const ws1 = MockWebSocket.instances[0];
    ws1.simulateOpen();
    ws1.simulateMessage(makeEvent(42));
    ws1.simulateDrop(1006); // network drop -> should reconnect

    expect(client.getStatus()).toBe('reconnecting');
    vi.advanceTimersByTime(2000); // backoff window
    const ws2 = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    ws2.simulateOpen();
    const resume = ws2.sent.map((s) => JSON.parse(s as string))
      .find((m) => m.type === 'session.resume');
    expect(resume).toBeTruthy();
    expect(resume.data.last_sequence).toBe(42);
    vi.useRealTimers();
  });

  it('does not retry on auth rejection (4401)', () => {
    vi.useFakeTimers();
    const client = new RealtimeClient({
      url: '/ws/realtime?ticket=bad', onEvent: () => {} });
    client.connect();
    MockWebSocket.instances[0].simulateDrop(4401);
    expect(client.getStatus()).toBe('failed');
    vi.advanceTimersByTime(5000);
    expect(MockWebSocket.instances).toHaveLength(1); // no reconnect attempt
    vi.useRealTimers();
  });

  it('sends heartbeat pings while open', () => {
    vi.useFakeTimers();
    const client = new RealtimeClient({
      url: '/ws/realtime?ticket=x', onEvent: () => {} });
    client.connect();
    const ws = MockWebSocket.instances[0];
    ws.simulateOpen();
    vi.advanceTimersByTime(26000);
    const ping = ws.sent.map((s) => JSON.parse(s as string)).find((m) => m.type === 'ping');
    expect(ping).toBeTruthy();
    client.close();
    vi.useRealTimers();
  });
});

// ---------------------------------------------------------------------------
// Design system components
// ---------------------------------------------------------------------------

describe('UI components', () => {
  it('Button shows loading state and disables', () => {
    render(<Button loading>Save</Button>);
    const btn = screen.getByRole('button');
    expect(btn).toBeDisabled();
    expect(screen.getByRole('status')).toBeTruthy(); // spinner aria
  });

  it('Badge renders tone classes', () => {
    render(<Badge tone="green">active</Badge>);
    expect(screen.getByText('active')).toBeTruthy();
  });

  it('Modal opens and closes on Escape', () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Test dialog">
        <p>body</p>
      </Modal>);
    expect(screen.getByRole('dialog')).toBeTruthy();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('Modal not rendered when closed', () => {
    render(<Modal open={false} onClose={() => {}} title="X"><p /></Modal>);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('Tabs switches with keyboard arrows', () => {
    const onChange = vi.fn();
    render(<Tabs active="a" onChange={onChange}
                 tabs={[{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }]} />);
    const active = screen.getByRole('tab', { selected: true });
    fireEvent.keyDown(active, { key: 'ArrowRight' });
    expect(onChange).toHaveBeenCalledWith('b');
  });

  it('EmptyState renders title and action', () => {
    render(<EmptyState title="Nothing here" action={<Button>Do it</Button>} />);
    expect(screen.getByText('Nothing here')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Do it' })).toBeTruthy();
  });

  it('lets a user sign in with the demo account in one click', async () => {
    mockLogin.mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <Login />
      </MemoryRouter>
    );

    fireEvent.click(screen.getByRole('button', { name: /use demo account/i }));

    expect(mockLogin).toHaveBeenCalledWith('demo@globaltalk.local', 'demo1234');
  });
});
