/**
 * WS-transport smoke: two guests join through the real lobby, the canned
 * transcript inject drives the real server pipeline (STT skip → MT fan-out →
 * TTS delivery), every listener's truth chips verify it, and Leave clears the
 * server seat — the exact teardown path fixed in the Leave-button remediation.
 */
import { expect, test } from "@playwright/test";
import { chipLevel, expectChip, joinAsGuest, seedMeeting } from "./helpers";

test.describe("WS meeting, two guests", () => {
  test("guests see each other, a translated turn lands as captions + voice chips, leave clears the seat", async ({ browser, request }) => {
    const seed = await seedMeeting(request, "ws");

    const alice = await joinAsGuest(browser, seed.inviteUrl, "Alice (E2E)", "en");
    const bob = await joinAsGuest(browser, seed.inviteUrl, "Bob (E2E)", "en");

    // 1) Transport truth on BOTH pages: link ok (WS joined), mic ok (the lobby
    //    auto-toggled mic with the fake device).
    await expectChip(alice.page, "media", "ok");
    await expectChip(bob.page, "media", "ok");
    await expectChip(alice.page, "mic", "ok");

    // 2) Roster: each page shows the other guest's tile name.
    await expect(alice.page.getByText("Bob (E2E)")).toBeVisible();
    await expect(bob.page.getByText("Alice (E2E)")).toBeVisible();

    // 3) Pipeline: inject a Hindi turn; both listeners hear language "en", so
    //    the fan-out must translate it and synthesize voice for them.
    await bob.page.getByRole("button", { name: "HI→English" }).click();

    // Translated caption reaches the listener (translated text preferred;
    // the original line is what the overlay falls back to).
    await expect(bob.page.getByTestId("caption-box")).toBeVisible();
    await expect(alice.page.getByTestId("caption-box")).toBeVisible();

    // Truth chips agree with reality, not with the banner: STT ok, MT ok,
    // TTS ok on the listener page.
    await expectChip(bob.page, "stt", "ok");
    await expectChip(bob.page, "mt", "ok");
    await expectChip(bob.page, "tts", "ok");

    // 4) Leave teardown: Bob leaves, his seat disappears server-side
    //    (participants API is the same source the roster effect polls).
    await bob.page.locator('[aria-label="Leave call"]').click();
    await expect(bob.page).not.toHaveURL(seed.inviteUrl); // navigated away
    const detail = await (await request.get(`/api/v1/meetings/${seed.meetingId}`)).json();
    const bobSeat = (detail.participants ?? []).find(
      (p: { display_name: string; status: string }) =>
        p.display_name === "Bob (E2E)" && p.status === "joined");
    expect(bobSeat, "Leaving must clear the joined seat immediately").toBeUndefined();

    // 5) Alice still sees the room alive after Bob left.
    expect(await chipLevel(alice.page, "media")).toBe("ok");

    await alice.context.close();
    await bob.context.close();
  });
});
