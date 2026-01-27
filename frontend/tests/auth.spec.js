import { test, expect } from '@playwright/test';

test.describe('Authentication', () => {
  test('should display login page', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('h1')).toContainText('Unified Certificate Manager');
    await expect(page.locator('input[type="text"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
  });
  
  test('should login successfully', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[placeholder="Enter your username"]', 'admin');
    await page.fill('input[placeholder="Enter your password"]', 'changeme123');
    await page.click('button[type="submit"]');
    
    await page.waitForURL('**/dashboard', { timeout: 5000 });
    await expect(page).toHaveURL(/.*dashboard/);
    await expect(page.locator('h1')).toContainText('Dashboard');
  });
  
  test('should show error on invalid credentials', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[placeholder="Enter your username"]', 'invalid');
    await page.fill('input[placeholder="Enter your password"]', 'wrong');
    await page.click('button[type="submit"]');
    
    await expect(page.locator('.error-banner, .error-message')).toBeVisible({ timeout: 3000 });
  });
});
