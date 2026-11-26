"""Run every chaos script and print a scoreboard.

Run:  python -m scripts.chaos.run_all
Needs the API on port 8000 (01_crash and connections start their own servers).
"""
import subprocess
import sys

SCRIPTS = [
    ("step 1 · crash in the middle", "01_crash"),
    ("step 2 · concurrent transfers", "02_concurrency"),
    ("step 4 · too many connections", "connections"),
    ("step 5 · duplicate on retry", "duplicate"),
]

board = []
for label, module in SCRIPTS:
    code = subprocess.run([sys.executable, "-m", f"scripts.chaos.{module}"]).returncode
    board.append((label, "PASS" if code == 0 else "FAIL"))

print("\n========= scoreboard")
for label, result in board:
    print(f"  {result}  {label}")
