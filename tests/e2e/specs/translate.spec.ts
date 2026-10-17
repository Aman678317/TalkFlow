/**
 * E2E: signup -> translate a sentence -> find it in history -> sign out and back
 * in (PDD §55).
 *
 * Requires the dev web/API pair of `docs/TESTING.md`: the Vite dev server on
 * :5173, proxying to the deployed backend tree on :8088.
 *
 * The asserted output is the dev translation table's own answer for
 * "Hello world!" — the run is only deterministic because the backend is
 * configured with `TRANSLATION_PROVIDER=dev_echo`. Point this at a real MT
 * provider and the expected string becomes a guess.
 */
import { test, expect } from '@playwright/test';

const stamp = Date.now().toString(36);
const email = `e2e_${stamp}@example.com`;
const password = 'e2epass123';
const SOURCE = 'Hello world!';
// The Hindi the dev table holds for this sentence. Asserted on the main
// paragraph rather than the panel, because the panel also renders an
// alternatives row whose entries are other answers to the same sentence.
const TRANSLATED = 'नमस्ते दुनिया';

test('signup, login, translate, and see history', async ({ page }) => {
  // --- signup ---
  await page.goto('/signup');
  await page.getByLabel('Full name').fill('E2E Tester');
  await page.getByLabel('Work email').fill(email);
  await page.getByLabel('Organization').fill('E2E Org');
  // The field's accessible name carries its hint, so exact 'Password' matches none.
  await page.getByLabel(/^password/i).fill(password);
  await page.getByRole('button', { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });
  await expect(page.getByText(/welcome back/i)).toBeVisible();

  // --- translate ---
  await page.goto('/translate');
  // Each panel picks its language from a chip row plus a "More languages"
  // select; Hindi is beyond the chips, and the second select on the page
  // belongs to the target panel. The option list comes from /languages, so
  // wait for it before choosing — and choose before typing, because the
  // request goes out on a debounce after the last keystroke.
  const target = page.getByLabel('More languages').nth(1);
  await expect(target.locator('option[value="hi"]')).toBeAttached({ timeout: 20_000 });
  await target.selectOption('hi');
  await page.getByLabel('Source text').fill(SOURCE);
  await expect(page.getByLabel('Translated text').locator('p').first())
    .toContainText(TRANSLATED, { timeout: 20_000 });

  // --- history ---
  await page.goto('/history');
  await expect(page.getByText(SOURCE).first()).toBeVisible({ timeout: 15_000 });

  // --- logout + login again ---
  // Signing out lands on the login screen, not the landing page.
  await page.getByText('Sign out').click();
  await expect(page).toHaveURL(/\/login$/, { timeout: 20_000 });
  await page.getByLabel('Email').fill(email);
  await page.getByLabel(/^password/i).fill(password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });
});
