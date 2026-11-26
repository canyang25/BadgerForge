from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import datetime
import uuid

class RunMetadata(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for the run.")
    agent_version: str = Field(..., description="The version of the agent used.")
    test_name: str = Field(..., description="The name of the test/task executed.")
    total_input_tokens: int = Field(0, description="Total input tokens consumed.")
    total_output_tokens: int = Field(0, description="Total output tokens consumed.")
    execution_time_sec: float = Field(0.0, description="Total execution time in seconds.")
    final_status: str = Field("running", description="Status of the run (e.g., success, timeout, error).")
    trajectory: List[Dict[str, Any]] = Field(default_factory=list, description="List of messages/actions taken.")
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, description="Time of run.")

class AgentState(BaseModel):
    messages: List[Dict[str, Any]] = Field(default_factory=list, description="Conversation messages.")
    finished: bool = Field(False, description="Whether the agent has completed the task.")
    input_tokens: int = Field(0, description="Tokens used for input.")
    output_tokens: int = Field(0, description="Tokens used for output.")
    current_turn: int = Field(0, description="Current turn number.")
