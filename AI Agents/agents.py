# Import all the files.

from dotenv import load_dotenv
import os
import requests

load_dotenv()

from langchain_groq import ChatGroq
from langchain.tools import tool
from langchain_core.messages import ToolMessage
from tavily import TavilyClient
from rich import print
from langchain.agents import create_agent
from langchain.agents.middleware import wrap_tool_call

# 🌦️ WEATHER TOOL

@tool
def get_weather(city: str) -> str:
    """Get current weather of a city."""

    api_key = os.getenv("OPENWEATHER_API_KEY")

    if not api_key:
        return "Error: OPENWEATHER_API_KEY is not configured."

    url = (
        "https://api.openweathermap.org/data/2.5/weather"
        f"?q={city},IN"
        f"&appid={api_key}"
        "&units=metric"
    )

    try:
        response = requests.get(url, timeout=10)
        data = response.json()

    except requests.RequestException as e:
        return f"Error connecting to weather service: {e}"

    if str(data.get("cod")) != "200":
        return f"Error: {data.get('message', 'Could not fetch weather')}"

    temp = data["main"]["temp"]
    feels_like = data["main"]["feels_like"]
    humidity = data["main"]["humidity"]
    desc = data["weather"][0]["description"]

    return (
        f"Weather in {city}:\n"
        f"Condition: {desc}\n"
        f"Temperature: {temp}°C\n"
        f"Feels like: {feels_like}°C\n"
        f"Humidity: {humidity}%"
    )


# =========================================================
# 📰 NEWS TOOL
# =========================================================

tavily_api_key = os.getenv("TAVILY_API_KEY")

if not tavily_api_key:
    raise ValueError("TAVILY_API_KEY is not configured in .env")

tavily_client = TavilyClient(
    api_key=tavily_api_key
)


@tool
def get_news(city: str) -> str:
    """Get latest news about a city."""

    try:
        response = tavily_client.search(
            query=f"latest news in {city}",
            search_depth="basic",
            max_results=3
        )

    except Exception as e:
        return f"Error fetching news: {e}"

    results = response.get("results", [])

    if not results:
        return f"No news found for {city}"

    news_list = []

    for r in results:
        title = r.get("title", "No title")
        url = r.get("url", "")
        snippet = r.get("content", "")

        news_list.append(
            f"- {title}\n"
            f"  🔗 {url}\n"
            f"  📝 {snippet[:150]}..."
        )

    return (
        f"Latest news in {city}:\n\n"
        + "\n\n".join(news_list)
    )


# =========================================================
# 🧠 GROQ LLM
# =========================================================

llm = ChatGroq(
    model="openai/gpt-oss-120b"
)


# =========================================================
# 👤 HUMAN APPROVAL MIDDLEWARE
# =========================================================

@wrap_tool_call
def human_approval(request, handler):
    """Ask for human approval before every tool call."""

    tool_name = request.tool_call["name"]

    print(
        f"\n[yellow]Agent wants to call tool:[/yellow] "
        f"[cyan]{tool_name}[/cyan]"
    )

    confirm = input("Approve? (yes/no): ")

    if confirm.lower() != "yes":

        print("[red]Tool call denied.[/red]")

        return ToolMessage(
            content="Tool call denied by user.",
            tool_call_id=request.tool_call["id"]
        )

    print("[green]Tool call approved.[/green]")

    return handler(request)


# =========================================================
# 🤖 CREATE AGENT
# =========================================================

agent = create_agent(
    llm,
    tools=[
        get_weather,
        get_news
    ],
    system_prompt=(
        "You are a helpful city assistant. "
        "You can provide current weather information "
        "and recent news about cities. "
        "Use the appropriate tool when necessary."
    ),
    middleware=[
        human_approval
    ]
)


# =========================================================
# 💬 CHAT LOOP
# =========================================================

print("\n[bold cyan]🌆 City Assistant[/bold cyan]")
print("[green]Weather + News Agent[/green]")
print("Type [bold]exit[/bold] to quit.\n")


while True:

    user_input = input("You: ")

    if user_input.lower().strip() == "exit":
        print("\n[cyan]Goodbye! 👋[/cyan]")
        break

    if not user_input.strip():
        continue

    try:

        result = agent.invoke({
            "messages": [
                {
                    "role": "user",
                    "content": user_input
                }
            ]
        })

        print("\n[bold green]Bot:[/bold green]")
        print(result["messages"][-1].content)
        print()

    except Exception as e:

        print(
            f"\n[red]Error:[/red] {e}\n"
        )