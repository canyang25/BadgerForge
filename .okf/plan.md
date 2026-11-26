# Agent Improvement Plan

Based on the analysis of the `cancel-async-tasks` run (`257a280f-7033-405c-af60-219556296830`), the agent failed because it hit the `max_turns_reached` limit prematurely. While attempting to comprehensively solve the task, it ran out of cycles before calling `FinishTask`.

## 1. Core Issue: Severe Turn Limit Constraint
The agent hit a hard cap of `MAX_TURNS=10`. In the baseline agent provided by the starter code, the default is `100`. Complex reasoning tasks, especially those requiring empirical testing (like the agent correctly did in Steps 9-11), require significantly more than 10 turns.
- **Action:** Increase the default `MAX_TURNS` in `lg_agent/agent.py` from 10 to at least 100, aligning it with the competition baseline.

## 2. Behavioral Issue: Lack of Proper Self-Correction and Verification
The agent wrote an initial implementation (Step 7) but immediately realized it was flawed (Step 9). It then pivoted to writing exploratory test scripts (`/tmp/test_cancel.py`). This is excellent behavior, but because it lacked a structural mechanism to "plan" its workflow, it burned precious turns.
- **Action:** Introduce a clear "Plan -> Act -> Verify" loop in the system prompt. Give the agent a dedicated `Plan` tool or encourage it to write a `plan.md` inside the container before executing code.

## 3. Tool Deficiencies
The agent currently only has `ExecuteCommand` and `FinishTask`.
In Step 7, it wrote the entire Python file using `cat > /app/run.py << 'PYEOF'`. This approach is brittle and prone to escaping errors or truncation issues (as seen by the `[truncated]` marker in the logs, though it succeeded here).
- **Action:** Implement higher-level, dedicated file manipulation tools within the LangGraph structure:
  - `WriteFile(filepath, content)`
  - `ReadFile(filepath, start_line, end_line)`
  - `ReplaceInFile(filepath, old_text, new_text)`

## 4. Context Window Management
The agent's trajectory accumulates full terminal outputs, including the verbose Docker Compose warning (`>>>> Executing external compose provider...`). Over many turns, this will pollute the context window and dilute the model's focus.
- **Action:** Add a context summarizer or a reducer in `lg_agent/graph.py`. Before appending `ToolMessage`, we should strip out known noisy headers (like Docker Compose warnings) and truncate standard output if it exceeds a reasonable length (e.g., 2000 chars), storing the full output only if requested by the agent.

## Summary of Next Steps
1. **Immediate Fix:** Change `AGENT_MAX_TURNS` default to 100.
2. **Short Term:** Add explicit File I/O tools to `lg_agent/graph.py`.
3. **Medium Term:** Implement output sanitization and context window summarization.
