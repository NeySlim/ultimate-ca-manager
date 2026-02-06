#!/usr/bin/env python3
"""
Screenshot generator for UCM documentation
"""
import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE_URL = "https://localhost:8443"
OUTPUT_DIR = "/root/ucm-src-pro/docs/screenshots"
CREDENTIALS = {"username": "admin", "password": "changeme123"}

# Pages to screenshot
PAGES = [
    ("login", "/login", False),
    ("dashboard", "/", True),
    ("certificates", "/certificates", True),
    ("cas", "/cas", True),
    ("csrs", "/csrs", True),
    ("templates", "/templates", True),
    ("users", "/users", True),
    ("settings", "/settings", True),
    ("acme", "/acme", True),
    ("scep", "/scep", True),
    ("crl-ocsp", "/crl-ocsp", True),
    ("truststore", "/truststore", True),
    ("import-export", "/import-export", True),
    ("audit-logs", "/audit-logs", True),
    # Pro pages
    ("groups", "/groups", True),
    ("rbac", "/rbac", True),
    ("sso", "/sso", True),
    ("hsm", "/hsm", True),
]

def setup_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--ignore-certificate-errors")
    options.binary_location = "/usr/bin/chromium"
    
    driver = webdriver.Chrome(options=options)
    return driver

def login(driver):
    driver.get(f"{BASE_URL}/login")
    time.sleep(2)
    
    # Step 1: Enter username
    try:
        # Find the input element (could be in different forms)
        username_input = driver.find_element(By.CSS_SELECTOR, "input[type='text']")
        username_input.clear()
        username_input.send_keys(CREDENTIALS["username"])
        
        # Click continue button
        continue_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        continue_btn.click()
        time.sleep(1.5)
    except Exception as e:
        print(f"Step 1 error: {e}")
    
    # Step 2: Enter password
    try:
        password_input = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
        password_input.send_keys(CREDENTIALS["password"])
        
        # Click sign in button
        signin_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        signin_btn.click()
        time.sleep(2)
        print("✓ Logged in")
    except Exception as e:
        print(f"Step 2 error: {e}")

def take_screenshot(driver, name, path, needs_auth):
    try:
        driver.get(f"{BASE_URL}{path}")
        time.sleep(1.5)  # Wait for page load
        
        filepath = os.path.join(OUTPUT_DIR, f"{name}.png")
        driver.save_screenshot(filepath)
        print(f"✓ {name}.png")
        return True
    except Exception as e:
        print(f"✗ {name}: {e}")
        return False

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    driver = setup_driver()
    
    try:
        # Take login screenshot first (before auth)
        take_screenshot(driver, "login", "/login", False)
        
        # Login
        login(driver)
        
        # Take screenshots of all pages
        for name, path, needs_auth in PAGES:
            if name == "login":
                continue
            take_screenshot(driver, name, path, needs_auth)
        
        print(f"\n✅ Screenshots saved to {OUTPUT_DIR}")
        
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
