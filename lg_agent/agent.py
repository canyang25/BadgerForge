import json
import os
import time
from pathlib import Path
import asyncio
from typing import Dict, Any

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage

from lg_agent.graph import create_agent_graph
from lg_agent.models import RunMetadata
from lg_agent.observability import log_run

MAX_TURNS = int(os.environ.get("AGENT_MAX_TURNS", "150"))
MAX_WALL_CLOCK_SEC = int(os.environ.get("AGENT_MAX_WALL_CLOCK_SEC", "840"))
COMMAND_TIMEOUT_SEC = int(os.environ.get("AGENT_COMMAND_TIMEOUT_SEC", "120"))

class LGAgent(BaseAgent):
    @staticmethod
    def name() -> str:
        return "lg_agent"

    def version(self) -> str | None:
        return "0.1.0"

    async def setup(self, environment: BaseEnvironment) -> None:
        pass

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        start_time = time.time()
        
        # Build graph
        app = create_agent_graph(
            environment,
            command_timeout_sec=COMMAND_TIMEOUT_SEC,
            model_name=getattr(self, "model_name", None),
        )
        
        # Initialize state
        initial_state = {
            "messages": [
                HumanMessage(content=instruction)
            ],
            "sender": "Supervisor",
            "next_agent": "",
            "finished": False,
            "input_tokens": 0,
            "output_tokens": 0,
            "action_taken": False,
        }
        
        total_in_tokens = 0
        total_out_tokens = 0
        final_status = "running"
        turn_count = 0
        current_state = initial_state
        
        try:
            # Run graph iteratively to update context and handle max turns
            async for step in app.astream(initial_state, stream_mode="values"):
                turn_count += 1
                current_state = step
                
                # GraphState now uses Annotated[..., operator.add] for tokens, so the state emits cumulative totals
                total_in_tokens = step.get("input_tokens", 0)
                total_out_tokens = step.get("output_tokens", 0)
                
                # Context updates for Harbor per turn
                context.n_input_tokens = total_in_tokens
                context.n_output_tokens = total_out_tokens
                context.metadata = {
                    **(context.metadata or {}),
                    "turns": turn_count,
                    "finished": step.get("finished", False),
                    "messages": [
                        {"role": "user" if isinstance(m, HumanMessage) else ("tool" if isinstance(m, ToolMessage) else "assistant"), "content": m.content}
                        if hasattr(m, "content") else str(m)
                        for m in step.get("messages", [])
                    ],
                }
                
                if time.time() - start_time > MAX_WALL_CLOCK_SEC:
                    final_status = "max_time_reached"
                    break
                
                if step.get("finished", False) or turn_count >= MAX_TURNS:
                    break
                    
            if current_state.get("finished"):
                context.metadata["finished"] = True
                final_status = "success"
            else:
                final_status = "max_turns_reached"

        except asyncio.TimeoutError:
            final_status = "timeout"
        except Exception as e:
            self.logger.error(f"Error in run: {e}")
            final_status = f"error: {str(e)}"
        finally:
            exec_time = time.time() - start_time

            # Serialize messages for the trajectory
            trajectory = []
            for msg in current_state.get("messages", []):
                msg_dict = {
                    "type": msg.__class__.__name__,
                    "content": getattr(msg, "content", str(msg)),
                }
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    msg_dict["tool_calls"] = msg.tool_calls
                if hasattr(msg, "tool_call_id") and msg.tool_call_id:
                    msg_dict["tool_call_id"] = msg.tool_call_id
                if hasattr(msg, "name") and msg.name:
                    msg_dict["name"] = msg.name
                trajectory.append(msg_dict)

            # Save trajectory.json directly into self.logs_dir for Harbor
            if hasattr(self, "logs_dir") and self.logs_dir:
                logs_path = Path(self.logs_dir)
                logs_path.mkdir(parents=True, exist_ok=True)
                trajectory_file = logs_path / "trajectory.json"
                try:
                    with open(trajectory_file, "w", encoding="utf-8") as f:
                        json.dump(trajectory, f, indent=2, ensure_ascii=False)
                except Exception as exc:
                    self.logger.error(f"Failed writing trajectory to {trajectory_file}: {exc}")

            # Derive task name from logs_dir or metadata
            task_name = context.metadata.get("test_name")
            if not task_name or task_name == "unknown_task":
                if hasattr(self, "logs_dir") and self.logs_dir:
                    p = Path(self.logs_dir)
                    if p.name == "agent" and p.parent:
                        task_name = p.parent.name.split("__")[0]
                    else:
                        task_name = p.name.split("__")[0]
                elif getattr(context, "task_id", None):
                    task_name = getattr(context, "task_id")
                else:
                    task_name = "unknown_task"

            # Run metadata logging
            run_meta = RunMetadata(
                agent_version=self.version(),
                test_name=task_name,
                total_input_tokens=total_in_tokens,
                total_output_tokens=total_out_tokens,
                execution_time_sec=exec_time,
                final_status=final_status,
                trajectory=trajectory,
            )
            try:
                log_run(run_meta)
            except Exception as exc:
                self.logger.error(f"Failed to log run: {exc}")
