"""
Pydantic models for API request/response validation and serialization.
These models define the expected data structures for interacting with the API.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import datetime # For timestamp fields

# --- Base Models & Common Fields ---
class OrmBaseModel(BaseModel):
    """A base model that enables ORM mode for compatibility with ORM objects."""
    class Config:
        orm_mode = True


# --- Item Schemas (Example from initial setup) ---
class ItemBase(BaseModel):
    name: str
    description: Optional[str] = None

class ItemCreate(ItemBase):
    pass

class Item(OrmBaseModel, ItemBase): # Inherit from OrmBaseModel
    id: int


# --- Task Schemas ---
class TaskCreateRequest(BaseModel):
    description: str = Field(..., min_length=1, example="Plan the project's next phase.")

class TaskResponse(OrmBaseModel):
    id: int
    description: str
    status: str
    timestamp: datetime.datetime # Assuming stored as datetime object or ISO string convertible

class TaskUpdateRequest(BaseModel):
    status: Optional[str] = Field(None, example="in_progress")
    description: Optional[str] = Field(None, example="Refined plan for project's next phase.")


# --- Plan Schemas ---
class PlanCreateRequest(BaseModel):
    details: str = Field(..., min_length=1, example="Step 1: Research, Step 2: Develop, Step 3: Test.")

class PlanResponse(OrmBaseModel):
    id: int
    details: str
    timestamp: datetime.datetime


# --- Log Schemas ---
class LogEntryResponse(OrmBaseModel):
    id: int
    message: str
    level: str
    timestamp: datetime.datetime

class LogCreateRequest(BaseModel): # If allowing external log submission
    message: str = Field(..., min_length=1)
    level: str = Field("INFO", example="WARNING")


# --- Agent Configuration Schemas (from previous structure, retained) ---
class AgentConfig(BaseModel):
    llm_model_local: Optional[str] = "phi3"
    llm_model_remote: Optional[str] = None
    max_iterations: Optional[int] = 10
    self_healing_enabled: Optional[bool] = True
    plugins_enabled: Optional[List[str]] = ["file_ops"]


# --- Memory Schemas (from previous structure, retained/adapted) ---
class MemoryQuery(BaseModel):
    query: str # Renamed from query_text for consistency if 'query' is used in MemoryManager
    type: Optional[str] = Field("structured", example="structured OR semantic") # To specify query type
    top_k: Optional[int] = 5

class MemoryQueryResult(BaseModel):
    id: str
    content: Dict[str, Any]
    score: Optional[float] = None # For semantic search results
    type: str # e.g., "task", "log", "plan", "semantic_match"
    source: str # e.g., "sqlite_tasks", "vector_db"


# --- Tool Schemas (from previous structure, retained) ---
class ToolInfo(BaseModel):
    name: str
    description: str
    parameters_schema: Dict[str, Any] # JSON schema for parameters

class ToolExecutionRequest(BaseModel):
    parameters: Dict[str, Any]

class ToolExecutionResult(BaseModel):
    tool_name: str
    status: str # e.g., "success", "error"
    result: Optional[Any] = None
    error_message: Optional[str] = None


# --- General API Responses ---
class MessageResponse(BaseModel):
    message: str


# --- LLM Interaction Schemas ---
class LLMAskRequest(BaseModel):
    prompt: str = Field(..., min_length=1, example="Explain quantum computing in simple terms.")
    model: Optional[str] = Field("auto", example="phi3:latest OR auto")
    safe: Optional[bool] = Field(True, description="Hint for routing: True prefers local/CPU, False prefers remote/GPU if available.")
    stream: Optional[bool] = Field(False, description="Whether to stream the response.") # For future streaming support
    system_prompt: Optional[str] = Field(None, example="You are a helpful AI assistant.")
    options: Optional[Dict[str, Any]] = Field(None, example={"temperature": 0.7})

class LLMAskResponse(BaseModel):
    response: Any # Will be string for non-streamed, or potentially a different structure for streamed
    model_used: Optional[str] = None
    instance_used: Optional[str] = None # 'local' or 'remote'
    error: Optional[str] = None # If an error occurred


# --- Celery Asynchronous Task Schemas ---
class AddNumbersTaskRequest(BaseModel):
    a: float = Field(..., example=5.5)
    b: float = Field(..., example=10.2)

class SimulateLongTaskRequest(BaseModel):
    duration_seconds: int = Field(..., ge=1, example=5)
    message: Optional[str] = Field("Simulating work", example="Processing large dataset")

class AsyncTaskResponse(BaseModel):
    task_id: str = Field(..., example="abc123xyz789")
    status: str = Field("PENDING", example="PENDING") # Initial status upon submission
    message: Optional[str] = Field(None, example="Task submitted successfully.")

class AsyncTaskStatusResponse(BaseModel):
    task_id: str = Field(..., example="abc123xyz789")
    status: str = Field(..., example="SUCCESS / FAILURE / PENDING / RETRY / STARTED")
    result: Optional[Any] = Field(None, example=15.7) # Result of the task if successful
    error: Optional[str] = Field(None, example="ValueError: Division by zero") # Error message if failed
    traceback: Optional[str] = Field(None, description="Full traceback if the task failed.") # For detailed error info


# --- Semantic Memory Schemas ---
class SemanticAddRequest(BaseModel):
    text: str = Field(..., min_length=1, example="The agent observed a new pattern in the data.")
    metadata: Dict[str, Any] = Field(default_factory=dict, example={"source": "observation", "timestamp": "2023-11-16T10:00:00Z"})
    id: Optional[str] = Field(None, example="obs_pattern_001")

class SemanticAddResponse(BaseModel):
    id: str = Field(..., example="obs_pattern_001")
    message: str = Field("Semantic entry added successfully.", example="Semantic entry added successfully.")

class SemanticQueryRequest(BaseModel):
    query_text: str = Field(..., min_length=1, example="patterns in data")
    top_k: Optional[int] = Field(5, gt=0, example=3)
    metadata_filter: Optional[Dict[str, Any]] = Field(None, example={"source": "observation"})

class SemanticQueryResponseItem(BaseModel):
    id: str
    text: str
    metadata: Dict[str, Any]
    distance: Optional[float] = None # ChromaDB includes this

class SemanticQueryResponse(BaseModel):
    results: List[SemanticQueryResponseItem]

class SemanticErrorResponse(BaseModel): # Can be used if vector store is unavailable
    error: str
    detail: Optional[str] = None


# --- Self Modification Schemas ---
class ProposeChangeRequestSchema(BaseModel):
    files_content: Dict[str, str] = Field(..., example={"src/main.py": "print('Hello, World!')"})
    commit_message: str = Field(..., min_length=5, example="feat: Implement new greeting feature")
    branch_prefix: Optional[str] = Field(None, example="feature")

class ProposalResponseSchema(BaseModel):
    proposal_id: str = Field(..., example="prop_123xyz")
    branch_name: str = Field(..., example="feature/prop_123xyz_new_greeting")
    status: str = Field(..., example="proposed")
    message: Optional[str] = Field(None, example="Proposal submitted and validation pending.")

class ProposalStatusResponseSchema(OrmBaseModel): # Enable ORM mode for reading from MemoryManager
    proposal_id: str
    branch_name: str
    commit_message: str
    status: str
    validation_output: Optional[str] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    approved_by: Optional[str] = None


# Add more Pydantic models as the API evolves.
