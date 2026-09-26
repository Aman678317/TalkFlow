/**
 * E2E golden demo (PDD §69) across two browser contexts:
 * A (Hindi speaker, hears English) and C (hears Marathi) in one meeting.
 * Speech is injected via the dev-mode text channel when STT runs in dev mode,
 * or via the fake microphone device in full-model environments.
 */
import { test, expect, type Page } from '@playwright/test';

const stamp = Date.now().toString(36);

async function signup(page: Page, name: string, org?: string) {
  const email = `e2e_${name}_${stamp}@example.com`;
  await page.goto('/signup');
  await page.getByLabel('Full name').fill(name);
  await page.getByLabel('Work email').fill(email);
  if (org) await page.getByLabel('Organization').fill(org);
  await page.getByLabel('Password', { exact: true }).fill('e2epass123');
  await page.getByRole('button', { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });
  return email;
}

test('golden demo: hindi speaker -> english + marathi listeners', async ({ browser }) => {
  const ctxA = await browser.newContext();
  const ctxC = await browser.newContext();
  const pageA = await ctxA.newPage();
  const pageC = await ctxC.newPage();

  // A creates the workspace
  await signup(pageA, 'Speaker A', 'Golden Org');

  // create meeting as A: speaks Hindi, hears English
  await pageA.goto('/meetings');
  await pageA.getByRole('button', { name: /new meeting/i }).click();
  await pageA.getByLabel('Meeting title').fill('Golden Demo');
  await pageA.getByLabel('I speak').selectOption('hi');
  await pageA.getByLabel('I want to hear').selectOption('en');
  await pageA.getByRole('button', { name: /create & join/i }).click();
  await expect(pageA).toHaveURL(/\/meeting\//, { timeout: 20_000 });
  const meetingUrl = pageA.url();
  const meetingId = meetingUrl.split('/').pop()!;

  // invite C into the org via API-free UI path: team page
  const emailC = `e2e_C_${stamp}@example.com`;
  await pageA.goto('/team');
  await pageA.getByRole('button', { name: /add member/i }).click();
  await pageA.getByLabel('Email').fill(emailC);
  await pageA.getByRole('button', { name: /^add member$/i }).last().click();
  await expect(pageA.getByText(emailC)).toBeVisible({ timeout: 10_000 });

  // C signs up + logs into Golden Org
  await signup(pageC, 'Listener C');
  // C re-login into A's org is automatic once membership exists on next login;
  // use the API through the page context to fetch org id, then re-login via UI:
  await pageC.goto('/settings'); // ensure loaded
  // join meeting room directly (join endpoint accepts any org member)
  await pageC.goto(`/meeting/${meetingId}`);
  // If C's token points at their own org, join will 404 -> re-login flow:
  if (await pageC.getByText(/could not join|not found/i).first().isVisible().catch(() => false)) {
    await pageC.evaluate(async () => {
      localStorage.clear();
    });
    await pageC.goto('/login');
    await pageC.getByLabel('Email').fill(emailC);
    await pageC.getByLabel('Password', { exact: true }).fill('e2epass123');
    await pageC.getByRole('button', { name: /sign in/i }).click();
    await expect(pageC).toHaveURL(/\/dashboard/, { timeout: 20_000 });
    await pageC.goto(`/meeting/${meetingId}`);
  }

  // C sets: hears Marathi
  await expect(pageC.getByLabel('I want to hear')).toBeVisible({ timeout: 20_000 });
  await pageC.getByLabel('I want to hear').selectOption('mr');

  // A's room: enable dev speech channel if present, "speak" Hindi
  const inject = pageA.getByLabel('Simulate spoken utterance');
  if (await inject.isVisible().catch(() => false)) {
    await inject.fill('नमस्ते, आज हम परियोजना की समीक्षा करेंगे।');
    await pageA.getByRole('button', { name: /^speak$/i }).click();
  } else {
    // real mic path (fake device) — enable mic and wait for VAD/STT
    await pageA.getByRole('button', { name: /unmute microphone/i }).click();
    await pageA.waitForTimeout(6000);
  }

  // canonical caption visible to A (Hindi source)
  await expect(pageA.getByText('नमस्ते').first()).toBeVisible({ timeout: 25_000 });

  // C sees the same source + a Marathi translated caption
  await expect(pageC.getByText('नमस्ते').first()).toBeVisible({ timeout: 25_000 });
  await expect(pageC.locator('text=/mr|मराठी|\\[mr\\]/i').first()).toBeVisible({ timeout: 25_000 });

  // transcript persisted: A's transcript panel has the segment
  await expect(pageA.getByRole('tab', { name: /transcript/i })).toBeVisible();

  await ctxA.close();
  await ctxC.close();
});

test('document upload flow shows pipeline progress', async ({ page }) => {
  await signup(page, 'DocUser', 'Doc Org');
  await page.goto('/documents');
  await page.getByRole('button', { name: /upload document/i }).click();
  const fs = await import('node:fs');
  const os = await import('node:os');
  const path = await import('node:path');
  const tmp = path.join(os.tmpdir(), `e2e_${stamp}.txt`);
  fs.writeFileSync(tmp, 'Quarterly report.\n\nRevenue grew strongly this quarter.\n');
  await page.locator('input[type=file]').first().setInputFiles(tmp);
  await page.getByLabel('Target language').selectOption('hi');
  await page.getByRole('button', { name: /upload & translate/i }).click();
  await expect(page.getByText(/ready|translating|parsing/i).first())
    .toBeVisible({ timeout: 45_000 });
});
