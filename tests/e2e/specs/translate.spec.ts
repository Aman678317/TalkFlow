/**
 * E2E: signup -> login -> text translation -> history (PDD §55).
 * Requires: API on :8000, web on :5173 (see docs/TESTING.md).
 */
import { test, expect } from '@playwright/test';

const stamp = Date.now().toString(36);
const email = `e2e_${stamp}@example.com`;
const password = 'e2epass123';

test('signup, login, translate, and see history', async ({ page }) => {
  // --- signup ---
  await page.goto('/signup');
  await page.getByLabel('Full name').fill('E2E Tester');
  await page.getByLabel('Work email').fill(email);
  await page.getByLabel('Organization').fill('E2E Org');
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: /create account/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });
  await expect(page.getByText(/good (morning|afternoon|evening)/i)).toBeVisible();

  // --- translate ---
  await page.goto('/translate');
  await page.getByLabel('Source text').fill('Hello, how are you today?');
  await page.getByLabel('Target language').selectOption('hi');
  // debounce ~650ms + backend latency
  const target = page.locator('textarea[aria-label="Source text"]').locator('..')
    .locator('xpath=following-sibling::*').first();
  await expect(page.getByText(/\[hi\]|नमस्ते|Hello, how are you/i).first())
    .toBeVisible({ timeout: 15_000 });

  // --- history ---
  await page.goto('/history');
  await expect(page.getByText('Hello, how are you today?').first())
    .toBeVisible({ timeout: 15_000 });

  // --- logout + login again ---
  await page.getByRole('button', { name: /sign out/i }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goto('/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 20_000 });
});
