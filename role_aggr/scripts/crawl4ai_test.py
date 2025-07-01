import asyncio
from crawl4ai import *

TARGET_URL = "https://barclays.wd3.myworkdayjobs.com/en-US/External_Career_Site_Barclays"


async def main():
    browser_config = BrowserConfig(headless=True)
    run_config = CrawlerRunConfig(
                    word_count_threshold=10,        # Minimum words per content block
                    exclude_external_links=True,    # Remove external links
                    remove_overlay_elements=True,   # Remove popups/modals
                    process_iframes=True)           # Process iframe content
    
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=TARGET_URL, 
                                    run_config=run_config)
        print(result.markdown)


async def simple_example_with_css_selector():
    print("\n--- Using CSS Selectors ---")
    browser_config = BrowserConfig(headless=True)
    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS, css_selector="[data-automation-id='jobResults']"
    )

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=TARGET_URL, config=crawler_config
        )
        print(result.markdown[:500])


if __name__ == "__main__":
    asyncio.run(simple_example_with_css_selector())