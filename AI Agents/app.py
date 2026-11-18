"""City Assistant backend: your agent + a FastAPI web API.
Run:  uvicorn app:app --reload   then open http://127.0.0.1:8000
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from tavily import TavilyClient
from langchain.tools import tool
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

# ---------- Tools ----------
@tool
def get_weather(city: str) -> str:
    """Get current weather of a city (include the country if not India)."""
    key = os.getenv("OPENWEATHER_API_KEY")
    if not key:
        return "Error: OPENWEATHER_API_KEY is not configured."
    try:
        r = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": key, "units": "metric"}, timeout=10)
        d = r.json()
    except (requests.RequestException, ValueError) as e:
        return f"Error connecting to weather service: {e}"
    if str(d.get("cod")) != "200":
        return f"Error: {d.get('message', 'Could not fetch weather')}"
    return (f"Weather in {d['name']}, {d['sys'].get('country', '')}: "
            f"{d['weather'][0]['description']}, {d['main']['temp']}°C "
            f"(feels like {d['main']['feels_like']}°C), humidity {d['main']['humidity']}%, "
            f"wind {d['wind']['speed']} m/s")

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY", ""))

@tool
def get_news(city: str) -> str:
    """Get latest news about a city."""
    try:
        res = tavily.search(query=f"latest news in {city}", topic="news",
                            search_depth="basic", max_results=4)
    except Exception as e:
        return f"Error fetching news: {e}"
    items = res.get("results", [])
    if not items:
        return f"No news found for {city}"
    return "\n\n".join(
        f"- {i.get('title')}\n  {i.get('url')}\n  {i.get('content', '')[:200]}" for i in items)

# ---------- Agent (approval now happens in the browser) ----------
agent = create_agent(
    ChatGroq(model="openai/gpt-oss-120b", temperature=0),
    tools=[get_weather, get_news],
    system_prompt=(
        "You are a helpful city assistant. Use get_weather for current weather and "
        "get_news for recent news. Reply concisely, and include news links as plain URLs."),
    middleware=[HumanInTheLoopMiddleware(
        interrupt_on={"get_weather": True, "get_news": True})],
    checkpointer=InMemorySaver(),   # remembers each chat session
)

# ---------- API ----------
app = FastAPI(title="City Assistant")

class ChatIn(BaseModel):
    thread_id: str
    message: str = Field(min_length=1, max_length=1000)

class DecisionIn(BaseModel):
    thread_id: str
    approve: bool

def _respond(result: dict) -> dict:
    """Turn an agent result into either a final answer or an approval request."""
    if result.get("__interrupt__"):
        value = result["__interrupt__"][0].value
        return {"type": "approval", "actions": [
            {"name": a["name"], "args": a["args"]} for a in value["action_requests"]]}
    return {"type": "message", "content": result["messages"][-1].content}

def _run(payload, thread_id: str) -> dict:
    try:
        cfg = {"configurable": {"thread_id": thread_id}}
        return _respond(agent.invoke(payload, config=cfg))
    except Exception as e:
        return {"type": "error", "content": f"{type(e).__name__}: {e}"}

@app.post("/api/chat")
def chat(body: ChatIn):
    return _run({"messages": [{"role": "user", "content": body.message}]}, body.thread_id)

@app.post("/api/decision")
def decision(body: DecisionIn):
    # Approve/deny every pending tool call together.
    snap = agent.get_state({"configurable": {"thread_id": body.thread_id}})
    pending = sum(len(i.value["action_requests"]) for t in snap.tasks for i in t.interrupts) or 1
    d = ({"type": "approve"} if body.approve
         else {"type": "reject", "message": "The user denied this tool call."})
    return _run(Command(resume={"decisions": [d] * pending}), body.thread_id)

@app.get("/")
def index():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")
