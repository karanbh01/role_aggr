import requests
from bs4 import BeautifulSoup
import json
import re

def get_user_agent():
    """Return a user agent to avoid being blocked"""
    return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

def examine_deutsche_bank():
    url = "https://db.wd3.myworkdayjobs.com/en-US/DBWebsite?Country=29247e57dbaf46fb855b224e03170bc7"
    headers = {'User-Agent': get_user_agent()}
    
    print(f"Fetching Deutsche Bank job board: {url}")
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"Failed to fetch the page: {response.status_code}")
        return
    
    print("Successfully fetched the page")
    
    # Save the HTML for inspection
    with open("deutsche_bank_page.html", "w", encoding="utf-8") as f:
        f.write(response.text)
    
    # Parse the HTML
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Print the title of the page to confirm we got the right page
    title = soup.title.text if soup.title else "No title found"
    print(f"Page title: {title}")
    
    # Look for common job listing elements in Workday sites
    print("\nSearching for job listings...")
    
    # Try different selectors that might contain job listings
    selectors = [
        'li.css-1q2dra3',  # Our current selector
        'ul.css-1mos5t',    # Common Workday job list
        'div[data-automation-id="jobResults"]',  # Job results container
        'li[data-automation-id="jobSearchResult"]',  # Individual job result
        'a[data-automation-id="jobTitle"]',  # Job title links
    ]
    
    for selector in selectors:
        elements = soup.select(selector)
        print(f"Selector '{selector}': {len(elements)} elements found")
        
        # Print details of first few elements if found
        for i, element in enumerate(elements[:3]):
            print(f"\nElement {i+1}:")
            print(f"HTML: {element}")
            
            # Try to extract job title
            title_element = element.select_one('a') or element
            print(f"Possible title: {title_element.text.strip() if title_element else 'None'}")
    
    # Check if there's any JSON data embedded in the page (common in modern job boards)
    print("\nLooking for embedded JSON data...")
    scripts = soup.find_all('script')
    for script in scripts:
        script_text = script.string
        if script_text and 'jobPostings' in script_text:
            print("Found script with jobPostings!")
            # Try to extract the JSON
            try:
                json_match = re.search(r'window\.\_(\w+)\s*=\s*({.*})', script_text, re.DOTALL)
                if json_match:
                    print("Found JSON data in script")
                    # We'd parse this JSON to extract job listings
            except Exception as e:
                print(f"Error parsing JSON: {e}")
    
    # Check for AJAX requests
    print("\nThe page might load job listings via AJAX. Check the Network tab in browser dev tools.")
    print("Look for XHR requests after the page loads.")

if __name__ == "__main__":
    examine_deutsche_bank()