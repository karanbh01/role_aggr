from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

def examine_aviva_job_date():
    """
    Examine the Aviva job posting to find the date information
    """
    url = "https://aviva.wd1.myworkdayjobs.com/en-US/Aviva_Investors_External/job/London-UK/Model-Validation-Analyst---London_R-151944?locations=ffa161f517d11024fc25a8572b00e1c0"
    
    print(f"Examining Aviva job posting: {url}")
    
    # Set up Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    # Initialize Chrome driver
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        # Navigate to the job posting URL
        driver.get(url)
        
        # Wait for the page to load
        print("Waiting for page to load...")
        time.sleep(5)
        
        # Save the page source for inspection
        with open("aviva_job_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        
        print("Page source saved to aviva_job_page.html")
        
        # Take a screenshot
        driver.save_screenshot("aviva_job_screenshot.png")
        print("Screenshot saved to aviva_job_screenshot.png")
        
        # Look for date information using various selectors
        print("\nSearching for date information...")
        
        # Common date selectors in Workday job postings
        date_selectors = [
            "[data-automation-id='postedOn']",
            "[data-automation-id='datePosted']",
            "[data-automation-id='jobPostingDate']",
            "[data-automation-id='jobDate']",
            ".jobPostingDate",
            ".postedDate",
            ".job-date",
            ".posted-date",
            "time",
            "[datetime]",
            # More general selectors that might contain date information
            "span:contains('Posted')",
            "div:contains('Posted')",
            "span:contains('Date')",
            "div:contains('Date')"
        ]
        
        for selector in date_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    print(f"Found {len(elements)} elements with selector: {selector}")
                    for i, element in enumerate(elements):
                        print(f"  Element {i+1} text: {element.text}")
                        print(f"  Element {i+1} HTML: {element.get_attribute('outerHTML')}")
            except Exception as e:
                print(f"Error with selector {selector}: {str(e)}")
        
        # Try to find any element containing date-related text
        print("\nSearching for elements containing date-related text...")
        page_text = driver.page_source.lower()
        date_keywords = ["posted", "date", "published"]
        
        for keyword in date_keywords:
            if keyword in page_text:
                print(f"Found keyword '{keyword}' in page text")
                
                # Try to find elements containing this keyword
                try:
                    # Use XPath to find elements containing the keyword
                    xpath = f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{keyword}')]"
                    elements = driver.find_elements(By.XPATH, xpath)
                    
                    if elements:
                        print(f"Found {len(elements)} elements containing '{keyword}':")
                        for i, element in enumerate(elements[:5]):  # Limit to first 5 to avoid too much output
                            print(f"  Element {i+1} text: {element.text}")
                            print(f"  Element {i+1} HTML: {element.get_attribute('outerHTML')}")
                except Exception as e:
                    print(f"Error searching for elements with keyword {keyword}: {str(e)}")
        
        # Look for any elements with date attributes
        print("\nSearching for elements with date attributes...")
        date_attributes = ["datetime", "date", "dateTime", "datePosted", "publishedDate"]
        
        for attr in date_attributes:
            try:
                # Use XPath to find elements with the attribute
                xpath = f"//*[@{attr}]"
                elements = driver.find_elements(By.XPATH, xpath)
                
                if elements:
                    print(f"Found {len(elements)} elements with attribute '{attr}':")
                    for i, element in enumerate(elements[:5]):  # Limit to first 5
                        print(f"  Element {i+1} attribute value: {element.get_attribute(attr)}")
                        print(f"  Element {i+1} text: {element.text}")
                        print(f"  Element {i+1} HTML: {element.get_attribute('outerHTML')}")
            except Exception as e:
                print(f"Error searching for elements with attribute {attr}: {str(e)}")
        
        # Look for structured data in the page
        print("\nSearching for structured data (JSON-LD)...")
        try:
            script_elements = driver.find_elements(By.XPATH, "//script[@type='application/ld+json']")
            for i, script in enumerate(script_elements):
                print(f"JSON-LD Script {i+1}: {script.get_attribute('textContent')}")
        except Exception as e:
            print(f"Error searching for JSON-LD: {str(e)}")
        
    finally:
        # Close the browser
        driver.quit()
        print("Browser closed")

if __name__ == "__main__":
    examine_aviva_job_date()