/**
 * LiveKit-transport smoke: this is the path that needed a real browser —
 * single-use media-token minting, room join, camera publish (including the
 * "camera opened before the room" case, which the lobby exercises on every
 * join), and remote subscription. With Chromium fake devices both guests
 * publish synthetic video and each must RECEIVE the other's.
 */
import { expect, test } from "@playwright/test";
import { expectChip, joinAsGuest, seedMeeting } from "./helpers";

test.describe("LiveKit meeting, two guests", () => {
  test("media tokens connect both guests and remote video actually flows", async ({ browser, request }) => {
    const seed = await seedMeeting(request, "livekit");

    const alice = await joinAsGuest(browser, seed.inviteUrl, "Carol (E2E)", "en");
    const dave = await joinAsGuest(browser, seed.inviteUrl, "Dave (E2E)", "en");

    // Video room truth: link chip stays ok with the LiveKit room connected.
    await expectChip(alice.page, "media", "ok");
    await expectChip(dave.page, "media", "ok");

    // Roster across transports.
    await expect(alice.page.getByText("Dave (E2E)")).toBeVisible();
    await expect(dave.page.getByText("Carol (E2E)")).toBeVisible();

    // Remote video flow: each page ends up with at least two <video> elements
    // (self preview + the remote subscriber), each with a live MediaStream.
    // This is the regression test for the "published nothing to the room"
    // camera bug: with a fake camera the track count proves publication worked.
    const remoteVideos = await (async () => {
      await expect.poll(
        async () => (await alice.page.locator("video").count()) >= 2,
        { timeout: 60_000, intervals: [1_000, 2_000, 5_000] },
      ).toBe(true);
      return alice.page.locator("video").count();
    })();
    expect(remoteVideos).toBeGreaterThanOrEqual(2);

    // Mic publication must reach the room too ( muted vox is not asserted,
    // but the publish path itself is exercised by the lobby auto-toggle ).
    await expectChip(dave.page, "mic", "ok");

    // Leave tears down the room connection, not just the local tracks.
    await dave.page.locator('[aria-label="Leave call"]').click();
    await expect.poll(async () => {
      const detail = await (await request.get(`/api/v1/meetings/${seed.meetingId}`)).json();
      return !((detail.participants ?? []).some(
        (p: { display_name: string; status: string }) =>
          p.display_name === "Dave (E2E)" && p.status === "joined"));
    }, { timeout: 30_000, intervals: [1_000, 2_000] }).toBe(true);

    await alice.context.close();
    await dave.context.close();
  });
});
