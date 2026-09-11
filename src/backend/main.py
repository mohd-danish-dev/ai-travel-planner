"""
FastAPI backend for the Singapore travel assistant.

Run with:
    uvicorn main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import memory
from mcp_client import MCPToolClients
from orchestrator import handle_message

mcp_clients = MCPToolClients()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await mcp_clients.start()
    yield
    await mcp_clients.stop()


app = FastAPI(title="Singapore Travel Assistant API", lifespan=lifespan)

# The Streamlit UI (src/ui) runs as a separate process/port during local dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    answer: str
    intent: str
    sources: list[dict]
    tools_called: list[str]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    result = await handle_message(req.session_id, req.message, mcp_clients)
    return result


@app.post("/reset")
def reset(session_id: str):
    memory.clear_session(session_id)
    return {"status": "cleared"}
