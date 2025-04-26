# Job Aggregator Web App

A simple Python web application that aggregates job listings from various job boards.

## Features

- Scrapes job listings from multiple job boards (excluding LinkedIn and Indeed)
- Displays job title, company, and date posted for each listing
- Clicking on a listing navigates to the original job board posting
- Dark-themed user interface
- Caching system to avoid scraping on every request

## Requirements

- Python 3.8 or higher
- Flask
- Requests
- BeautifulSoup4

## Installation

1. Clone this repository or download the files
2. Navigate to the project directory
3. Install the required dependencies:

```bash
pip install -r requirements.txt
```

## Usage

1. Make sure the `job_boards.csv` file is in the project directory
2. Run the Flask application:

```bash
python app.py
```

3. Open your web browser and navigate to `http://127.0.0.1:5000/`

## Refreshing Job Listings

- Click the "Refresh Listings" button on the web app to force a refresh of the job listings
- Job listings are cached for 1 hour by default to avoid excessive scraping

## Customization

- To add or remove job boards, edit the `job_boards.csv` file
- To modify the appearance, edit the CSS in `static/css/style.css`
- To change the caching duration, modify the `CACHE_EXPIRY` variable in `app.py`

## Notes

- The scraper may not work for all job boards due to different HTML structures
- Some job boards may block scraping attempts
- The application includes basic error handling for scraping failures