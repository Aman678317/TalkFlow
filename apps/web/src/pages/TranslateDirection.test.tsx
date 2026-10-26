import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import Translate from "./Translate";

const apiMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", () => ({
  api: apiMock,
  friendlyMessage: (e: unknown) => String(e),
}));

const streamMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/liveTranslation", () => ({ streamLiveTranslation: streamMock }));

function cap(code: string, name: string, native: string, rtl: boolean) {
  return {
    code, name, native_name: native, script: "Latn", rtl,
    speech_input_supported: true, speech_output_supported: true,
    translation_supported: true, realtime_supported: true, document_supported: true,
    translation_status: "PRODUCTION", speech_input_status: "SUPPORTED",
    speech_output_status: "SUPPORTED", realtime_status: "SUPPORTED",
    document_status: "SUPPORTED", tts_voices: [],
  };
}

const LANGS = [
  cap("en", "English", "English", false),
  cap("de", "German", "Deutsch", false),
  cap("ar", "Arabic", "العربية", true),
];

function renderTranslate() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <Translate />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

async function pickTarget(name: string) {
  fireEvent.click(screen.getByRole("button", { name: "More target languages" }));
  fireEvent.click(await screen.findByRole("button", { name }, { timeout: 5000 }));
}

describe("Translate panes follow the script direction", () => {
  beforeEach(() => {
    apiMock.mockImplementation((path: string) => {
      if (path === "/api/v1/languages") return Promise.resolve(LANGS);
      if (path === "/api/v1/dictionary") {
        return Promise.resolve({ word: "hello", definition: "", translations: [] });
      }
      return Promise.resolve([]);
    });
    streamMock.mockImplementation((_payload: unknown, handlers: any) => {
      handlers.onDone({
        request_id: "r-1",
        translations: [{
          translation_id: "r-1",
          source_language: "en",
          target_language: "ar",
          source_text: "Hello there my friend",
          translated_text: "مرحبا",
          model: "nllb-200-600m",
          provider: "nllb_ct2",
          latency_ms: 20,
          quality_flags: [],
        }],
        detected_confidence: null,
        ttfd_ms: 10,
        total_ms: 20,
        draft_used: false,
      });
      return Promise.resolve();
    });
  });

  afterEach(() => {
    cleanup();
    apiMock.mockReset();
    streamMock.mockReset();
  });

  it("keeps a Latin-script source left-to-right", async () => {
    renderTranslate();
    await pickTarget("Arabic (العربية)");
    const box = screen.getByLabelText("Source text");
    fireEvent.change(box, { target: { value: "Hello there my friend" } });
    await waitFor(() => expect(box).toHaveAttribute("dir", "ltr"));
  });

  it("sets dir=rtl on the source box once an RTL language is picked", async () => {
    renderTranslate();
    fireEvent.click(screen.getByRole("button", { name: "More source languages" }));
    fireEvent.click(await screen.findByRole("button", { name: "Arabic (العربية)" }, { timeout: 5000 }));
    const box = screen.getByLabelText("Source text");
    fireEvent.change(box, { target: { value: "مرحبا" } });
    await waitFor(() => expect(box).toHaveAttribute("dir", "rtl"));
  });

  it("sets dir=rtl on the translated output for an RTL target", async () => {
    renderTranslate();
    await pickTarget("Arabic (العربية)");
    fireEvent.change(screen.getByLabelText("Source text"), { target: { value: "Hello there my friend" } });
    await screen.findByText("مرحبا");
    expect(screen.getByText("مرحبا")).toHaveAttribute("dir", "rtl");
  });
});
