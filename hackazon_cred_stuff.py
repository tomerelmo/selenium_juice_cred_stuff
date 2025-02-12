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

class HackazonCredentialChecker:
    """
    Credential checker for a Hackazon vulnerable application.
    """

    def __init__(self, hackazon_url, browser="chrome", headless=True, implicit_wait=0, explicit_wait=5, driver_path=None):
        """
        Initializes the HackazonCredentialChecker.

        Args:
            hackazon_url (str): The base URL of the Hackazon application.
            browser (str, optional): The browser to use ('chrome' or 'firefox'). Defaults to "chrome".
            headless (bool, optional): Whether to run the browser in headless mode. Defaults to True.
            implicit_wait (int, optional): Implicit wait time in seconds. Defaults to 0.
            explicit_wait (int, optional): Explicit wait time in seconds. Defaults to 5.
            driver_path (str, optional):  Path to the WebDriver executable (e.g., chromedriver, geckodriver).
                                         If None, attempts to use the system PATH.
        """

        self.hackazon_url = hackazon_url.rstrip("/")  # Remove trailing slash if present
        self.login_url = self.hackazon_url + "/user/login" #  Construct login URL
        self.implicit_wait = implicit_wait
        self.explicit_wait = explicit_wait
        self.driver = None

        if browser.lower() == "chrome":
            options = webdriver.ChromeOptions()
            options.add_argument("--headless") if headless else None
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-popup-blocking")
             # Disable images (performance)
            options.add_argument("--blink-settings=imagesEnabled=false")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)


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
            options.set_preference("dom.webnotifications.enabled", False)  # Disable notifications
            options.set_preference("dom.push.enabled", False) # Disable push notifications
            options.set_preference("permissions.default.image", 2)  # Disable images
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
            raise ValueError("Invalid browser specified.  Choose 'chrome' or 'firefox'.")

        if self.driver:
             self.driver.implicitly_wait(self.implicit_wait)



    def _navigate_to_login_page(self):
        """Navigates to the login page."""
        try:
            self.driver.get(self.hackazon_url)

             # Close initial popup (if present) - Use a short timeout
            try:
                close_button = WebDriverWait(self.driver, 1).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "a.close, button.close"))
                )
                close_button.click() # Try regular click first.
            except (TimeoutException, NoSuchElementException):
                pass # It's okay if the popup isn't there

             # Click the "Sign In / Sign Up" link (using more robust locator)
            try:
                login_link = WebDriverWait(self.driver, self.explicit_wait).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "a.login-window, li.hw-login-item a[href*='#login-box']"))
                )
                # Use JavaScript click for reliability.
                self.driver.execute_script("arguments[0].click();", login_link)

                # Wait for the login form to appear (using ID, as provided in the HTML).
                WebDriverWait(self.driver, self.explicit_wait).until(
                    EC.presence_of_element_located((By.ID, "loginForm"))
                )
            except (TimeoutException, NoSuchElementException) as e:
                raise Exception(f"Failed to navigate to login popup: {e}")

        except WebDriverException as e:
             raise Exception(f"Failed to navigate to the initial page: {e}")


    def login(self, username, password):
        """Attempts to log in."""
        try:
            self._navigate_to_login_page()

            username_field = self.driver.find_element(By.ID, "username")
            password_field = self.driver.find_element(By.ID, "password")
            login_button = self.driver.find_element(By.ID, "loginbtn")

            username_field.clear()
            username_field.send_keys(username)
            password_field.clear()
            password_field.send_keys(password)
            # Use JavaScript to click login - more robust.
            self.driver.execute_script("arguments[0].click();", login_button)

            # Wait for *either* successful login OR an error message.
            try:
                WebDriverWait(self.driver, self.explicit_wait).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".alert.alert-success")),  # Success indicator (adjust if needed)
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".alert.alert-danger")) # Error indicator
                    )
                )
                # Check for success/failure *after* the wait.  More reliable.
                if self.driver.find_elements(By.CSS_SELECTOR, ".alert.alert-success"):
                    return "success"
                else:
                    # Look for a specific error message, if possible (increases accuracy).
                    error_message = self.driver.execute_script('return document.querySelector(".alert.alert-danger")?.textContent;')
                    if error_message:
                       return "failure"
                    else:
                        return "failure" #Some other error occurred.

            except TimeoutException:
                return "failure"  # Timed out waiting for either success or failure

        except (NoSuchElementException, TimeoutException, WebDriverException) as e:
            raise Exception(f"Error during login attempt: {e}")

    def check_credentials(self, credentials):
        """Checks a list of credentials."""
        results = {}
        for username, password in credentials:
            try:
                result = self.login(username, password)
                results[(username, password)] = result
                # No logout needed after a failure, and Hackazon doesn't have an explicit logout.
                # Instead, we re-navigate to the base URL.  This is generally better
                # for web apps without a dedicated logout button/URL.
                if result == "success":
                    self.driver.get(self.hackazon_url)  # Go back to home page
            except Exception as e:
                results[(username, password)] = f"ERROR: {e}"
        return results

    def close(self):
        """Closes the browser."""
        if self.driver:
            self.driver.quit()



def is_valid_email(email):
    """Simple email validation."""
    return re.match(r"[^@]+@[^@]+\.[^@]+", email) is not None


def load_credentials_from_file(filepath):
    """Loads credentials from a file (username,password per line)."""
    credentials = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if line and "," in line:
                    try:
                        username, password = line.split(',', 1)  # Split only on the first comma
                        username = username.strip()
                        password = password.strip()
                        if username and password:  # Basic check for empty strings
                            credentials.append((username, password))
                        else:
                            print(f"Skipping invalid line (empty username/password): {line}")
                    except ValueError:
                        print(f"Skipping badly formatted line: {line}")
    except FileNotFoundError:
        print(f"Credentials file not found: {filepath}")
    return credentials



def main():
    # --- Configuration ---
    # Get Hackazon URL from user input
    hackazon_url = input("Enter the base URL of the Hackazon application (e.g., https://securedemo.radware.net): ")

    credentials_file = "credentials.txt"  # Or get this from user input if you prefer
    browser_type = "chrome"  # Or "firefox"
    run_headless = False  # Set to False to see the browser window
    driver_path = None #  "/path/to/chromedriver"  # Or None to use PATH

    # --- Load Credentials ---
    credentials = load_credentials_from_file(credentials_file)
    if not credentials:
        print("No valid credentials found. Exiting.")
        return

    # --- Initialize and Run Checker ---
    try:
        checker = HackazonCredentialChecker(hackazon_url, browser=browser_type, headless=run_headless, driver_path=driver_path)
        results = checker.check_credentials(credentials)

        # --- Print Results ---
        for (username, password), result in results.items():
            print(f"Username: {username}, Password: {password}, Result: {result}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if 'checker' in locals():  # Check if checker was initialized
            checker.close()


if __name__ == "__main__":
    main()
