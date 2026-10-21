/**
 * "Translate a selection" — the reference product translates whatever the
 * user selects; in the app the same gesture works inside the editor.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { SelectionTranslate } from "../SelectionTranslate";

const apiMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api", () => ({
  api: apiMock,
  friendlyMessage: (e: unknown) => (e instanceof Error ? e.message : String(e)),
}));

function Harness() {
  const ref = React.useRef<HTMLTextAreaElement | null>(null);
  return (
    <div className="relative">
      <textarea ref={ref} aria-label="Source text" defaultValue="translate the cloud console please" />
      <SelectionTranslate editorRef={ref} sourceLanguage="en" targetLanguage="hi" />
    </div>
  );
}

function selectPhrase() {
  const ta = screen.getByLabelText("Source text") as HTMLTextAreaElement;
  ta.focus();
  ta.setSelectionRange(14, 27); // "cloud console"
  fireEvent.mouseUp(document);
  return ta;
}

afterEach(() => {
  cleanup();
  apiMock.mockReset();
});

describe("SelectionTranslate", () => {
  it("offers to translate the selected phrase", () => {
    render(<Harness />);
    selectPhrase();
    expect(screen.getByText("Translate selection")).toBeTruthy();
    // the popover quotes the selection (the textarea contains it too)
    expect(screen.getByTitle("cloud console")).toBeTruthy();
  });

  it("stays hidden when nothing (or almost nothing) is selected", () => {
    render(<Harness />);
    const ta = screen.getByLabelText("Source text") as HTMLTextAreaElement;
    ta.focus();
    ta.setSelectionRange(3, 3);
    fireEvent.mouseUp(document);
    expect(screen.queryByText("Translate selection")).toBeNull();
  });

  it("translates the selection and shows the result", async () => {
    apiMock.mockResolvedValue({ translations: [{ translated_text: "क्लाउड कंसोल" }] });
    render(<Harness />);
    selectPhrase();
    // A real click: mousedown collapses the textarea selection, the document
    // mouseup must not clear the popover, and only then does the click land.
    const button = screen.getByText("Translate selection");
    fireEvent.mouseDown(button);
    fireEvent.mouseUp(document);
    fireEvent.click(button);
    await waitFor(() => expect(screen.getByText("क्लाउड कंसोल")).toBeTruthy());
    expect(apiMock).toHaveBeenCalledWith(
      "/api/v1/translate",
      expect.objectContaining({
        method: "POST",
        body: expect.objectContaining({ text: "cloud console", target_language: "hi" }),
      }),
    );
  });

  it("surfaces an error instead of failing silently", async () => {
    apiMock.mockRejectedValue(new Error("provider unavailable"));
    render(<Harness />);
    selectPhrase();
    fireEvent.click(screen.getByText("Translate selection"));
    await waitFor(() => expect(screen.getByText("provider unavailable")).toBeTruthy());
  });
});
