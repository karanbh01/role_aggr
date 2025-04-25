import os
from dotenv import load_dotenv

load_dotenv()

WORKSPACE_ROOT = os.path.dirname(os.path.abspath(__file__))
DATABASE_DIR = os.path.join(WORKSPACE_ROOT, 'database')

DATABASE_FILE = os.path.join(DATABASE_DIR, 'job_database.db')
CSV_FILE_PATH = os.path.join(WORKSPACE_ROOT, 'job_boards.csv')
