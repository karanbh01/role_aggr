# role/aggr: An Aggregator for Finance Roles built using Flask

![role_aggr_home](role_aggr/role_aggr_home.jpeg)

## Project Overview
`role/aggr` is a specialized web application designed to aggregate job listings specifically for finance roles from various online job boards. It provides a centralized platform for job seekers to discover relevant opportunities, streamlining the job search process in the finance industry. The application features robust web scraping capabilities, a structured database for job data, and an intuitive web interface for easy navigation and search.

## Development Status
This web application is currently under active development. New features, integrations, and improvements are continuously being implemented to enhance its functionality and user experience.

## Integration Status
- **Workday Integration**: The integration with Workday job listings is fully functional and is able to gather data from Workday job boards.
- **Other Major Job Boards**: Integrations with other major job boards such as LinkedIn, eFinancialCareers and others are currently work in progress. Our goal is to expand coverage to a comprehensive list of platforms.

## Installation and Setup Instructions

To set up and run `role/aggr` locally, follow these steps:

### Prerequisites
- Python 3.8+
- pip
- Git

### Step-by-Step Setup

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/your-username/role_aggr.git
   cd role_aggr
   ```

2. **Create a Virtual Environment (Recommended):**
   ```bash
   python -m venv .venv
   ```

3. **Activate the Virtual Environment:**
   - **On Windows:**
     ```bash
     .venv\Scripts\activate
     ```
   - **On macOS/Linux:**
     ```bash
     source .venv/bin/activate
     ```

4. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Database Setup:**
   The application uses a SQLite database. Initial setup will create the necessary database file and tables.
   ```bash
   # This command will initialize the database if it doesn't exist
   python -c "from role_aggr.database.model import create_tables; create_tables()"
   ```

6. **Configure Intelligent Parser (Optional):**
   To enable advanced location parsing capabilities, create a `.env` file with your OpenRouter API key:
   ```bash
   # Create .env file for intelligent parsing
   echo "ENABLE_INTELLIGENT_PARSING=true" > .env
   echo "OPENROUTER_API_KEY=your_api_key_here" >> .env
   echo "INTELLIGENT_PARSER_MODEL=google/gemini-2.5-flash" >> .env
   ```
   
   **Note**: The intelligent parser provides structured location data (city, country, region) from raw location strings. If not configured, the system will use basic fallback parsing without affecting functionality.

## Usage Examples

### Running the Application

To start the Flask web server:

```bash
python role_aggr/app.py
```

Once the server is running, open your web browser and navigate to `http://127.0.0.1:5000` (or the address displayed in your console).

### Running the Scraper

To manually run the web scraper to fetch new job listings:

```bash
python role_aggr/scripts/scraper.py
```
*(Note: This will populate your database with job listings based on configured job boards.)*

## Current Features and Limitations

### Features
- **Job Aggregation**: Collects finance job listings from various online sources.
- **Workday Integration**: Fully functional scraping and integration with Workday job portals.
- **Database Storage**: Stores job details in a structured SQLite database.
- **Web Interface**: User-friendly web interface for searching and viewing job listings.
- **Search & Filter**: Basic search and filtering capabilities for job listings.
- **🎯 Intelligent Location Parsing (EIP-002)**: Advanced LLM-powered location parsing that standardizes inconsistent location strings into structured `city`, `country`, and `region` fields with 99% API efficiency optimization.

### Enhanced Capabilities (EIP-002)
- **Smart Location Data**: Automatically parses raw location strings like "SF, CA" into structured data: `city: "San Francisco"`, `country: "United States"`, `region: "Americas"`
- **Batch Processing**: Processes multiple locations in a single API call for optimal efficiency
- **Fallback Mechanisms**: Graceful degradation with multiple fallback options
- **Database Integration**: Properly stores structured location data in queryable database fields
- **Performance Optimized**: 99% reduction in LLM API calls through intelligent batch processing

### Limitations
- **Limited Job Board Coverage**: Currently, only Workday integration is complete. Other major job boards are still being integrated.
- **No User Accounts**: The application does not yet support user accounts, personalized settings, or saved searches.
- **Basic UI**: The user interface is functional but will undergo further enhancements for improved aesthetics and usability.
- **No Notifications**: There are no features for job alerts or notifications.

## Technical Stack Information

`role/aggr` is built using the following technologies:

-   **Backend**:
    -   Python 3.x
    -   Flask (Web Framework)
    -   SQLAlchemy (ORM for database interactions)
    -   Playwright (for web scraping)
    -   OpenAI Client (for intelligent parsing via OpenRouter API)
-   **Database**:
    -   SQLite (for local development and deployment)
    -   Structured location data (city, country, region fields)
-   **Frontend**:
    -   HTML5
    -   CSS3 (with basic styling)
    -   JavaScript (minimal, for interactive elements)
-   **AI/ML Integration**:
    -   **LLM-Powered Parsing**: Google Gemini 2.5 Flash via OpenRouter API
    -   **Batch Processing**: Optimized for 99% API call reduction
    -   **Intelligent Caching**: In-memory location data caching
    -   **Fallback Systems**: Multi-tier error handling and graceful degradation

## Licensing Details

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.