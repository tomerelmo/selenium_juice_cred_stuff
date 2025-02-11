import re
import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException, StaleElementReferenceException
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
# No ActionChains needed

class JuiceShopCredentialChecker:
    """
    Credential checker for OWASP Juice Shop.
    """

    def __init__(self, juice_shop_url, browser="chrome", headless=True, implicit_wait=0, explicit_wait=2, driver_path=None):  # Headless by default, lower explicit wait
        """
        Initializes the JuiceShopCredentialChecker.
        """
        self.juice_shop_url = juice_shop_url.rstrip("/") + "/#/login"
        self.implicit_wait = implicit_wait  # Set to 0
        self.explicit_wait = explicit_wait  # Reduced to 2
        self.driver = None

        if browser.lower() == "chrome":
            options = webdriver.ChromeOptions()
            options.add_argument("--headless") if headless else None  # More concise headless handling
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-popup-blocking")
            options.add_argument("--disable-notifications")  # Keep notification disabling
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            # Add these options for performance
            options.add_argument("--blink-settings=imagesEnabled=false")  # Disable images
            options.add_argument("--disable-javascript")           # Disable JavaScript *if possible* - see note below.


            try:
                if driver_path:
                    absolute_driver_path = os.path.abspath(driver_path)
                    service = ChromeService(executable_path=absolute_driver_path)
                    self.driver = webdriver.Chrome(service=service, options=options)
                else:
                    self.driver = webdriver.Chrome(options=options)
            except WebDriverException as e:
                raise WebDriverException(f"Failed to initialize Chrome driver: {e}.")

        elif browser.lower() == "firefox":
            options = webdriver.FirefoxOptions()
            if headless:
                options.add_argument("--headless")
            options.set_preference("dom.webnotifications.enabled", False)
            options.set_preference("dom.push.enabled", False)
            options.set_preference("permissions.default.image", 2)  # Disable images in Firefox
            options.set_preference("javascript.enabled", False)  # Disable JS *if possible*
            try:
                if driver_path:
                    absolute_driver_path = os.path.abspath(driver_path)
                    service = FirefoxService(executable_path=absolute_driver_path)
                    self.driver = webdriver.Firefox(service=service, options=options)
                else:
                    self.driver = webdriver.Firefox(options=options)
            except WebDriverException as e:
                raise WebDriverException(f"Failed to initialize Firefox driver: {e}.")
        else:
            raise ValueError("Invalid browser specified.")

        if self.driver:
           self.driver.implicitly_wait(self.implicit_wait) # keep it 0


    def _navigate_to_login_page(self):
      """Navigates to the login page, handles popups (faster)."""
      try:
          self.driver.get(self.juice_shop_url)

          # Handle popups with VERY short timeouts (0.5 seconds). We rely more on JS.
          try:
              # Remove Notification
              self.driver.execute_script("arguments[0].remove();", WebDriverWait(self.driver, 0.5).until(
                  EC.presence_of_element_located((By.ID, "mat-dialog-0"))
              ))
          except (TimeoutException, WebDriverException):
              pass

          try:
              # close welcome banner
              WebDriverWait(self.driver, 0.5).until(
                  EC.element_to_be_clickable((By.CSS_SELECTOR, "a[aria-label='Close Welcome Banner']"))
              ).click()
          except TimeoutException:
              pass

          try:
              # close cookie
              WebDriverWait(self.driver, 0.5).until(
                  EC.element_to_be_clickable((By.CSS_SELECTOR, "a[aria-label='dismiss cookie message'], button[id='cookieconsent:button']"))
              ).click()
          except TimeoutException:
              pass

          # If we're not on the login page, navigate (faster staleness check)
          if not self.driver.current_url.endswith("/#/login"):
                try:
                    account_button = WebDriverWait(self.driver, self.explicit_wait).until(
                         EC.element_to_be_clickable((By.ID, "navbarAccount"))
                     )
                    # Use JavaScript to click - FASTER than Selenium click()
                    self.driver.execute_script("arguments[0].click();", account_button)

                    # Staleness check is still good, but with the shorter explicit wait.
                    WebDriverWait(self.driver, self.explicit_wait).until(
                        EC.staleness_of(account_button)
                    )
                except (TimeoutException, StaleElementReferenceException):
                    self.driver.get(self.juice_shop_url) # go to login and return
                    return
                # Use JavaScript to click login button
                login_button = WebDriverWait(self.driver, self.explicit_wait).until(
                    EC.element_to_be_clickable((By.ID, "navbarLoginButton"))
                )
                self.driver.execute_script("arguments[0].click();", login_button)


          WebDriverWait(self.driver, self.explicit_wait).until(
              EC.presence_of_element_located((By.ID, "email"))
          )

      except (TimeoutException, NoSuchElementException, WebDriverException) as e:
          raise Exception(f"Failed to navigate to login page: {e}")


    def login(self, email, password):
        """Attempts to log in."""
        try:
            self._navigate_to_login_page()

            email_field = self.driver.find_element(By.ID, "email")
            password_field = self.driver.find_element(By.ID, "password")
            login_button = self.driver.find_element(By.ID, "loginButton")

            email_field.clear()
            email_field.send_keys(email)
            password_field.clear()
            password_field.send_keys(password)
            # Use JavaScript to click the login button.
            self.driver.execute_script("arguments[0].click();", login_button)

            try:
                WebDriverWait(self.driver, self.explicit_wait).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.ID, "navbarLogoutButton")),
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".error.ng-star-inserted"))
                    )
                )
                if self.driver.find_elements(By.ID, "navbarLogoutButton"):
                    return "success"
                else:
                    # Find and check error using JavaScript for speed
                    error_message = self.driver.execute_script('return document.querySelector(".error.ng-star-inserted")?.textContent;')
                    if error_message and "Invalid email or password" in error_message:
                         return "failure"
                    return "failure" # error or timeout
            except TimeoutException:
                return "failure"

        except (NoSuchElementException, TimeoutException, WebDriverException) as e:
            raise Exception(f"Error during login attempt: {e}")



    def check_credentials(self, credentials):
        """Checks a list of credentials."""
        results = {}
        for email, password in credentials:
            try:
                result = self.login(email, password)
                results[(email, password)] = result
                if result == "success": # Only logout on success
                    self.logout()
            except Exception as e:
                results[(email, password)] = f"ERROR: {e}"
        return results


    def logout(self):
        """Logs out."""
        try:
            account_button = WebDriverWait(self.driver, self.explicit_wait).until(
                EC.element_to_be_clickable((By.ID, "navbarAccount"))
            )
            # Use JavaScript to click the account button - FASTER.
            self.driver.execute_script("arguments[0].click();", account_button)

            WebDriverWait(self.driver, self.explicit_wait).until(
                EC.staleness_of(account_button)
            )
            logout_button = WebDriverWait(self.driver, self.explicit_wait).until(
                EC.element_to_be_clickable((By.ID, "navbarLogoutButton"))
            )
             # Use JavaScript to click the logout button - FASTER.
            self.driver.execute_script("arguments[0].click();", logout_button)

            WebDriverWait(self.driver, self.explicit_wait).until(
                EC.presence_of_element_located((By.ID, "navbarLoginButton"))
            )
        except (TimeoutException, NoSuchElementException, StaleElementReferenceException):
            self.driver.get(self.juice_shop_url)


    def close(self):
        """Closes the browser."""
        try:
            if self.driver:
                self.driver.quit()
        except WebDriverException as e:
            print(f"Error closing WebDriver: {e}")



def is_valid_email(email):
    """Simple email validation."""
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)


def load_credentials_from_file(filepath):
    """Loads credentials from a file."""
    credentials = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        email, password = line.split(',', 1)
                        email = email.strip()
                        password = password.strip()
                        if is_valid_email(email) and password:
                            credentials.append((email, password))
                        else:
                            print(f"Skipping invalid line: {line}")
                    except ValueError:
                        print(f"Skipping badly formatted line: {line}")
    except FileNotFoundError:
        print(f"Credentials file not found: {filepath}")
    return credentials


def main():
    # --- Configuration ---
    juice_shop_url = "https://<Your-juice-app>"
    credentials_file = "credentials.txt"
    browser_type = "chrome"
    run_headless = False  # Run headless by default for speed
    driver_path = None

    # --- Load Credentials ---
    credentials = load_credentials_from_file(credentials_file)
    if not credentials:
        print("No valid credentials found. Exiting.")
        return

    # --- Initialize and Run Checker ---
    try:
        checker = JuiceShopCredentialChecker(juice_shop_url, browser=browser_type, headless=run_headless, driver_path=driver_path)
        results = checker.check_credentials(credentials)

        # --- Print Results ---
        for (email, password), result in results.items():
            print(f"Email: {email}, Password: {password}, Result: {result}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if 'checker' in locals():
            checker.close()


if __name__ == "__main__":
    main()
