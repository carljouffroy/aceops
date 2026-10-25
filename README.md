# ACE Ops intake
Client-facing assessment intake for ACE. A client's AI receives one approved question at a time and returns answers and files.
The internal side pushes the question bundle and pulls the results. This service holds no ACE business secrets.
Run the work board with `uv run python src/board/__main__.py` (http://127.0.0.1:8790).
