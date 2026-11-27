"""Characterization tests for the review of andrew/feat-agent-stability.

These tests lock in the behavior on that branch. A failure means the
behavior changed, not that the behavior is desirable.
"""

import asyncio
import errno
import inspect
import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from harbor.environments.base import ExecResult
from harbor.environments.docker.docker_unix import UnixOps
from harbor.models.agent.context import AgentContext
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from lg_agent import agent as agent_mod
from lg_agent import graph as graph_mod
from lg_agent.agent import LGAgent
from lg_agent.graph import create_agent_graph
from lg_agent.models import RunMetadata
from lg_agent.observability import LOG_FILE, RUNS_DIR, log_run

REPO = Path(__file__).resolve().parents[2]


def _install_llm(monkeypatch, handler):
    created = []

    class FakeLLM:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.schema = None
            created.append(self)

        def bind_tools(self, tools):
            return self

        def with_structured_output(self, schema):
            self.schema = schema
            return self

        async def ainvoke(self, messages):
            return await handler(self, messages)

    monkeypatch.setattr(graph_mod, "ChatOpenAI", FakeLLM)
    return created


def _exec_recorder(store, stdout="", return_code=0):
    async def _exec(**kwargs):
        store.append(kwargs["command"])
        return ExecResult(stdout=stdout, stderr="", return_code=return_code)

    return _exec


def _state(messages, **extra):
    base = {
        "messages": messages,
        "sender": "Supervisor",
        "next_agent": "",
        "finished": False,
        "input_tokens": 0,
        "output_tokens": 0,
        "action_taken": False,
    }
    base.update(extra)
    return base


async def _tools(monkeypatch, messages, stdout=""):
    commands = []

    async def handler(self, _messages):
        raise AssertionError("tools path should not call the LLM")

    _install_llm(monkeypatch, handler)
    graph = create_agent_graph(SimpleNamespace(exec=_exec_recorder(commands, stdout=stdout)))
    result = await graph.nodes["tools"].ainvoke(_state(messages, sender="Coder"))
    return result, commands


def _ai(name, args, call_id):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


class _App:
    def __init__(self, steps):
        self.steps = steps
        self.yielded = 0

    async def astream(self, state, stream_mode="values"):
        for step in self.steps:
            produced = step(state) if callable(step) else step
            if inspect.isawaitable(produced):
                produced = await produced
            self.yielded += 1
            yield produced


async def _run(monkeypatch, tmp_path, app, clock=None):
    logged = {}

    def capture(meta):
        logged["status"] = meta.final_status

    monkeypatch.setattr(agent_mod, "log_run", capture)
    monkeypatch.setattr(agent_mod, "create_agent_graph", lambda *a, **k: app)
    if clock is not None:
        monkeypatch.setattr(agent_mod.time, "time", lambda: clock["now"])
    agent = LGAgent(logs_dir=tmp_path)
    ctx = SimpleNamespace(
        metadata={},
        n_input_tokens=0,
        n_output_tokens=0,
        task_timeout_sec=30,
    )
    await agent.run("solve the task", MagicMock(), ctx)
    return ctx, logged


def _unfinished(text="still working"):
    return {
        "messages": [HumanMessage(content=text)],
        "finished": False,
        "input_tokens": 1,
        "output_tokens": 1,
    }


def _run_shell(command, *, cwd=None, shell=False):
    argv = command if shell else ["bash", "-c", command]
    return subprocess.run(
        argv,
        shell=shell,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.asyncio
async def test_expert_client_uses_the_same_effort_as_medium(monkeypatch):
    """llm_high is constructed with medium effort, same as llm_medium."""

    async def handler(self, messages):
        raise AssertionError("not called")

    created = _install_llm(monkeypatch, handler)
    create_agent_graph(MagicMock())
    efforts = [client.kwargs["reasoning_effort"] for client in created]
    bodies = [client.kwargs["extra_body"]["reasoning_effort"] for client in created]
    assert efforts == ["low", "medium", "medium"]
    assert bodies == ["low", "medium", "medium"]
    source = (REPO / "lg_agent" / "graph.py").read_text()
    assert "You are the ExpertCoder" in source
    assert "You are the MediumCoder" in source


@pytest.mark.asyncio
async def test_worker_node_tolerates_missing_usage_metadata(monkeypatch):
    """create_agent_node checks usage_metadata before calling .get."""
    seen = {}

    async def handler(self, messages):
        seen["prompt"] = messages[0].content
        response = SimpleNamespace(content="WORKER_OK", usage_metadata=None)
        return response

    _install_llm(monkeypatch, handler)
    graph = create_agent_graph(MagicMock())
    result = await graph.nodes["Coder"].ainvoke(
        _state([HumanMessage(content="ORIGINAL_TASK")])
    )
    assert result["messages"][0].content == "WORKER_OK"
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0


@pytest.mark.asyncio
async def test_tester_summary_replaced_when_usage_metadata_is_none(monkeypatch):
    commands = []

    async def handler(self, messages):
        text = "\n".join(getattr(message, "content", "") for message in messages)
        if "specialized test engineer" in text:
            return self.schema(command="echo planned", test_script_code=None)
        return SimpleNamespace(content="SHOULD_SURVIVE", usage_metadata=None)

    _install_llm(monkeypatch, handler)
    graph = create_agent_graph(SimpleNamespace(exec=_exec_recorder(commands, stdout="ok")))
    result = await graph.nodes["Tester"].ainvoke(
        _state(
            [
                HumanMessage(content="ORIGINAL_TASK"),
                HumanMessage(content="Message from Supervisor to Tester:\nRun checks"),
            ]
        )
    )
    report = result["messages"][0].content
    assert "Error evaluating summary" in report
    assert "SHOULD_SURVIVE" not in report
    assert result["input_tokens"] == 0
    assert commands == ["echo planned"]


@pytest.mark.asyncio
async def test_tester_plan_call_does_not_add_its_tokens(monkeypatch):
    calls = {"plan": 0, "eval": 0}

    async def handler(self, messages):
        text = "\n".join(getattr(message, "content", "") for message in messages)
        if "specialized test engineer" in text:
            calls["plan"] += 1
            return self.schema(command="echo planned", test_script_code=None)
        calls["eval"] += 1
        return SimpleNamespace(
            content="EVAL_ONLY",
            usage_metadata={"input_tokens": 11, "output_tokens": 7},
        )

    _install_llm(monkeypatch, handler)
    graph = create_agent_graph(
        SimpleNamespace(exec=_exec_recorder([], stdout="ok"))
    )
    result = await graph.nodes["Tester"].ainvoke(
        _state([HumanMessage(content="ORIGINAL_TASK")])
    )
    assert calls == {"plan": 1, "eval": 1}
    assert "EVAL_ONLY" in result["messages"][0].content
    assert result["input_tokens"] == 11
    assert result["output_tokens"] == 7


@pytest.mark.asyncio
async def test_tester_plan_failure_fallback_forces_exit_zero(monkeypatch, tmp_path):
    commands = []

    async def handler(self, messages):
        raise RuntimeError("structured output failed")

    _install_llm(monkeypatch, handler)
    graph = create_agent_graph(SimpleNamespace(exec=_exec_recorder(commands)))
    await graph.nodes["Tester"].ainvoke(_state([HumanMessage(content="ORIGINAL_TASK")]))
    assert len(commands) == 1
    assert commands[0].endswith("|| true")
    completed = _run_shell(commands[0], cwd=tmp_path, shell=True)
    assert completed.returncode == 0


@pytest.mark.asyncio
async def test_turn_budget_counts_yields_that_are_not_model_calls(monkeypatch, tmp_path):
    app = _App([_unfinished(str(i)) for i in range(200)])
    monkeypatch.setattr(agent_mod, "MAX_TURNS", 150)
    ctx, logged = await _run(monkeypatch, tmp_path, app)
    assert ctx.metadata["turns"] == 150
    assert app.yielded == 150
    assert logged["status"] == "max_turns_reached"


@pytest.mark.asyncio
async def test_first_model_call_consumes_three_graph_yields(monkeypatch, tmp_path):
    calls = {"n": 0}

    async def handler(self, messages):
        calls["n"] += 1
        return AIMessage(
            content="",
            tool_calls=[{"name": "FinishTask", "args": {"reason": "done"}, "id": "c1"}],
        )

    _install_llm(monkeypatch, handler)
    monkeypatch.setattr(agent_mod, "log_run", lambda meta: None)
    agent = LGAgent(logs_dir=tmp_path)
    ctx = AgentContext(metadata={})
    await agent.run("solve the task", MagicMock(), ctx)
    assert calls["n"] == 1
    assert ctx.metadata["turns"] == 3
    assert ctx.metadata["finished"] is True


@pytest.mark.asyncio
async def test_turn_cap_stops_before_finish_tool_runs(monkeypatch, tmp_path):
    calls = {"n": 0}

    async def handler(self, messages):
        calls["n"] += 1
        return AIMessage(
            content="",
            tool_calls=[{"name": "FinishTask", "args": {"reason": "done"}, "id": "c1"}],
        )

    _install_llm(monkeypatch, handler)
    logged = {}
    monkeypatch.setattr(agent_mod, "log_run", lambda meta: logged.setdefault("status", meta.final_status))
    monkeypatch.setattr(agent_mod, "MAX_TURNS", 2)
    agent = LGAgent(logs_dir=tmp_path)
    ctx = AgentContext(metadata={})
    await agent.run("solve the task", MagicMock(), ctx)
    assert calls["n"] == 1
    assert ctx.metadata["turns"] == 2
    assert ctx.metadata["finished"] is False
    assert logged["status"] == "max_turns_reached"


@pytest.mark.asyncio
async def test_max_time_reached_is_overwritten(monkeypatch, tmp_path):
    clock = {"now": 0.0}

    def step(_state):
        clock["now"] = 1_000.0
        return _unfinished("past the deadline")

    ctx, logged = await _run(monkeypatch, tmp_path, _App([step]), clock)
    assert ctx.metadata["turns"] == 1
    assert logged["status"] == "max_turns_reached"


@pytest.mark.asyncio
async def test_time_limit_is_checked_only_between_steps(monkeypatch, tmp_path):
    clock = {"now": 0.0}
    seen = {"finished_over_limit_step": False}

    async def step(_state):
        clock["now"] = 5_000.0
        seen["finished_over_limit_step"] = True
        return _unfinished("step ran long")

    ctx, logged = await _run(monkeypatch, tmp_path, _App([step, _unfinished("next")]), clock)
    assert seen["finished_over_limit_step"] is True
    assert ctx.metadata["turns"] == 1
    assert logged["status"] == "max_turns_reached"


@pytest.mark.asyncio
async def test_wall_clock_default_ignores_context_timeout(monkeypatch, tmp_path):
    source = inspect.getsource(agent_mod)
    assert 'os.environ.get("AGENT_MAX_WALL_CLOCK_SEC", "840")' in source
    assert "timeout" not in inspect.signature(LGAgent.run).parameters
    assert agent_mod.MAX_WALL_CLOCK_SEC == 840
    clock = {"now": 0.0}
    app = _App([])

    class ClockApp:
        async def astream(self, state, stream_mode="values"):
            for stamp in (0.0, 100.0, 200.0):
                clock["now"] = stamp
                app.yielded += 1
                yield _unfinished(str(stamp))

    ctx, logged = await _run(monkeypatch, tmp_path, ClockApp(), clock)
    assert app.yielded == 3
    assert ctx.task_timeout_sec == 30
    assert logged["status"] == "max_turns_reached"


@pytest.mark.asyncio
async def test_task_cancel_is_logged_as_running(monkeypatch, tmp_path):
    class CancelApp:
        async def astream(self, state, stream_mode="values"):
            yield _unfinished("partial")
            raise asyncio.CancelledError()

    logged = {}
    monkeypatch.setattr(agent_mod, "log_run", lambda meta: logged.setdefault("status", meta.final_status))
    monkeypatch.setattr(agent_mod, "create_agent_graph", lambda *a, **k: CancelApp())
    agent = LGAgent(logs_dir=tmp_path)
    ctx = AgentContext(metadata={})
    with pytest.raises(asyncio.CancelledError):
        await agent.run("solve the task", MagicMock(), ctx)
    assert logged["status"] == "running"


@pytest.mark.asyncio
async def test_stream_error_before_metadata_becomes_attributeerror(monkeypatch, tmp_path, caplog):
    """A failure before the loop assigns metadata escapes as AttributeError."""

    class Boom:
        async def astream(self, state, stream_mode="values"):
            failed = True
            if failed:
                raise RuntimeError("stream failed early")
            yield _unfinished("unused")

    logged = {}
    monkeypatch.setattr(agent_mod, "log_run", lambda meta: logged.setdefault("status", meta.final_status))
    monkeypatch.setattr(agent_mod, "create_agent_graph", lambda *_a, **_k: Boom())
    agent = LGAgent(logs_dir=tmp_path)
    caplog.set_level("ERROR")
    with pytest.raises(AttributeError, match="'NoneType' object has no attribute 'get'"):
        await agent.run("solve the task", MagicMock(), AgentContext())
    assert "stream failed early" in caplog.text
    assert "status" not in logged


@pytest.mark.asyncio
async def test_readfile_drops_middle_of_large_output(monkeypatch):
    marker = "MIDDLE_MARKER_UNIQUE"
    stdout = ("H" * 2500) + marker + ("T" * 2500)
    messages = [
        HumanMessage(content="ORIGINAL_TASK"),
        _ai("ReadFile", {"filepath": "/tmp/big.txt"}, "r1"),
    ]
    result, commands = await _tools(monkeypatch, messages, stdout=stdout)
    body = result["messages"][0].content
    assert commands == ["cat '/tmp/big.txt'"]
    assert marker not in body
    assert "[OUTPUT TRUNCATED]" in body
    assert body.startswith("Exit code: 0")


@pytest.mark.asyncio
async def test_readfile_offset_without_limit_cats_the_whole_file(monkeypatch):
    messages = [
        _ai("ReadFile", {"filepath": "/tmp/big.txt", "offset": 2}, "r1"),
    ]
    _result, commands = await _tools(monkeypatch, messages, stdout="line\n")
    assert commands == ["cat '/tmp/big.txt'"]


@pytest.mark.asyncio
async def test_readfile_quote_in_path_breaks_the_shell(monkeypatch, tmp_path):
    path = tmp_path / "a'b.txt"
    path.write_text("QUOTE_OK\n")
    messages = [_ai("ReadFile", {"filepath": str(path)}, "r1")]
    _result, commands = await _tools(monkeypatch, messages)
    assert "'" in commands[0]
    completed = _run_shell(commands[0], shell=True)
    assert completed.returncode != 0
    assert "QUOTE_OK" not in completed.stdout
    assert "Unterminated quoted string" in completed.stderr


@pytest.mark.asyncio
async def test_writefile_command_is_one_argv_and_dies_near_100kb(monkeypatch, tmp_path):
    assert UnixOps.exec_shell_args("echo hi") == ["bash", "-c", "echo hi"]
    small = tmp_path / "small.txt"
    small_messages = [
        _ai("WriteFile", {"filepath": str(small), "content": "hello-write"}, "w1")
    ]
    _result, commands = await _tools(monkeypatch, small_messages)
    completed = _run_shell(commands[0])
    assert completed.returncode == 0
    assert small.read_text() == "hello-write"

    large = tmp_path / "large.txt"
    payload = "A" * 100_000
    large_messages = [_ai("WriteFile", {"filepath": str(large), "content": payload}, "w2")]
    _result, commands = await _tools(monkeypatch, large_messages)
    assert len(commands[0]) > 131_072
    with pytest.raises(OSError) as exc_info:
        _run_shell(commands[0])
    assert exc_info.value.errno == errno.E2BIG
    assert not large.exists()


@pytest.mark.asyncio
async def test_long_history_drops_supervisor_instruction(monkeypatch):
    captured = {}

    async def handler(self, messages):
        captured["messages"] = messages
        return AIMessage(content="ok")

    _install_llm(monkeypatch, handler)
    graph = create_agent_graph(MagicMock())
    instruction = "Message from Supervisor to Researcher:\nUNIQUE_INSTRUCTION_ALPHA"
    messages = [HumanMessage(content="ORIGINAL_TASK"), HumanMessage(content=instruction)]
    messages.extend(HumanMessage(content=f"filler-{i}") for i in range(40))
    await graph.nodes["Researcher"].ainvoke(_state(messages, sender="Researcher"))
    blob = "\n".join(message.content for message in captured["messages"])
    assert "ORIGINAL_TASK" in blob
    assert "UNIQUE_INSTRUCTION_ALPHA" not in blob


@pytest.mark.asyncio
async def test_short_history_keeps_supervisor_instruction(monkeypatch):
    captured = {}

    async def handler(self, messages):
        captured["messages"] = messages
        return AIMessage(content="ok")

    _install_llm(monkeypatch, handler)
    graph = create_agent_graph(MagicMock())
    messages = [
        HumanMessage(content="ORIGINAL_TASK"),
        HumanMessage(content="Message from Supervisor to Researcher:\nKEEP_ME"),
        HumanMessage(content="recent"),
    ]
    await graph.nodes["Researcher"].ainvoke(_state(messages, sender="Researcher"))
    blob = "\n".join(message.content for message in captured["messages"])
    assert "KEEP_ME" in blob


@pytest.mark.asyncio
async def test_supervisor_prompt_gives_up_on_rosetta_errors(monkeypatch):
    captured = {}

    async def handler(self, messages):
        captured["messages"] = messages
        return AIMessage(content="ok")

    _install_llm(monkeypatch, handler)
    graph = create_agent_graph(MagicMock())
    await graph.nodes["Supervisor"].ainvoke(_state([HumanMessage(content="ORIGINAL_TASK")]))
    prompt = captured["messages"][0].content
    assert "Rosetta unimplemented syscall" in prompt
    assert "call `FinishTask` immediately" in prompt
    assert "LD_PRELOAD" in prompt


@pytest.mark.asyncio
async def test_tester_prompt_is_never_sent(monkeypatch):
    sent = []

    async def handler(self, messages):
        sent.append("\n".join(getattr(message, "content", "") for message in messages))
        text = sent[-1]
        if "specialized test engineer" in text:
            return self.schema(command="echo planned", test_script_code=None)
        return SimpleNamespace(
            content="summary",
            usage_metadata={"input_tokens": 1, "output_tokens": 1},
        )

    _install_llm(monkeypatch, handler)
    graph = create_agent_graph(SimpleNamespace(exec=_exec_recorder([], stdout="ok")))
    await graph.nodes["Tester"].ainvoke(_state([HumanMessage(content="ORIGINAL_TASK")]))
    source = inspect.getsource(create_agent_graph)
    assert source.count("tester_prompt") == 1
    assert "You DO NOT know test results until you run ExecuteCommand" in source
    assert all("You DO NOT know test results" not in text for text in sent)
    assert sent


@pytest.mark.asyncio
async def test_graph_reads_openai_api_key_and_hardcodes_gateway(monkeypatch):
    async def handler(self, messages):
        raise AssertionError("not called")

    created = _install_llm(monkeypatch, handler)
    monkeypatch.setenv("LLM_API_KEY", "llm-key-value")
    monkeypatch.setenv("LLM_BASE_URL", "http://configured.example/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    create_agent_graph(MagicMock())
    assert {client.kwargs["api_key"] for client in created} == {"dummy"}
    assert {client.kwargs["base_url"] for client in created} == {
        "https://llm-gw01.doit.wisc.edu/v1"
    }

    created.clear()
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key-value")
    create_agent_graph(MagicMock())
    assert {client.kwargs["api_key"] for client in created} == {"openai-key-value"}
    assert {client.kwargs["base_url"] for client in created} == {
        "https://llm-gw01.doit.wisc.edu/v1"
    }


def test_observability_writes_okf_relative_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    log_run(RunMetadata(agent_version="0.1.0", test_name="review", final_status="success"))
    assert LOG_FILE == ".okf/logs.jsonl"
    assert RUNS_DIR == ".okf/runs"
    assert (tmp_path / ".okf" / "logs.jsonl").is_file()
    assert list((tmp_path / ".okf" / "runs").glob("*.md"))


def test_repo_hygiene_files_are_on_the_branch():
    assert (REPO / "starter" / "agent" / "llm.py").is_file()
    assert (REPO / "podman-rosetta.py").is_file()
    assert "rosetta" in (REPO / "podman-rosetta.py").read_text().lower()
    devcontainer = (REPO / ".devcontainer" / "devcontainer.json").read_text()
    assert "linux/arm64" in devcontainer
    starter_llm = (REPO / "starter" / "agent" / "llm.py").read_text()
    graph_source = (REPO / "lg_agent" / "graph.py").read_text()
    assert "LLM_API_KEY" in starter_llm
    assert "LLM_BASE_URL" in starter_llm
    assert "OPENAI_API_KEY" in graph_source
    assert "LLM_API_KEY" not in graph_source
    assert (REPO / ".okf" / "logs.jsonl").stat().st_size > 10_000_000


def test_source_has_no_live_api_keys_or_private_keys():
    blobs = []
    paths = (
        list((REPO / "lg_agent").rglob("*.py"))
        + list((REPO / "starter").rglob("*.py"))
        + list((REPO / "scripts").rglob("*.py"))
        + list(REPO.glob("*.py"))
        + list(REPO.glob("*.sh"))
    )
    for path in paths:
        if path.name == "test_review_findings.py":
            continue
        blobs.append(path.read_text())
    source = "\n".join(blobs)
    assert not re.search(r"sk-[A-Za-z0-9_\-]{10,}", source)
    assert "BEGIN PRIVATE KEY" not in source
    assert "BEGIN RSA PRIVATE KEY" not in source


def test_run_logs_are_finishtask_not_harbor_rewards():
    log_path = REPO / ".okf" / "logs.jsonl"
    lines = log_path.read_text().splitlines()
    assert lines
    assert not any("reward" in line.lower() for line in lines)
    rows = [json.loads(line) for line in lines if line.strip()]
    assert not any(row["final_status"] == "max_time_reached" for row in rows)
    successes = [row for row in rows if row["final_status"] == "success"]
    assert successes
    for row in successes:
        names = [call.get("name") for message in row["trajectory"] for call in message.get("tool_calls") or []]
        assert "FinishTask" in names
    named = {row["test_name"] for row in rows if row["test_name"] not in {"unknown_task", "agent"}}
    named_success = {
        row["test_name"]
        for row in successes
        if row["test_name"] not in {"unknown_task", "agent"}
    }
    assert len(named) == 89
    assert len(named_success) == 59
    timed_out_as_turns = [
        row
        for row in rows
        if row["final_status"] == "max_turns_reached"
        and row["execution_time_sec"] >= 840
        and len(row["trajectory"]) < 80
    ]
    assert timed_out_as_turns
    near_900 = [
        row
        for row in rows
        if row["final_status"] == "running" and abs(row["execution_time_sec"] - 900) < 0.05
    ]
    assert len(near_900) >= 20
    pem_files = [
        path
        for path in (REPO / ".okf").rglob("*")
        if path.is_file() and "BEGIN PRIVATE KEY" in path.read_text(errors="ignore")
    ]
    assert len(pem_files) == 4
    akias = set(re.findall(r"AKIA[0-9A-Z]{16}", log_path.read_text(errors="ignore")))
    assert akias == {"AKIA1234567890123456"}


def test_expert_prompt_prefers_makefile_flags_over_system_headers():
    source = (REPO / "lg_agent" / "graph.py").read_text()
    assert "Makefile flags" in source
    assert "-std=c++11" in source


@pytest.mark.asyncio
async def test_read_only_streak_nudge_fires_after_five_commands(monkeypatch):
    async def handler(self, messages):
        raise AssertionError("not called")

    _install_llm(monkeypatch, handler)

    def history(count):
        messages = []
        for index in range(count - 1):
            messages.append(_ai("ExecuteCommand", {"command": "ls"}, f"old{index}"))
            messages.append(
                ToolMessage(content="ok", tool_call_id=f"old{index}", name="ExecuteCommand")
            )
        messages.append(_ai("ExecuteCommand", {"command": "ls"}, "current"))
        return messages

    async def run(count):
        graph = create_agent_graph(SimpleNamespace(exec=_exec_recorder([])))
        return await graph.nodes["tools"].ainvoke(
            _state(history(count), sender="Researcher")
        )

    four = await run(4)
    five = await run(5)
    assert not any("SYSTEM WARNING" in getattr(message, "content", "") for message in four["messages"])
    assert any("SYSTEM WARNING" in getattr(message, "content", "") for message in five["messages"])
