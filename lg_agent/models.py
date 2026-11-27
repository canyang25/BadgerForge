from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import datetime
import os
import time
import uuid

_last_v7_timestamp = 0
_v7_seq = 0

def uuid7() -> str:
    """Generate a strictly increasing, time-ordered UUIDv7 (RFC 9562)."""
    global _last_v7_timestamp, _v7_seq
    ns = time.time_ns()
    ms = ns // 1_000_000
    if ms <= _last_v7_timestamp:
        ms = _last_v7_timestamp
        _v7_seq = (_v7_seq + 1) & 0xFFF
        if _v7_seq == 0:
            ms += 1
    else:
        _v7_seq = (ns % 1_000_000) & 0xFFF
    _last_v7_timestamp = ms

    ts_bytes = ms.to_bytes(6, byteorder="big")
    seq_bytes = _v7_seq.to_bytes(2, byteorder="big")
    ver_byte = 0x70 | (seq_bytes[0] & 0x0F)
    seq_low_byte = seq_bytes[1]

    rand_bytes = os.urandom(8)
    var_byte = 0x80 | (rand_bytes[0] & 0x3F)

    uuid_bytes = ts_bytes + bytes([ver_byte, seq_low_byte, var_byte]) + rand_bytes[1:]
    return str(uuid.UUID(bytes=uuid_bytes))

class RunMetadata(BaseModel):
    run_id: str = Field(default_factory=uuid7, description="Unique identifier for the run.")
    agent_version: str = Field(..., description="The version of the agent used.")
    test_name: str = Field(..., description="The name of the test/task executed.")
    total_input_tokens: int = Field(0, description="Total input tokens consumed.")
    total_output_tokens: int = Field(0, description="Total output tokens consumed.")
    execution_time_sec: float = Field(0.0, description="Total execution time in seconds.")
    final_status: str = Field("running", description="Status of the run (e.g., success, timeout, error).")
    trajectory: List[Dict[str, Any]] = Field(default_factory=list, description="List of messages/actions taken.")
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.utcnow, description="Time of run.")
