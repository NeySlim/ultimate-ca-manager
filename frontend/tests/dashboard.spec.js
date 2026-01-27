import { test, expect } from '@playwright/test';

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[placeholder="Enter your username"]', 'admin');
    await page.fill('input[placeholder="Enter your password"]', 'changeme123');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/dashboard');
  });
  
  test('should display dashboard stats', async ({ page }) => {
    await expect(page.locator('h1')).toContainText('Dashboard');
    await expect(page.locator('.stats-grid')).toBeVisible();
    await expect(page.locator('.stat-card')).toHaveCount(4);
  });
  
  test('should show stat values', async ({ page }) => {
    const statLabels = ['Total Certificates', 'Active CAs', 'Expiring Soon', 'Revoked'];
    
    for (const label of statLabels) {
      await expect(page.locator(`.stat-label:has-text("${label}")`)).toBeVisible();
    }
  });
  
  test('should display system status', async ({ page }) => {
    await expect(page.locator('h2:has-text("System Status")')).toBeVisible();
    await expect(page.locator('.status-item')).toHaveCount.greaterThanOrEqual(3);
  });
});
