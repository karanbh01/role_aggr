from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import json

def scrape_deutsche_bank_with_selenium():
    """
    Use Selenium to scrape Deutsche Bank job listings
    """
    print("Setting up Chrome options...")
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    print("Initializing Chrome driver...")
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        url = "https://db.wd3.myworkdayjobs.com/en-US/DBWebsite?Country=29247e57dbaf46fb855b224e03170bc7"
        print(f"Navigating to {url}...")
        driver.get(url)
        
        # Wait for the page to load
        print("Waiting for page to load...")
        time.sleep(5)  # Initial wait
        
        # Wait for job listings to appear
        print("Waiting for job listings to load...")
        try:
            # Try different selectors that might indicate job listings have loaded
            selectors = [
                "div[data-automation-id='jobResults']",
                "ul.css-1mos5t",
                "li[data-automation-id='jobSearchResult']",
                "a[data-automation-id='jobTitle']"
            ]
            
            for selector in selectors:
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    print(f"Found elements with selector: {selector}")
                    break
                except:
                    print(f"No elements found with selector: {selector}")
            
            # Additional wait to ensure everything is loaded
            time.sleep(2)
            
            # Get the page source after JavaScript has executed
            page_source = driver.page_source
            
            # Save the page source for inspection
            with open("deutsche_bank_selenium.html", "w", encoding="utf-8") as f:
                f.write(page_source)
            
            print("Page source saved to deutsche_bank_selenium.html")
            
            # Try to extract job listings
            print("\nExtracting job listings...")
            
            # Try different selectors for job listings
            job_selectors = [
                "li[data-automation-id='jobSearchResult']",
                "div[data-automation-id='jobResults'] li",
                "a[data-automation-id='jobTitle']"
            ]
            
            jobs_found = False
            
            for selector in job_selectors:
                job_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if job_elements:
                    jobs_found = True
                    print(f"Found {len(job_elements)} job listings with selector: {selector}")
                    
                    # Extract details from the first few job listings
                    for i, job_element in enumerate(job_elements[:5]):
                        print(f"\nJob {i+1}:")
                        
                        # Try to extract job title
                        try:
                            title_element = job_element.find_element(By.CSS_SELECTOR, "a[data-automation-id='jobTitle']")
                            print(f"Title: {title_element.text}")
                            print(f"URL: {title_element.get_attribute('href')}")
                        except:
                            try:
                                # If the job element itself is the title link
                                if job_element.tag_name == 'a':
                                    print(f"Title: {job_element.text}")
                                    print(f"URL: {job_element.get_attribute('href')}")
                                else:
                                    print("Could not extract title")
                            except:
                                print("Could not extract title")
                        
                        # Try to extract location
                        try:
                            location_element = job_element.find_element(By.CSS_SELECTOR, "[data-automation-id='locationLabel']")
                            print(f"Location: {location_element.text}")
                        except:
                            print("Could not extract location")
                        
                        # Try to extract posted date
                        try:
                            date_element = job_element.find_element(By.CSS_SELECTOR, "[data-automation-id='postedOn']")
                            print(f"Posted: {date_element.text}")
                        except:
                            print("Could not extract posted date")
                    
                    break
            
            if not jobs_found:
                print("No job listings found with any selector")
                
                # Check if there's a "No results found" message
                try:
                    no_results = driver.find_element(By.CSS_SELECTOR, "[data-automation-id='noResultsFound']")
                    print(f"No results message found: {no_results.text}")
                except:
                    print("No 'No results found' message detected")
            
            # Capture a screenshot for visual inspection
            driver.save_screenshot("deutsche_bank_screenshot.png")
            print("Screenshot saved to deutsche_bank_screenshot.png")
            
        except Exception as e:
            print(f"Error waiting for job listings: {str(e)}")
        
    finally:
        print("Closing browser...")
        driver.quit()

if __name__ == "__main__":
    print("Starting Deutsche Bank scraping with Selenium...")
    scrape_deutsche_bank_with_selenium()
    print("Done!")