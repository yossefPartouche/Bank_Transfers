"""Run every chaos script and print a scoreboard.

Run:  python -m scripts.chaos.run_all
Needs the API on port 8000 (crash.py starts its own on 8001).
"""
import subprocess
import sys

SCRIPTS = [
    ("1  lost update, sender", "lost_update_sender"),
    ("2  lost update, receiver", "lost_update_receiver"),
    ("3+4 overdraft, stale reads", "overdraft"),
    ("5  halfway states visible", "halfway_visible"),
    ("6-8 crash partway", "crash"),
    ("9  duplicate on retry", "duplicate"),
    ("10 too many connections", "connections"),
]

board = []
for label, module in SCRIPTS:
    code = subprocess.run([sys.executable, "-m", f"scripts.chaos.{module}"]).returncode
    board.append((label, "PASS" if code == 0 else "FAIL"))

print("\n========= scoreboard")
for label, result in board:
    print(f"  {result}  {label}")
