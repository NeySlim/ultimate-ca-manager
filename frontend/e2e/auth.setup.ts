import { test as setup, expect } from '@playwright/test'
import { config } from './config'

const authFile = 'e2e/.auth/user.json'

/**
 * Authentication Setup
 * Runs before all tests to create authenticated session
 * 
 * UCM Login Flow:
 * 1. Enter username → Continue
 * 2. Auto-detects auth methods (mTLS, WebAuthn, Password)
 * 3. If WebAuthn available, shows fingerprint prompt and waits
 * 4. After WebAuthn timeout, "Use password instead" link appears
 * 5. Click link → Enter password → Sign in
 */
setup('authenticate', async ({ page }) => {
  // Go to login page
  await page.goto('/login')
  
  // Wait for login form
  await page.waitForSelector('input[type="text"], input[name="username"]', { timeout: 10000 })
  
  // Step 1: Enter username
  const usernameInput = page.locator('input[type="text"], input[name="username"]').first()
  await usernameInput.fill(config.credentials.username)
  
  // Click Continue button
  const continueButton = page.locator('button[type="submit"]').first()
  await continueButton.click()
  
  // Wait for auth method detection and WebAuthn timeout
  // WebAuthn will timeout after ~30s if no key is touched
  // The "Use password instead" link appears when loading=false
  await page.waitForTimeout(3000)
  
  // Try to find and click "Use password instead" link (may need to wait for WebAuthn to stop loading)
  const usePasswordLink = page.locator('text=Use password instead')
  try {
    await usePasswordLink.waitFor({ state: 'visible', timeout: 35000 })
    await usePasswordLink.click()
  } catch {
    // If link doesn't appear, password field might already be visible
    console.log('Password link not found, checking for password field directly')
  }
  
  // Step 2: Enter password
  await page.waitForSelector('input[type="password"]', { timeout: 10000 })
  const passwordInput = page.locator('input[type="password"]')
  await passwordInput.fill(config.credentials.password)
  
  // Click Sign In button
  const signInButton = page.locator('button[type="submit"]').first()
  await signInButton.click()
  
  // Wait for dashboard (successful login)
  await page.waitForURL('**/dashboard', { timeout: 15000 })
  
  // Verify we're logged in (wait for sidebar Dashboard link to be visible)
  await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible({ timeout: 10000 })
  
  // Save authentication state
  await page.context().storageState({ path: authFile })
})
