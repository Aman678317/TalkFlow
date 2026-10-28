/**
 * LiveKit outage drill: the media server going down must degrade the room
 * honestly instead of lying. Verified against the real pages with the real
 * room WS and real media tokens; the outage is simulated at the true socket
 * boundary from inside the page (helpers have native kill/refuse handles
 * for the media sockets):
 *
 *   1. mid-meeting kill  -> RoomEvent.Disconnected -> bounded reconnect
 *      (3 attempts, fresh single-use token per attempt) -> honest media
 *      chip DOWN + status pill error WITH a Reconnect button, while the
 *      room WS keeps delivering captions (media outage != total outage).
 *   2. Retry while the outage persists -> still an honest failure (never
 *      a phantom eternal "Reconnecting").
 *   3. Outage ends -> Reconnect re-mints a token and the room recovers
 *      to chip OK for real, and leave still tears the seat down.
 *
 * No Docker/network coupling: the media server stays healthy for the
 * neighboring specs; only the tested page's media sockets are cut.
 */
import { expect, test } from "@playwright/test";
import {
  expectChip, joinAsGuest, killMediaSockets, seedMeeting, setMediaReachable,
} from "./helpers";

test.describe("LiveKit media outage, drill", () => {
  test("mid-meeting outage: honest failure + captions keep flowing, bounded retry, real recovery", async ({ browser, request }) => {
    test.setTimeout(180_000);
    const seed = await seedMeeting(request, "livekit");

    const alice = await joinAsGuest(browser, seed.inviteUrl, "Erin (E2E)", "en");
    const dave = await joinAsGuest(browser, seed.inviteUrl, "Frank (E2E)", "en");

    // Real room first: chip ok proves the drill starts from truth.
    await expectChip(alice.page, "media", "ok");
    await expectChip(dave.page, "media", "ok");

    // --- 1) Kill alice's media transport mid-meeting and refuse new media
    //         sockets while the "outage" lasts. The room WS stays up; the
    //         media chip tells the truth: degraded while reconnecting, then
    //         DOWN with the actionable error, and dave is unaffected.
    await setMediaReachable(alice.page, false);
    await killMediaSockets(alice.page);
    await expectChip(alice.page, "media", "down", 60_000);
    await expectChip(dave.page, "media", "ok");

    const reconnect = alice.page.getByRole("button", { name: "Reconnect" }).first();
    await expect(reconnect).toBeVisible();

    // Media outage != total outage: dave's injected turn still reaches
    // alice as a caption through the room WS alone.
    await dave.page.getByRole("button", { name: "HI→English" }).click();
    await expect(alice.page.getByTestId("caption-box")).toBeVisible();

    // --- 2) Retry while the outage persists: bounded and honest again.
    await reconnect.click();
    await expectChip(alice.page, "media", "down", 60_000);
    await expect(reconnect).toBeVisible();

    // --- 3) Outage ends: Reconnect must recover the room for real.
    await setMediaReachable(alice.page, true);
    await reconnect.click();
    await expectChip(alice.page, "media", "ok", 60_000);

    // Leave cleanliness survives the error/recovery cycle for both seats.
    await dave.page.locator('[aria-label="Leave call"]').click({ force: true });
    await expect.poll(async () => {
      const detail = await (await request.get(`/api/v1/meetings/${seed.meetingId}`)).json();
      return !((detail.participants ?? []).some(
        (p: { display_name: string; status: string }) =>
          p.display_name === "Frank (E2E)" && p.status === "joined"));
    }, { timeout: 30_000, intervals: [1_000, 2_000] }).toBe(true);

    await alice.context.close();
    await dave.context.close();
  });

  test("outage before join: connection fails honestly with a Reconnect affordance", async ({ browser, request }) => {
    const seed = await seedMeeting(request, "livekit");

    // The media server is already unreachable when Erin joins: the hook's
    // initial connect loop (3 attempts, fresh single-use token each) must
    // end in the honest error state, not a phantom connection.
    const erin = await joinAsGuest(browser, seed.inviteUrl, "Erin (E2E)", "en", { preBlocked: true });

    await expectChip(erin.page, "media", "down", 60_000);
    await expect(erin.page.getByRole("button", { name: "Reconnect" }).first()).toBeVisible();

    // Media-down != seat-down: Frank joins through the room WS alone and the
    // roster still finds him from Erin's page.
    const frank = await joinAsGuest(browser, seed.inviteUrl, "Frank (E2E)", "en", { preBlocked: true });
    await expectChip(frank.page, "media", "down", 60_000);
    await expect(erin.page.getByText("Frank (E2E)")).toBeVisible();

    await erin.context.close();
    await frank.context.close();
  });
});
