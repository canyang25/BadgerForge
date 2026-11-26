import json
import os
from lg_agent.models import RunMetadata

LOG_FILE = ".okf/logs.jsonl"
RUNS_DIR = ".okf/runs"

def log_run(metadata: RunMetadata):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    os.makedirs(RUNS_DIR, exist_ok=True)
    
    # 1. Append to JSONL
    # Pydantic's model_dump_json takes care of datetime serialization
    log_entry = metadata.model_dump_json()
    with open(LOG_FILE, "a") as f:
        f.write(log_entry + "\n")
        
    # 2. Generate a Markdown report for easy viewing in VS Code
    md_path = os.path.join(RUNS_DIR, f"{metadata.run_id}.md")
    with open(md_path, "w") as f:
        f.write(f"# Run Report: {metadata.test_name}\n\n")
        f.write(f"- **Run ID:** `{metadata.run_id}`\n")
        f.write(f"- **Timestamp:** {metadata.timestamp}\n")
        f.write(f"- **Status:** `{metadata.final_status}`\n")
        f.write(f"- **Execution Time:** {metadata.execution_time_sec:.2f}s\n")
        f.write(f"- **Tokens:** {metadata.total_input_tokens} In / {metadata.total_output_tokens} Out\n\n")
        
        f.write("## Trajectory\n\n")
        for i, msg in enumerate(metadata.trajectory):
            mtype = msg.get('type', 'Message')
            f.write(f"### Step {i+1}: {mtype}\n")
            
            content = msg.get('content')
            if content:
                f.write(f"```text\n{content.strip()}\n```\n\n")
                
            tool_calls = msg.get('tool_calls')
            if tool_calls:
                f.write("**Tool Calls:**\n")
                for tc in tool_calls:
                    f.write(f"- `{tc.get('name')}`: `{tc.get('args')}`\n")
                f.write("\n")
            f.write("---\n\n")

