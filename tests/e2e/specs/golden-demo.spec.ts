/**
 * E2E golden demo (PDD §69) across two browser sessions in one meeting.
 *
 * A signs up, creates the meeting and speaks Hindi to their own language; C joins
 * the same room from the shared link with no account at all, listening in English.
 * The utterance goes in through the room's dev speech-injection channel, which is
 * the `transcript.inject` event over the same WebSocket a microphone feeds — so
 * what is proven here is the fan-out and per-listener routing in two real browser
 * clients, not recogniser quality.
 *
 * The canned text is `नमस्ते दुनिया!` because that string is an exact key in the
 * dev translation table: any other wording leaves the room for a public web
 * translator, and the assertion below would then be a bet on the internet.
 */
import { test, expect, type Page } from '@playwright/test';

const stamp = Date.now().toString(36);
const SPOKEN_HI = 'नमस्ते दुनिया!';
const SPOKEN_EN = 'Hello world!';

async function signup(page: Page, name: string, org?: string) {
  const email = `e2e_${name.replace(/\W+/g, '_').toLowerCase()}_${stamp}@example.com`;
  await page.goto('/signup');
  await page.getByLabel('Full name').fill(name);
  await page.getByLabel('Work email').fill(email);
  if (org) await page.getByLabel('Organization').fill(org);
  // The field's accessible name carries its hint ("Password At least 8
  // characters…"), so an exact match on 'Password' resolves to nothing.
  await page.getByLabel(/^password/i).fill('e2epass123');
  await page.getByRole('button', { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });
  return email;
}

async function joinRoom(page: Page, name: string, speak: string, hear: string) {
  await page.getByLabel('Your name').fill(name);
  await page.getByLabel('I speak').selectOption(speak);
  await page.getByLabel('Translate incoming speech into').selectOption(hear);
  await page.getByRole('button', { name: /add to call/i }).click();
}

test('golden demo: hindi speaker and an english listener in one room', async ({ browser }) => {
  const ctxA = await browser.newContext();
  const ctxC = await browser.newContext();
  const pageA = await ctxA.newPage();
  const pageC = await ctxC.newPage();

  await signup(pageA, 'Speaker A', 'Golden Org');

  await pageA.goto('/meetings');
  await pageA.getByRole('button', { name: /new meeting/i }).click();
  await pageA.getByLabel('Meeting title').fill('Golden Demo');
  await pageA.getByRole('button', { name: /create & join/i }).click();
  await expect(pageA).toHaveURL(/\/meeting\//, { timeout: 20_000 });
  const meetingUrl = pageA.url();

  // A hears their own language: the room shows them what they said.
  await joinRoom(pageA, 'Speaker A', 'hi', 'hi');

  // C arrives on the same link, signed out. The room is not behind a login: a
  // listener with a link and a name is a participant.
  await pageC.goto(meetingUrl);
  await joinRoom(pageC, 'Listener C', 'en', 'en');

  // Both seats have to be registered before anyone speaks. "Add to call" returns
  // when the click lands, not when the handshake finishes, and a turn that goes
  // up while the room holds one participant fans out to nothing — the speaker is
  // then told "Translation Unavailable · no_targets" and the listener never sees
  // the sentence at all.
  await expect(pageC.getByText(/Realtime Translation Active/i)).toBeVisible({ timeout: 20_000 });
  await expect(pageA.getByText('Listener C').first()).toBeVisible({ timeout: 20_000 });

  // The dev bar only exists once the handshake put A in the room.
  const inject = pageA.getByRole('button', { name: 'HI→English' });
  await expect(inject).toBeVisible({ timeout: 20_000 });
  await inject.click();

  // Both see the source caption — the canonical transcript is one conversation,
  // not a per-client copy.
  await expect(pageA.getByText(SPOKEN_HI).first()).toBeVisible({ timeout: 25_000 });
  await expect(pageC.getByText(SPOKEN_HI).first()).toBeVisible({ timeout: 25_000 });

  // Only C is asked for English, and it arrives in C's session, not A's.
  await expect(pageC.getByText(SPOKEN_EN).first()).toBeVisible({ timeout: 25_000 });
  await expect(pageA.getByText(SPOKEN_EN)).toHaveCount(0);

  await ctxA.close();
  await ctxC.close();
});

test('document upload flow shows pipeline progress', async ({ page }) => {
  await signup(page, 'DocUser', 'Doc Org');
  await page.goto('/documents');
  const filename = `e2e_${stamp}.txt`;
  const fs = await import('node:fs');
  const os = await import('node:os');
  const path = await import('node:path');
  const tmp = path.join(os.tmpdir(), filename);
  fs.writeFileSync(tmp, 'Quarterly report.\n\nRevenue grew strongly this quarter.\n');
  // There is no submit button: the dropzone uploads on selection, and the
  // request carries whichever target language is set at that moment.
  await page.getByLabel('Target language').selectOption('hi');
  await page.locator('input[type=file]').first().setInputFiles(tmp);

  await expect(page.getByText(filename).first()).toBeVisible({ timeout: 30_000 });
  // The queue badge is the only element on the page whose whole text is one of
  // these words, so anchoring the pattern is what keeps it a status assertion.
  const status = page.getByText(/^(queued|parsing|translating|ready|failed)$/i).first();
  await expect(status).toBeVisible({ timeout: 30_000 });
  await expect(status).toHaveText(/^(ready|failed)$/i, { timeout: 90_000 });
});
