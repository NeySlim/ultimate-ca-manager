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
  // Listen to all network requests for debugging
  const requests: string[] = []
  page.on('response', async response => {
    const url = response.url()
    if (url.includes('/api/')) {
      const status = response.status()
      let body = ''
      try {
        body = await response.text()
      } catch {}
      requests.push(`${status} ${url}: ${body.substring(0, 200)}`)
    }
  })
  
  // Go to login page
  await page.goto('/login')
  await page.waitForLoadState('networkidle')
  await page.waitForTimeout(2000)
  
  // Step 1: Enter username
  const usernameInput = page.locator('input:visible').first()
  await usernameInput.click()
  await usernameInput.type(config.credentials.username)
  
  // Click Continue button
  await page.locator('button:has-text("Continue")').click()
  await page.waitForTimeout(2000)
  
  // Step 2: Check if WebAuthn is shown (user has security keys), click Password link
  // Wait for WebAuthn prompt to appear
  await page.waitForTimeout(3000)
  
  // Click on Password option to switch to password auth
  const passwordLink = page.getByText('Password', { exact: true })
  try {
    await passwordLink.waitFor({ state: 'visible', timeout: 5000 })
    await passwordLink.click()
    await page.waitForTimeout(2000)
  } catch {
    // Password link might not be visible if WebAuthn not available
    console.log('No WebAuthn prompt, proceeding with password')
  }
  
  // Step 3: Enter password
  const passwordInput = page.locator('input[placeholder="Enter your password"]')
  await passwordInput.waitFor({ state: 'visible', timeout: 10000 })
  await passwordInput.click()
  // Type slowly to let React pick up each char
  await page.keyboard.type(config.credentials.password, { delay: 50 })
  
  // Debug: screenshot before clicking Sign In
  await page.screenshot({ path: 'e2e/debug-before-signin.png' })
  
  // Click Sign In button
  await page.locator('button:has-text("Sign In")').click()
  await page.waitForTimeout(3000)
  
  // Debug: screenshot after clicking Sign In
  await page.screenshot({ path: 'e2e/debug-after-signin.png' })
  
  // Wait for dashboard or show what happened
  const currentUrl = page.url()
  if (!currentUrl.includes('dashboard')) {
    console.log('API Requests:', requests.join('\n'))
    throw new Error(`Login failed - current URL: ${currentUrl}\nAPI Requests:\n${requests.join('\n')}`)
  }
  
  // Verify we're logged in
  await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible({ timeout: 10000 })
  
  // Save authentication state
  await page.context().storageState({ path: authFile })
})
