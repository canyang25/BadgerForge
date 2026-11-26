import operator
import os
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

def create_agent_graph(environment: Any, command_timeout_sec: int = 60, model_name: str | None = None):
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
        command: str = Field(description="The bash command to execute.")

    class ReadFile(BaseModel):
        """Read the contents of a file."""
        filepath: str = Field(description="The absolute path to the file to read.")

    class WriteFile(BaseModel):
        """Write content to a file, overwriting it entirely."""
        filepath: str = Field(description="The absolute path to the file to write.")
        content: str = Field(description="The complete content to write to the file.")

    class ReplaceInFile(BaseModel):
        """Replace an exact unique substring in a file with new content."""
        filepath: str = Field(description="The absolute path to the file to modify.")
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
            default="/tmp/__verify_test_runner.py",
            description="Path for the temporary test script (e.g., /tmp/__verify_test_runner.py or /tmp/__verify_test_runner.sh)."
        )
        command: str = Field(
            default="pytest || python3 /tmp/__verify_test_runner.py",
            description="The shell command to execute the tests in the workspace."
        )

    def sanitize_output(output: str) -> str:
        noise = '>>>> Executing external compose provider "/Users/areichert/.docker/cli-plugins/docker-compose". Please see podman-compose(1) for how to disable this message. <<<<\n'
        output = output.replace(noise, '')
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
            effective_messages = prune_messages(messages, max_recent=10)
            
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
            "1. If an existing test suite or CLI verification command exists (e.g. pytest, cargo test, make test, openssl verify, systemctl/service check, CLI flags), prioritize running it directly.\n"
            "2. If testing a script or library without tests, write a standalone verification script in `test_script_code`.\n"
            "3. Keep any delays/timeouts in tests minimal to avoid timing out.\n"
            "4. Ensure the `command` accurately executes the test suite or custom test script."
        )
        plan_model = llm_medium.with_structured_output(TestRunPlan)
        try:
            plan: TestRunPlan = await plan_model.ainvoke([
                SystemMessage(content=plan_prompt),
                HumanMessage(content=instructions),
            ])
            target_file = plan.test_script_filename or "/tmp/__verify_test_runner.py"
            cmd = plan.command.strip() if plan.command else f"python3 {target_file}"
            script_code = plan.test_script_code
        except Exception:
            target_file = "/tmp/__verify_test_runner.py"
            cmd = "pytest || python3 /tmp/__verify_test_runner.py"
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
        
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call.get("args", {})
            tool_call_id = tool_call["id"]
            
            output_str = ""
            try:
                if tool_name == "ExecuteCommand":
                    command = tool_args.get("command", "")
                    result = await environment.exec(command=command, timeout_sec=command_timeout_sec)
                    stdout = sanitize_output(result.stdout or "")
                    stderr = sanitize_output(result.stderr or "")
                    output_str = f"Exit code: {result.return_code}\nStdout:\n{stdout}\nStderr:\n{stderr}"
                    
                elif tool_name == "ReadFile":
                    filepath = tool_args.get("filepath", "")
                    result = await environment.exec(command=f"cat '{filepath}'", timeout_sec=15)
                    stdout = sanitize_output(result.stdout or "")
                    stderr = sanitize_output(result.stderr or "")
                    if result.return_code == 0:
                        output_str = f"Exit code: 0\nFile {filepath} contents:\n{stdout}"
                    else:
                        output_str = f"Failed to read {filepath}. Exit code: {result.return_code}\nStdout:\n{stdout}\nStderr:\n{stderr}"
                        
                elif tool_name == "WriteFile":
                    filepath = tool_args.get("filepath", "")
                    content = tool_args.get("content", "")
                    import base64
                    encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
                    command = f"mkdir -p \"$(dirname '{filepath}')\" && echo '{encoded}' | base64 -d > '{filepath}'"
                    result = await environment.exec(command=command, timeout_sec=15)
                    stdout = sanitize_output(result.stdout or "")
                    stderr = sanitize_output(result.stderr or "")
                    if result.return_code == 0:
                        output_str = f"Exit code: 0\nSuccessfully wrote to {filepath}"
                    else:
                        output_str = f"Failed to write to {filepath}. Exit code: {result.return_code}\nStdout:\n{stdout}\nStderr:\n{stderr}"
                        
                elif tool_name == "ReplaceInFile":
                    filepath = tool_args.get("filepath", "")
                    old_text = tool_args.get("old_text", "")
                    new_text = tool_args.get("new_text", "")
                    read_res = await environment.exec(command=f"cat '{filepath}'", timeout_sec=15)
                    if read_res.return_code != 0:
                        output_str = f"Failed to read {filepath} for replacement. Stderr: {read_res.stderr}"
                    elif old_text not in read_res.stdout:
                        output_str = f"Error: old_text not found in {filepath}. Please verify the exact text."
                    else:
                        updated_content = read_res.stdout.replace(old_text, new_text, 1)
                        import base64
                        encoded = base64.b64encode(updated_content.encode('utf-8')).decode('utf-8')
                        write_cmd = f"echo '{encoded}' | base64 -d > '{filepath}'"
                        res = await environment.exec(command=write_cmd, timeout_sec=15)
                        if res.return_code == 0:
                            output_str = f"Successfully updated {filepath}"
                        else:
                            output_str = f"Failed to write updated content to {filepath}: {res.stderr}"

                elif tool_name == "FinishTask":
                    finished = True
                    output_str = "Task finished recorded."
                    
                elif tool_name == "Delegate":
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
                    next_agent = worker
                    new_messages.append(ToolMessage(content=output_str, tool_call_id=tool_call_id, name=tool_name))
                    new_messages.append(HumanMessage(content=f"Message from Supervisor to {worker}:\n{instructions}\n\nYou MUST use your tools to perform this task. Do not just hallucinate results and report back without acting."))
                    continue
                    
                elif tool_name == "ReportBack":
                    result_str = tool_args.get("result", "")
                    sender = state.get("sender", "")

                    # Check if action was performed in current tool calls batch first
                    has_acted = any(
                        isinstance(m, ToolMessage) and m.name in ("WriteFile", "ReplaceInFile", "ExecuteCommand")
                        for m in new_messages
                    )
                    if not has_acted:
                        for msg in reversed(messages):
                            if isinstance(msg, HumanMessage) and f"Message from Supervisor to {sender}" in (msg.content or ""):
                                break
                            if isinstance(msg, ToolMessage) and msg.name:
                                if sender in ("Coder", "MediumCoder", "ExpertCoder") and msg.name in ("WriteFile", "ReplaceInFile", "ExecuteCommand"):
                                    has_acted = True
                                    break
                                elif sender == "Researcher" and msg.name in ("ExecuteCommand", "ReadFile"):
                                    has_acted = True
                                    break

                    if not has_acted and sender in ("Coder", "MediumCoder", "ExpertCoder"):
                        action_name = "WriteFile, ReplaceInFile, or ExecuteCommand to implement/build code changes"
                        output_str = f"Action rejected: You have NOT executed any actions yet. You MUST call {action_name} before calling ReportBack."
                        next_agent = sender
                    else:
                        output_str = f"Reported back to Supervisor. Result: {result_str}"
                        next_agent = "Supervisor"
                    
                else:
                    output_str = f"Unknown tool: {tool_name}"
            except Exception as e:
                output_str = f"Error executing {tool_name}: {e}"
                
            new_messages.append(ToolMessage(content=output_str, tool_call_id=tool_call_id, name=tool_name))
            
        return {
            "messages": new_messages, 
            "finished": finished,
            "next_agent": next_agent if next_agent else state.get("next_agent", ""),
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
        
        # Nudges go back to sender
        if isinstance(last_message, HumanMessage) and last_message.content.startswith("You must call a tool"):
            return state.get("sender", "Supervisor")
            
        # Tool outputs route back to sender if no next_agent was assigned
        if isinstance(last_message, ToolMessage):
            return state.get("sender", "Supervisor")
            
        return "Supervisor"

    workflow = StateGraph(GraphState)
    
    supervisor_prompt = (
        "You are the Supervisor Agent managing a software engineering task in a headless container. "
        "You coordinate specialized worker agents:\n"
        "1. Researcher: Explores the environment, inspects existing files/data files, checks packages and requirements.\n"
        "2. Coder: Standard coder (low reasoning effort). Use for initial implementations of straightforward tasks.\n"
        "3. MediumCoder: Intermediate coder (medium reasoning effort). Use when Coder's solution fails tests or requires debugging.\n"
        "4. ExpertCoder: Deep reasoning coder. Use only when MediumCoder fails or for persistent bugs.\n"
        "5. Tester: Runs bash commands (e.g., pytest, python scripts) using ExecuteCommand to verify functionality and edge cases.\n\n"
        "Strict Escalation & De-escalation Workflow:\n"
        "1. GROUNDING: If the task mentions existing files or directories, ALWAYS delegate to Researcher first to inspect file contents and schemas.\n"
        "2. Initial implementation: Delegate to Coder (or MediumCoder for complex math, concurrency, or algorithms).\n"
        "3. Verification: Delegate to Tester to execute real verification commands in the workspace.\n"
        "4. Handling Failures:\n"
        "   - First failure: Delegate error trace and fix instructions to MediumCoder (medium reasoning effort).\n"
        "   - Second or repeated failures: Escalate to ExpertCoder with the full context and failed assertions.\n"
        "5. De-escalation: When test results improve (e.g., the core logic now works and only minor adjustments, formatting, or small fixes remain), DE-ESCALATE back to MediumCoder or Coder. Do not waste tokens on ExpertCoder for minor fixes.\n"
        "6. After every code modification, always delegate to Tester to verify the fix.\n"
        "7. Once tests pass with exit code 0 and the solution is verified, clean up any temporary test scripts and call FinishTask.\n"
        "Do NOT call FinishTask without verified test execution."
    )
    
    researcher_prompt = (
        "You are the Researcher Agent. Your supervisor has delegated a task to you. "
        "Use ExecuteCommand (ls, grep, cat) and ReadFile to investigate the environment. "
        "Do NOT write code or run tests. "
        "When you have finished gathering information, use the ReportBack tool to summarize your findings for the supervisor."
    )
    
    coder_prompt = (
        "You are the Coder Agent. Your supervisor has delegated a task to you. "
        "You MUST use the WriteFile tool to implement code changes. You may use ExecuteCommand for build, compilation, or package management commands.\n"
        "Guidelines:\n"
        "- Write complete, correct, production-grade code.\n"
        "- Do NOT write temporary test scripts or run tests; testing is handled exclusively by the Tester agent.\n"
        "- Avoid hardcoding assumptions: inspect files and error messages carefully.\n"
        "- Preserve expected exceptions and signatures exactly without unintended wrapping.\n"
        "- In async/concurrency contexts, ensure all pending tasks complete their cleanup in `finally:` blocks before re-raising exceptions.\n"
        "- Do NOT call ReportBack without actually using WriteFile.\n"
        "- When done writing files, call ReportBack summarizing what changes you made."
    )
    
    medium_coder_prompt = (
        "You are the MediumCoder Agent equipped with medium reasoning capabilities. Your supervisor has delegated a test failure or code fix to you.\n"
        "You MUST use the WriteFile tool to implement code changes. You may use ExecuteCommand for build, compilation, or package management commands.\n"
        "Guidelines:\n"
        "- Do NOT write temporary test scripts; testing is handled exclusively by Tester.\n"
        "- Analyze the failure traceback, test outputs, and existing code carefully before modifying files.\n"
        "- Look for subtle edge cases: exception handling, resource cleanup, boundary conditions, and type invariants.\n"
        "- Do NOT swallow or wrap raw exceptions unless explicitly specified by the interface.\n"
        "- When done writing files, call ReportBack summarizing what caused the bug and how you resolved it."
    )
    
    expert_coder_prompt = (
        "You are the ExpertCoder Agent equipped with deep reasoning capabilities. Your supervisor has escalated a persistent bug or complex algorithmic problem to you after earlier attempts failed.\n"
        "You MUST use the WriteFile tool to implement code changes. You may use ExecuteCommand for build, compilation, or package management commands.\n"
        "Guidelines:\n"
        "- Do NOT write temporary test scripts; testing is handled exclusively by Tester.\n"
        "- Carefully analyze the problem, failure trace, and edge cases (especially concurrency invariants, async cleanup, signals, or compiler constraints).\n"
        "- Ensure atomic operations, strict lifecycle management, and accurate signal/exception propagation.\n"
        "- Write clean, production-grade, bug-free implementations that account for edge cases.\n"
        "- Do NOT call ReportBack without actually using WriteFile.\n"
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