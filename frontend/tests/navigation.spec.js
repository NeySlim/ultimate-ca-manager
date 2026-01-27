import { test, expect } from '@playwright/test';

test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[placeholder="Enter your username"]', 'admin');
    await page.fill('input[placeholder="Enter your password"]', 'changeme123');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/dashboard');
  });
  
  test('should navigate to all main pages', async ({ page }) => {
    const pages = ['CAs', 'Certificates', 'CSRs', 'ACME', 'CRL/OCSP', 'SCEP', 'Templates', 'TrustStore'];
    
    for (const pageName of pages) {
      await page.click(`button:has-text("${pageName}")`);
      await page.waitForTimeout(500);
      await expect(page.locator('h1')).toBeVisible();
    }
  });
  
  test('should open command palette with ⌘K', async ({ page }) => {
    await page.keyboard.press('Meta+K');
    await expect(page.locator('.command-palette')).toBeVisible({ timeout: 1000 });
    await expect(page.locator('input[placeholder*="Search"]')).toBeVisible();
  });
  
  test('should search in command palette', async ({ page }) => {
    await page.keyboard.press('Meta+K');
    await page.fill('input[placeholder*="Search"]', 'cert');
    await expect(page.locator('.command-item')).toHaveCount(2); // Certificates + Certificate Authorities
  });
  
  test('should open theme switcher with ⌘T', async ({ page }) => {
    await page.keyboard.press('Meta+T');
    await expect(page.locator('.theme-switcher')).toBeVisible({ timeout: 1000 });
    await expect(page.locator('.theme-option')).toHaveCount(6);
  });
  
  test('should open More dropdown', async ({ page }) => {
    await page.click('button:has-text("More")');
    await expect(page.locator('.more-menu')).toBeVisible();
    await expect(page.locator('button:has-text("Settings")')).toBeVisible();
    await expect(page.locator('button:has-text("Users")')).toBeVisible();
    await expect(page.locator('button:has-text("Account")')).toBeVisible();
  });
  
  test('should navigate to Settings from More menu', async ({ page }) => {
    await page.click('button:has-text("More")');
    await page.click('button:has-text("Settings")');
    await expect(page).toHaveURL(/.*settings/);
    await expect(page.locator('h1')).toContainText('Settings');
  });
});
