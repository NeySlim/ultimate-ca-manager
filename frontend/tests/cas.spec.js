import { test, expect } from '@playwright/test';

test.describe('Certificate Authorities', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[placeholder="Enter your username"]', 'admin');
    await page.fill('input[placeholder="Enter your password"]', 'changeme123');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/dashboard');
    await page.click('button:has-text("CAs")');
  });
  
  test('should display CAs page', async ({ page }) => {
    await expect(page.locator('h1')).toContainText('Certificate Authorities');
  });
  
  test('should toggle between Tree and Grid view', async ({ page }) => {
    await page.click('button:has-text("Tree")');
    await page.waitForTimeout(300);
    await expect(page.locator('.ca-tree, .tree-view')).toBeVisible();
    
    await page.click('button:has-text("Grid")');
    await page.waitForTimeout(300);
    await expect(page.locator('.ca-grid, .grid-view')).toBeVisible();
  });
});
