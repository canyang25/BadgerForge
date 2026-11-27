import operator
import os
import re
from typing import Annotated, Sequence, TypedDict, Any, Literal

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

# Define State
class GraphState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    sender: str
    next_agent: str
    finished: bool
    input_tokens: Annotated[int, operator.add]
    output_tokens: Annotated[int, operator.add]
    action_taken: bool

def create_agent_graph(environment: Any, command_timeout_sec: int = 120, model_name: str | None = None):
    base_model = model_name or "qwen3.8-27b"
    base_url = "https://llm-gw01.doit.wisc.edu/v1"
    api_key = os.environ.get("OPENAI_API_KEY", "dummy")

    llm_low = ChatOpenAI(
        model=base_model,
        base_url=base_url,
        api_key=api_key,
        timeout=300,
        max_retries=5,
        reasoning_effort="low",
        extra_body={"reasoning_effort": "low"},
    )
    llm_medium = ChatOpenAI(
        model=base_model,
        base_url=base_url,
        api_key=api_key,
        timeout=300,
        max_retries=5,
        reasoning_effort="medium",
        extra_body={"reasoning_effort": "medium"},
    )
    llm_high = ChatOpenAI(
        model=base_model,
        base_url=base_url,
        api_key=api_key,
        timeout=300,
        max_retries=5,
        reasoning_effort="medium",
        extra_body={"reasoning_effort": "medium"},
    )
    
    # Common execution tools
    class ExecuteCommand(BaseModel):
        """Execute a bash command in the terminal."""
        command: str = Field(description="The bash command to execute.", alias="cmd")

    class ReadFile(BaseModel):
        """Read the contents of a file."""
        filepath: str = Field(description="The absolute path to the file to read.", alias="path")
        offset: int | None = Field(default=None, description="Optional 1-based start line number.")
        limit: int | None = Field(default=None, description="Optional maximum number of lines to read.")

    class WriteFile(BaseModel):
        """Write content to a file, overwriting it entirely."""
        filepath: str = Field(description="The absolute path to the file to write.", alias="path")
        content: str = Field(description="The complete content to write to the file.", alias="text")

    class ReplaceInFile(BaseModel):
        """Replace an exact unique substring in a file with new content."""
        filepath: str = Field(description="The absolute path to the file to modify.", alias="path")
        old_text: str = Field(description="The exact text to find and replace.")
        new_text: str = Field(description="The new text to replace old_text with.")

    # Multi-agent coordination tools
    class FinishTask(BaseModel):
        """Call this tool when the overall task is completely finished and verified."""
        reason: str = Field(description="Why the task is finished.")

    class Delegate(BaseModel):
        """Delegate a sub-task to a specialized worker."""
        worker: Literal["Researcher", "Coder", "MediumCoder", "ExpertCoder", "Tester"] = Field(
            description="The worker to delegate to. Follow escalation & de-escalation: Coder (initial implementation/minor fixes) -> MediumCoder (debugging/first failure) -> ExpertCoder (persistent/complex failure). De-escalate back to MediumCoder or Coder when test results improve."
        )
        instructions: str = Field(description="Detailed instructions for the worker.")

    class ReportBack(BaseModel):
        """Report the results of your sub-task back to the supervisor."""
        result: str = Field(description="Summary of what you did and the outcome.")

    class TestRunPlan(BaseModel):
        """Structured plan containing test code and execution command."""
        test_script_code: str | None = Field(
            default=None,
            description="If no existing test suite exists, provide complete verification script code with assertions. This will be written to a temporary test runner and executed."
        )
        test_script_filename: str = Field(
            default="/tmp/__verify_test_runner.sh",
            description="Path for the temporary test script (e.g., /tmp/__verify_test_runner.py or /tmp/__verify_test_runner.sh)."
        )
        command: str = Field(
            default="",
            description="The shell command to execute the tests in the workspace."
        )

    def sanitize_output(output: str) -> str:
        output = re.sub(r'>>>> Executing external compose provider.*?<<<<\r?\n?', '', output)
        output = output.replace('\x1b[4m', '').replace('\x1b[0m', '') 
        if len(output) > 4000:
            output = output[:2000] + "\n\n... [OUTPUT TRUNCATED] ...\n\n" + output[-2000:]
        return output.strip()

    def prune_messages(messages: Sequence[BaseMessage], max_recent: int = 35) -> list[BaseMessage]:
        """Keep initial task instruction and safe recent history without orphaned ToolMessages."""
        if len(messages) <= max_recent + 2:
            return list(messages)
        first_msg = messages[0]
        recent = list(messages[-max_recent:])
        # Never start the recent window on an orphaned ToolMessage (causes gateway HTTP 400)
        while recent and isinstance(recent[0], ToolMessage):
            recent.pop(0)
        return [first_msg] + recent

    def create_agent_node(agent_name: str, tools: list, system_prompt: str, model_client: ChatOpenAI | None = None):
        active_llm = model_client or llm_low
        bound_llm = active_llm.bind_tools(tools)
        async def node(state: GraphState):
            sys_msg = SystemMessage(content=system_prompt)
            messages = state.get("messages", [])
            effective_messages = prune_messages(messages, max_recent=35)
            
            response = await bound_llm.ainvoke([sys_msg] + effective_messages)
            # Annotate the message with the originating agent's name for clarity
            response.name = agent_name
            
            in_tokens = 0
            out_tokens = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                in_tokens = response.usage_metadata.get("input_tokens", 0)
                out_tokens = response.usage_metadata.get("output_tokens", 0)

            has_tool_calls = hasattr(response, "tool_calls") and bool(response.tool_calls)
            return {
                "messages": [response],
                "sender": agent_name,
                "next_agent": "",
                "finished": False,
                "input_tokens": in_tokens,
                "output_tokens": out_tokens
            }
        return node

    async def tester_chain_node(state: GraphState):
        """Deterministic chain: extract/generate command -> execute in container -> evaluate results."""
        messages = state.get("messages", [])
        last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
        instructions = last_human.content if last_human else "Run tests in the workspace."
        task_instruction = messages[0].content if messages else instructions

        # Step 1: Formulate / extract the test command from instructions
        plan_prompt = (
            "You are a specialized test engineer verifying code in the workspace container.\n"
            f"Original task requirement:\n{task_instruction}\n\n"
            f"Supervisor instructions for testing:\n{instructions}\n\n"
            "Instructions:\n"
            "1. If an existing test suite or CLI verification command exists (e.g., pytest, cargo test, make test, openssl verify, service checks, CLI binary checks), prioritize running it directly.\n"
            "2. For compiled languages (C, C++, Rust, Go), include any required compilation step in `command` (e.g., `gcc -O3 -o /tmp/runner /tmp/__verify_test_runner.c && /tmp/runner`).\n"
            "3. If testing a script or library without tests, provide complete verification script code in `test_script_code`. Do NOT use bash heredocs (`<< 'EOF'`) inside `command`; the system will automatically decode and write `test_script_code` to `test_script_filename`.\n"
            "4. For non-Python tasks (shell, OpenSSL, C, daemons), use native shell commands or standalone scripts without forcing Python installation.\n"
            "5. Ensure the `command` accurately executes the test suite or custom test script."
        )
        plan_model = llm_medium.with_structured_output(TestRunPlan)
        try:
            plan: TestRunPlan = await plan_model.ainvoke([
                SystemMessage(content=plan_prompt),
                HumanMessage(content=instructions),
            ])
            target_file = plan.test_script_filename or "/tmp/__verify_test_runner.sh"
            script_code = plan.test_script_code
            if plan.command and plan.command.strip():
                cmd = plan.command.strip()
            elif target_file.endswith(".py"):
                cmd = f"python3 {target_file}"
            elif target_file.endswith(".sh"):
                cmd = f"bash {target_file}"
            else:
                cmd = f"{target_file}"
        except Exception:
            target_file = "/tmp/__verify_test_runner.sh"
            # Generic fallback: execute instructions if simple command, else check test targets
            cmd = "pytest 2>/dev/null || make test 2>/dev/null || cargo test 2>/dev/null || true"
            script_code = None

        stdout = ""
        stderr = ""
        return_code = 1
        try:
            if script_code:
                import base64
                encoded = base64.b64encode(script_code.encode("utf-8")).decode("utf-8")
                write_cmd = f"mkdir -p $(dirname '{target_file}') && echo '{encoded}' | base64 -d > '{target_file}' && chmod +x '{target_file}'"
                await environment.exec(command=write_cmd, timeout_sec=15)

            exec_result = await environment.exec(command=cmd, timeout_sec=command_timeout_sec)
            stdout = sanitize_output(exec_result.stdout or "")
            stderr = sanitize_output(exec_result.stderr or "")
            return_code = exec_result.return_code
        except Exception as e:
            stderr = f"Execution failed or timed out: {e}"
        finally:
            if script_code:
                try:
                    await environment.exec(command=f"rm -f '{target_file}'", timeout_sec=15)
                except Exception:
                    pass

        # Step 3: Synthesis / reporting
        eval_prompt = (
            f"You executed the following test command in the container:\n```bash\n{cmd}\n```\n\n"
            f"Exit Code: {return_code}\n\n"
            f"Stdout:\n{stdout}\n\n"
            f"Stderr:\n{stderr}\n\n"
            "Summarize the test outcomes for the Supervisor.\n"
            "CRITICAL RULES:\n"
            "- If Exit Code is NOT 0, the test FAILED.\n"
            "- If Exit Code is 0 and CLI validation or command output confirms successful execution, report PASSED.\n"
            "- For assertion scripts, report PASSED if all assertions passed and Exit Code is 0.\n"
            "- If failed, detail the exact failure, traceback, or missing behavior so the coder can fix it."
        )
        try:
            eval_resp = await llm_medium.ainvoke([
                SystemMessage(content="You are the Tester reporting factual test results back to the Supervisor."),
                HumanMessage(content=eval_prompt),
            ])
            summary_content = eval_resp.content
            in_tokens = getattr(eval_resp, "usage_metadata", {}).get("input_tokens", 0)
            out_tokens = getattr(eval_resp, "usage_metadata", {}).get("output_tokens", 0)
        except Exception as e:
            summary_content = f"Execution completed with exit code {return_code}. Error evaluating summary: {e}"
            in_tokens = 0
            out_tokens = 0

        report_content = (
            f"### Tester Execution Report\n"
            f"**Command executed:** `{cmd}`\n"
            f"**Exit code:** `{return_code}`\n\n"
            f"**Result Summary:**\n{summary_content}"
        )
        return {
            "messages": [AIMessage(content=report_content, name="Tester")],
            "sender": "Tester",
            "next_agent": "Supervisor",
            "finished": False,
            "input_tokens": in_tokens,
            "output_tokens": out_tokens,
        }

    async def execute_tools(state: GraphState):
        messages = state["messages"]
        last_message = messages[-1]
        
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            # No tool call, nudge the model
            return {
                "messages": [HumanMessage(content="You must call a tool. If you are a worker, call ReportBack when done. If you are the Supervisor, Delegate or FinishTask.")],
                "input_tokens": 0, "output_tokens": 0
            }

        new_messages = []
        finished = state.get("finished", False)
        next_agent = ""
        next_action_taken = state.get("action_taken", False)
        delegated_this_turn = False
        
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {})
            tool_call_id = tool_call["id"]
            
            output_str = ""
            try:
                if tool_name == "ExecuteCommand":
                    command = tool_args.get("command") or tool_args.get("cmd", "")
                    result = await environment.exec(command=command, timeout_sec=command_timeout_sec)
                    stdout = sanitize_output(result.stdout or "")
                    stderr = sanitize_output(result.stderr or "")
                    next_action_taken = True
                    output_str = f"Exit code: {result.return_code}\nStdout:\n{stdout}\nStderr:\n{stderr}"
                    
                elif tool_name == "ReadFile":
                    filepath = tool_args.get("filepath") or tool_args.get("path") or tool_args.get("file_path", "")
                    offset = tool_args.get("offset")
                    limit = tool_args.get("limit")
                    if offset is not None and limit is not None:
                        start = int(offset)
                        end = start + int(limit) - 1
                        read_cmd = f"sed -n '{start},{end}p' '{filepath}'"
                    else:
                        read_cmd = f"cat '{filepath}'"
                    result = await environment.exec(command=read_cmd, timeout_sec=15)
                    stdout = sanitize_output(result.stdout or "")
                    stderr = sanitize_output(result.stderr or "")
                    if result.return_code == 0:
                        output_str = f"Exit code: 0\nFile {filepath} contents:\n{stdout}"
                    else:
                        output_str = f"Failed to read {filepath}. Exit code: {result.return_code}\nStdout:\n{stdout}\nStderr:\n{stderr}"
                        
                elif tool_name == "WriteFile":
                    filepath = tool_args.get("filepath") or tool_args.get("path") or tool_args.get("file_path", "")
                    content = tool_args.get("content") if "content" in tool_args else tool_args.get("text", "")
                    import base64
                    encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
                    command = f"mkdir -p \"$(dirname '{filepath}')\" && echo '{encoded}' | base64 -d > '{filepath}'"
                    result = await environment.exec(command=command, timeout_sec=15)
                    next_action_taken = True
                    stdout = sanitize_output(result.stdout or "")
                    stderr = sanitize_output(result.stderr or "")
                    if result.return_code == 0:
                        output_str = f"Exit code: 0\nSuccessfully wrote to {filepath}"
                    else:
                        output_str = f"Failed to write to {filepath}. Exit code: {result.return_code}\nStdout:\n{stdout}\nStderr:\n{stderr}"
                        
                elif tool_name == "ReplaceInFile":
                    filepath = tool_args.get("filepath") or tool_args.get("path") or tool_args.get("file_path", "")
                    old_text = tool_args.get("old_text") if "old_text" in tool_args else tool_args.get("old_str", tool_args.get("target", ""))
                    new_text = tool_args.get("new_text") if "new_text" in tool_args else tool_args.get("new_str", tool_args.get("replacement", ""))
                    read_res = await environment.exec(command=f"cat '{filepath}'", timeout_sec=15)
                    if read_res.return_code != 0:
                        output_str = f"Failed to read {filepath} for replacement. Stderr: {read_res.stderr}"
                    else:
                        raw_content = re.sub(r'>>>> Executing external compose provider.*?<<<<\r?\n?', '', read_res.stdout or "")
                        match_count = raw_content.count(old_text)
                        if match_count == 0:
                            output_str = f"Error: old_text not found in {filepath}. Please verify the exact text."
                        elif match_count > 1:
                            output_str = f"Error: old_text matches {match_count} locations in {filepath}. Please include more surrounding context to make the match unique."
                        else:
                            updated_content = raw_content.replace(old_text, new_text, 1)
                            import base64
                            encoded = base64.b64encode(updated_content.encode('utf-8')).decode('utf-8')
                            write_cmd = f"mkdir -p \"$(dirname '{filepath}')\" && echo '{encoded}' | base64 -d > '{filepath}'"
                            res = await environment.exec(command=write_cmd, timeout_sec=15)
                            if res.return_code == 0:
                                next_action_taken = True
                                output_str = f"Successfully updated {filepath}"
                            else:
                                output_str = f"Failed to write updated content to {filepath}: {res.stderr}"

                elif tool_name == "FinishTask":
                    finished = True
                    output_str = "Task finished recorded."
                    
                elif tool_name == "Delegate":
                    if delegated_this_turn:
                        output_str = "Action rejected: You have already delegated a task in this turn. Delegate to only one worker at a time."
                        new_messages.append(ToolMessage(content=output_str, tool_call_id=tool_call_id, name=tool_name))
                        continue
                    delegated_this_turn = True
                    raw_worker = tool_args.get("worker", "")
                    instructions = tool_args.get("instructions", "")
                    
                    worker_map = {
                        "researcher": "Researcher",
                        "coder": "Coder",
                        "mediumcoder": "MediumCoder",
                        "medium_coder": "MediumCoder",
                        "expertcoder": "ExpertCoder",
                        "expert_coder": "ExpertCoder",
                        "tester": "Tester",
                    }
                    worker = worker_map.get(raw_worker.strip().lower(), raw_worker.strip())
                    if worker not in ["Researcher", "Coder", "MediumCoder", "ExpertCoder", "Tester"]:
                        output_str = f"Error: '{raw_worker}' is not a valid worker. You must delegate to one of: Researcher, Coder, MediumCoder, ExpertCoder, Tester."
                        new_messages.append(ToolMessage(content=output_str, tool_call_id=tool_call_id, name=tool_name))
                        continue

                    output_str = f"Successfully delegated task to {worker}."
                    next_action_taken = False # Reset for new worker
                    next_agent = worker
                    new_messages.append(ToolMessage(content=output_str, tool_call_id=tool_call_id, name=tool_name))
                    new_messages.append(HumanMessage(content=f"Message from Supervisor to {worker}:\n{instructions}\n\nYou MUST use your tools to perform this task. Do not just hallucinate results and report back without acting."))
                    continue
                    
                elif tool_name == "ReportBack":
                    result_str = tool_args.get("result", "")
                    sender = state.get("sender", "")
                    
                    # Check if an action was taken in a previous turn OR in this turn.
                    acted_in_this_batch = any(
                        m.name in ("WriteFile", "ReplaceInFile", "ExecuteCommand")
                        for m in new_messages if isinstance(m, ToolMessage)
                    )
                    has_acted = state.get("action_taken", False) or acted_in_this_batch
                    
                    if not has_acted and sender in ("Coder", "MediumCoder", "ExpertCoder"):
                        action_name = "WriteFile, ReplaceInFile, or ExecuteCommand to implement/build code changes"
                        output_str = f"Action rejected: You have NOT executed any actions yet. You MUST call {action_name} before calling ReportBack."
                        next_agent = sender
                    else:
                        output_str = f"Reported back to Supervisor from {sender}. Result: {result_str}"
                        next_action_taken = False # Reset after successful report
                        next_agent = "Supervisor"
                    
                else:
                    output_str = f"Unknown tool: {tool_name}"
            except Exception as e:
                output_str = f"Error executing {tool_name}: {e}"
                
            new_messages.append(ToolMessage(content=output_str, tool_call_id=tool_call_id, name=tool_name))
            
        # Check for analysis paralysis (endless ExecuteCommand/ReadFile loops)
        if not finished and not next_agent:
            read_only_turns = 0
            for m in reversed(state["messages"]):
                if isinstance(m, AIMessage):
                    if hasattr(m, "tool_calls") and m.tool_calls:
                        is_read_only = True
                        for tc in m.tool_calls:
                            if tc.get("name") == "ExecuteCommand":
                                cmd = tc.get("args", {}).get("command", tc.get("args", {}).get("cmd", "")).strip()
                                # Only consider it analysis if it's a basic read command
                                if not any(cmd.startswith(x) for x in ["ls", "cat", "grep", "head", "tail", "pwd", "find", "wc"]):
                                    is_read_only = False
                                    break
                            elif tc.get("name") != "ReadFile":
                                is_read_only = False
                                break
                        if is_read_only:
                            read_only_turns += 1
                        else:
                            break
                    else:
                        break
                elif isinstance(m, HumanMessage) and "SYSTEM WARNING:" in str(m.content):
                    break
            
            if read_only_turns >= 5:
                nudge_str = "SYSTEM WARNING: You are trapped in an analysis loop (5+ consecutive exploration turns). Stop executing ExecuteCommand/ReadFile. IMMEDIATELY take concrete action (WriteFile, ReplaceInFile) or call FinishTask/ReportBack/Delegate."
                new_messages.append(HumanMessage(content=nudge_str))
            
        return {
            "messages": new_messages, 
            "finished": finished,
            "next_agent": next_agent if next_agent else state.get("next_agent", ""),
            "action_taken": next_action_taken,
            "input_tokens": 0, "output_tokens": 0
        }

    def router(state: GraphState):
        if state.get("finished", False):
            return END
        
        last_message = state["messages"][-1]
        
        # AI messages route to tools (executes tools or nudges if no tools called)
        if isinstance(last_message, AIMessage):
            return "tools"

        # If next_agent was targeted by delegation or reporting, route to that worker/supervisor
        next_a = state.get("next_agent")
        if next_a and next_a in ["Supervisor", "Researcher", "Coder", "MediumCoder", "ExpertCoder", "Tester"]:
            return next_a
        
        # Nudges and warnings go back to sender
        if isinstance(last_message, HumanMessage) and isinstance(last_message.content, str):
            if last_message.content.startswith("You must call a tool") or last_message.content.startswith("SYSTEM WARNING:"):
                return state.get("sender", "Supervisor")
            
        # Tool outputs route back to sender if no next_agent was assigned
        if isinstance(last_message, ToolMessage):
            return state.get("sender", "Supervisor")
            
        return "Supervisor"

    workflow = StateGraph(GraphState)
    
    supervisor_prompt = (
        "You are the Supervisor Agent managing a software engineering task in a headless container. "
        "You coordinate specialized worker agents: Researcher, Coder, MediumCoder, ExpertCoder, and Tester.\n\n"
        "Strict Workflow & Strategy:\n"
        "1. **PLAN & RECONNAISSANCE**: On your FIRST turn, briefly state your numbered plan. Then, inspect the workspace using ExecuteCommand (`pwd && ls -la`) or delegate to Researcher to discover files, packages, and schemas BEFORE taking code actions.\n"
        "2. **SANITY-CHECK CORE TOOLS**: For tasks involving complex tools (e.g., QEMU, compilers), your FIRST action should be a minimal command to verify the tool works (e.g., `qemu-system-x86_64 --version`). If it crashes with an OS/architecture error (e.g., Rosetta unimplemented syscall), DO NOT attempt to patch binaries, recompile libraries, or use LD_PRELOAD. Report the finding and call `FinishTask` immediately. Do not waste time on broken environments.\n"
        "3. **ENVIRONMENT SETUP**: When installing system packages (e.g., via `apt-get`), NEVER run the command in the background using `&`. Always wait for package managers to finish synchronously to avoid `dpkg` lock deadlocks.\n"
        "4. **STRATEGY SELECTION**: Based on reconnaissance, choose a strategy:\n"
        "   - For **setup/DevOps tasks**, create a linear shell command plan.\n"
        "   - For **complex code generation** (e.g., writing a large JSON, a complex algorithm from scratch), plan an **iterative development loop**. Delegate to a Coder to implement a small piece, then immediately delegate to the Tester to verify that piece. Repeat for each part of the implementation. Do not try to generate the entire complex file in one step.\n"
        "5. **GROUNDING & ENVIRONMENT**: Never assume file structures or installed tools. If a command (e.g., python3, gcc) is not found, remember on Debian/Ubuntu to run `apt-get update -qq` BEFORE `apt-get install -y <pkg>`.\n"
        "6. **DAEMONS & SERVERS**: When launching background services (e.g., pypi-server, qemu), ALWAYS redirect stdout/stderr: `nohup <cmd> > /tmp/daemon.log 2>&1 &` so the shell returns immediately.\n"
        "7. **IMPLEMENTATION & VERIFICATION LOOP**:\n"
        "   - **Delegate Implementation**: Delegate to Coder (or MediumCoder for complex tasks) following your chosen strategy.\n"
        "   - **Delegate Verification**: After EVERY code modification, ALWAYS delegate to Tester to verify the fix.\n"
        "8. **HANDLING FAILURES**:\n"
        "   - **First failure**: Delegate error trace and fix instructions to MediumCoder.\n"
        "   - **Repeated failures**: Escalate to ExpertCoder with the full context.\n"
        "   - **De-escalation**: When test results improve, DE-ESCALATE back to MediumCoder or Coder.\n"
        "9. **TIME LIMIT**: You are operating under a strict time limit. Do not let yourself or workers get trapped in endless loops of Python analysis scripts or command executions. Make decisions quickly.\n"
        "10. **FINISH**: Once all tests pass and the solution is fully verified, call FinishTask.\n"
        "Do NOT call FinishTask without verified test execution unless the environment is irreparably broken."
    )
    
    researcher_prompt = (
        "You are the Researcher Agent. Your supervisor has delegated a task to you. "
        "Use ExecuteCommand (ls, grep) and ReadFile to investigate the environment. "
        "CRITICAL: Do NOT use `sed`, `head`, or `tail` to read files line-by-line. ALWAYS use the `ReadFile` tool to read file contents, as it safely handles truncation and offsets for you.\n"
        "Do NOT write custom Python or Perl scripts to mathematically model or render data. Inspect the text directly and report findings.\n"
        "If external APIs return consecutive 400/404 errors, do not guess the schema. Fallback to downloading raw data files and parsing locally.\n"
        "Do NOT write application code or run tests. "
        "When you have finished gathering information, use the ReportBack tool to summarize your findings for the supervisor."
    )
    
    coder_prompt = (
        "You are the Coder Agent. Your supervisor has delegated a task to you. "
        "You MUST use the `ReplaceInFile` or `WriteFile` tool to implement code changes. Prefer `ReplaceInFile` for targeted edits to avoid rewriting entire files. You may use ExecuteCommand for build, compilation, or package management commands.\n"
        "Guidelines:\n"
        "- Write complete, correct, production-grade code.\n"
        "- **TIME LIMIT**: You are under a strict time limit. Do NOT run endless analysis scripts. Write code quickly.\n"
        "- Do NOT write temporary Python scripts just to parse or analyze data. Inspect files directly or write the final solution.\n"
        "- Do NOT write temporary test scripts or run tests; testing is handled exclusively by the Tester agent.\n"
        "- Avoid hardcoding assumptions: inspect files and error messages carefully.\n"
        "- Preserve expected exceptions and signatures exactly without unintended wrapping.\n"
        "- In async/concurrency contexts, ensure all pending tasks complete their cleanup in `finally:` blocks before re-raising exceptions.\n"
        "- Do NOT call ReportBack without actually using WriteFile.\n"
        "- When done writing files, call ReportBack summarizing what changes you made."
    )
    
    medium_coder_prompt = (
        "You are the MediumCoder Agent equipped with medium reasoning capabilities. Your supervisor has delegated a test failure or code fix to you.\n"
        "You MUST use the `ReplaceInFile` or `WriteFile` tool to implement code changes. Prefer `ReplaceInFile` for targeted edits to avoid rewriting entire files. You may use ExecuteCommand for build, compilation, or package management commands.\n"
        "Guidelines:\n"
        "- Do NOT write temporary test scripts; testing is handled exclusively by Tester.\n"
        "- **TIME LIMIT**: You are under a strict time limit. Do NOT get trapped in endless loops of `ExecuteCommand`. Write your solution quickly.\n"
        "- Analyze the failure traceback, test outputs, and existing code carefully before modifying files.\n"
        "- Look for subtle edge cases: exception handling, resource cleanup, boundary conditions, and type invariants.\n"
        "- Do NOT swallow or wrap raw exceptions unless explicitly specified by the interface.\n"
        "- When done writing files, call ReportBack summarizing what caused the bug and how you resolved it."
    )
    
    expert_coder_prompt = (
        "You are the ExpertCoder Agent equipped with deep reasoning capabilities. Your supervisor has escalated a persistent bug or complex algorithmic problem to you after earlier attempts failed.\n"
        "You MUST use the `ReplaceInFile` or `WriteFile` tool to implement code changes. Prefer `ReplaceInFile` for targeted edits to avoid rewriting entire files. You may use ExecuteCommand for build, compilation, or package management commands.\n"
        "Guidelines:\n"
        "- **CRITICAL: Thoroughly plan your changes BEFORE acting, but DO NOT get trapped in endless `ExecuteCommand` loops. Write your plan in your message, then immediately use `WriteFile` or `ReplaceInFile`. You are on a strict time limit.**\n"
        "- Do NOT write temporary Python scripts just to parse or analyze data. Write the final solution directly.\n"
        "- Do NOT write temporary test scripts; testing is handled exclusively by the Tester agent.\n"
        "- When fixing legacy C/C++ compilation errors, prefer overriding Makefile flags (e.g., `-std=c++11`) over patching system-wide headers.\n"
        "- Carefully analyze the problem, failure trace, and edge cases (especially concurrency invariants, async cleanup, signals, or compiler constraints) in your plan.\n"
        "- Ensure atomic operations, strict lifecycle management, and accurate signal/exception propagation.\n"
        "- Write clean, production-grade, bug-free implementations that account for edge cases.\n"
        "- Do NOT call ReportBack without actually using WriteFile, ReplaceInFile, or ExecuteCommand.\n"
        "- When done writing files, call ReportBack summarizing your analysis and the changes made."
    )
    
    tester_prompt = (
        "You are the Tester Agent. Your supervisor has delegated a task to you. "
        "You MUST use the ExecuteCommand tool to run tests (e.g., python scripts or pytest) in the container terminal.\n"
        "Rules:\n"
        "- You DO NOT know test results until you run ExecuteCommand. NEVER call ReportBack before running ExecuteCommand.\n"
        "- Test both standard operation and edge cases (boundary conditions, error handling, and resource cleanup).\n"
        "- NEVER loosen or modify test assertions to mask a failure. If an assertion fails, report the exact failure and traceback back to Supervisor so the bug can be escalated.\n"
        "- Once testing finishes, remove any temporary test scripts before calling ReportBack."
    )

    workflow.add_node("Supervisor", create_agent_node("Supervisor", [Delegate, ExecuteCommand, ReadFile, FinishTask], supervisor_prompt))
    workflow.add_node("Researcher", create_agent_node("Researcher", [ExecuteCommand, ReadFile, ReportBack], researcher_prompt))
    workflow.add_node("Coder", create_agent_node("Coder", [WriteFile, ReplaceInFile, ReadFile, ExecuteCommand, ReportBack], coder_prompt))
    workflow.add_node("MediumCoder", create_agent_node("MediumCoder", [WriteFile, ReplaceInFile, ReadFile, ExecuteCommand, ReportBack], medium_coder_prompt, model_client=llm_medium))
    workflow.add_node("ExpertCoder", create_agent_node("ExpertCoder", [WriteFile, ReplaceInFile, ReadFile, ExecuteCommand, ReportBack], expert_coder_prompt, model_client=llm_high))
    workflow.add_node("Tester", tester_chain_node)
    workflow.add_node("tools", execute_tools)

    routing_targets = {
        "tools": "tools",
        "Supervisor": "Supervisor",
        "Researcher": "Researcher",
        "Coder": "Coder",
        "MediumCoder": "MediumCoder",
        "ExpertCoder": "ExpertCoder",
        "Tester": "Tester",
        END: END,
    }

    for node in ["Supervisor", "Researcher", "Coder", "MediumCoder", "ExpertCoder"]:
        workflow.add_conditional_edges(node, router, routing_targets)

    workflow.add_edge("Tester", "Supervisor")
    workflow.add_conditional_edges(
        "tools",
        router,
        {"Supervisor": "Supervisor", "Researcher": "Researcher", "Coder": "Coder", "MediumCoder": "MediumCoder", "ExpertCoder": "ExpertCoder", "Tester": "Tester", END: END},
    )

    workflow.set_entry_point("Supervisor")
    return workflow.compile()