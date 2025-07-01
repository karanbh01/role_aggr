import os
from typing import Optional

# Concurrency settings
JOB_DETAIL_CONCURRENCY = 10

# Feature flag constants
ENABLE_INTELLIGENT_PARSING = os.getenv("ENABLE_INTELLIGENT_PARSING")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
INTELLIGENT_PARSER_LLM = os.getenv("INTELLIGENT_PARSER_LLM")