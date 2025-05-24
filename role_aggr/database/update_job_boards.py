import os
import sys

_current_file_dir = os.path.dirname(os.path.abspath(__file__))
_project_root_alt = os.path.abspath(os.path.join(_current_file_dir, '..','..'))
if _project_root_alt not in sys.path:
    sys.path.insert(0, _project_root_alt)

from role_aggr.database.functions import init_db, update_job_boards
from role_aggr.database.model import SessionLocal

if __name__ == "__main__":
    init_db()
    update_job_boards()
