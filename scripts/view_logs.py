#!/usr/bin/env python3
import json
import sys
import argparse
import os

LOG_FILE = ".okf/logs.jsonl"

def load_logs():
    logs = []
    try:
        with open(LOG_FILE, "r") as f:
            for line in f:
                if line.strip():
                    logs.append(json.loads(line))
    except FileNotFoundError:
        pass
    return logs

def print_summary(logs):
    if not logs:
        print("No logs found. Run an evaluation first.")
        return
    
    print(f"{'Run ID':<10} | {'Timestamp':<19} | {'Task':<25} | {'Status':<15} | {'Time':<6} | {'Tokens (In/Out)'}")
    print("-" * 100)
    for log in logs:
        run_id = log.get("run_id", "unknown")[:8]
        ts = log.get("timestamp", "")[:19].replace("T", " ")
        task = log.get("test_name", "")[:25]
        status = log.get("final_status", "")[:15]
        time_sec = f"{log.get('execution_time_sec', 0):.1f}s"
        tokens = f"{log.get('total_input_tokens', 0)} / {log.get('total_output_tokens', 0)}"
        
        print(f"{run_id:<10} | {ts:<19} | {task:<25} | {status:<15} | {time_sec:<6} | {tokens}")
    
    print("\nTip: Detailed markdown reports for each run are saved in the '.okf/runs/' directory.")

def main():
    parser = argparse.ArgumentParser(description="View a high-level summary of agent runs.")
    args = parser.parse_args()
    
    # Ensure we are running from the workspace root
    workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    os.chdir(workspace_root)
    
    logs = load_logs()
    print_summary(logs)

if __name__ == "__main__":
    main()
