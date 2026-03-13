<p align="center">
  <img src="https://raw.githubusercontent.com/2coderok/unoclaw/main/assets/unoclaw_text_logo.png" alt="UnoClaw" width="500">
</p>

<h1 align="center">🦾 UnoClaw — Minimalistic AI Assistant</h1>

<p align="center">
  <strong>SINGLE FILE. CONFIG-DRIVEN. SQLITE MEMORY.</strong>
</p>

<p align="center">
  <a href="#"><img src="https://img.shields.io/badge/Python-3.10+-yellow.svg?style=for-the-badge" alt="Python 3.10+"></a>
  <a href="#"><img src="https://img.shields.io/badge/Dependencies-Pydantic%20%7C%20OpenAI-blue.svg?style=for-the-badge" alt="Dependencies"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="MIT License"></a>
</p>

**UnoClaw** is a _lightweight, self-contained, single file AI agent_ that runs locally. 
It answers you on **Telegram** or via an interactive **CLI**. It connects to any OpenAI-compatible LLM (local or remote), manages a permanent SQLite memory, triggers its own background tasks, and exposes a set of sandboxed tools the model can call autonomously — all in under 500 lines of Python (with ~60 of those being just comments and extra whitespace for readability)

Inspired by **OpenClaw** and the minimalist philosophy of  **NanoBot**, we put a strong emphasis on **simplicity and readability**. Because the entire core logic lives in a single file, you can easily read it from top to bottom, hack it to your exact needs, or use it as a learning resource to understand how AI agents and tool-calling work under the hood.

Check it out if you want to play around with AI driven assistant that is highly hackable, requires zero external databases and lives in a single file.

[GitHub Repository](https://github.com/2coderok/unoclaw) · [Installation](#installation) · [Quick Start](#quick-start-tldr) · [Configuration](#configuration) · [Extending & Tools](#extending-unoclaw-adding-skills--tools) · [Security](#security-model-important)

## Installation

Runtime: **Python ≥ 3.10**.

### 🚀 Using uv (Recommended)
[uv](https://github.com/astral-sh/uv) is the fastest way to install and manage **unoclaw**.

**As a global tool with Telegram:**
```bash
uv tool install unoclaw --with "unoclaw[telegram]"
```

**As a global tool CLI only (no Telegram):**
```bash
uv tool install unoclaw
```

### From PyPI with Telegram
```bash
pip install "unoclaw[telegram]"
```

### From PyPI without Telegram
```bash
pip install unoclaw
```

### From Source (For Hacking/Development)
If you want to modify the code or contribute, we recommend using uv for a seamless experience:
```bash
git clone [https://github.com/2coderok/unoclaw.git](https://github.com/2coderok/unoclaw.git)
cd unoclaw

# Create environment and install all dependencies (including dev tools)
uv sync --all-extras
```

Alternatively, using standard pip:
```bash
git clone [https://github.com/2coderok/unoclaw.git](https://github.com/2coderok/unoclaw.git)
cd unoclaw

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # (Windows: .venv\Scripts\activate)

# Install in editable mode with Telegram and Dev support
pip install -e ".[telegram,dev]"
```

## Quick start (TL;DR)

1. **Configure:** Copy the example config and add your llm endpoint/telegram settings.
   ```bash
   cp config.example.json config.json
   ```
2. **Run:** Start the agent in your terminal using the conifg.
   ```bash
   unoclaw --config path/to/your/config.json
   ```

   UnoClaw will look for `config.json` in current working directory if --config was not provided.

If you provided a `telegram.token`, it will start polling immediately. If omitted, it will drop you into the interactive CLI mode. 

## Highlights

- **Agentic Scheduler** — Background loop triggers the LLM to autonomously perform scheduled prompts.
- **SQLite Memory** — Seamless, permanent conversation and task storage without messy text files.
- **Tool-calling** — The LLM can execute shell commands, read/write files, and fetch web pages.
- **Telegram + CLI** — Runs as a Telegram bot; falls back to CLI when no token is configured.
- **Workspace sandboxing** — Optionally restricts all file and command access to a single directory.
- **Async tool dispatch** — Tool functions run in threads via `asyncio.to_thread()`.

## Everything we built so far

### Core platform
- **Context trimming:** Chat history is automatically trimmed by message count and token heuristics (`max_context_tokens`, `max_context_messages`).
- **Config validation:** Pydantic models validate `config.json` at startup with clear error messages.
- **Agent Loop:** Handles native tool-calling natively through the official OpenAI SDK structure. 

### Memory & Persistence
- **Automatic Storage:** Every time the LLM replies to the user, the exchange is automatically saved to the `memory` SQLite table.
- **On-Demand Recall:** When the user sends a new message, UnoClaw scans it for keywords, queries the database, and invisibly injects relevant historical memories directly into the LLM's system prompt.

### Tools + automation
- **Native Tools:** `execute_command`, `read_file`, `write_file`, `read_web`.
- **Task Management:** `add_task`, `list_tasks`, `remove_task`.
- **Agentic Cron:** Unlike traditional schedulers, UnoClaw saves *natural language prompts* to the DB. When the timer hits zero, the background thread wakes up and messages the LLM: `[SYSTEM: AUTOMATED BACKGROUND TASK TRIGGERED]: <prompt>`. The agent autonomously executes tools and sends you a message with the result.

## How it works (short)

```text
 Telegram / CLI User
        │
        ▼
┌───────────────────────────────┐
│           UnoClaw             │◄── config.json
│          (main.py)            │   (API Keys, Settings, Tools)
│  [Memory & Scheduler loop]    │
└──────────────┬────────────────┘
        │      │
        │      ├─ Tools (Shell, Web, File I/O)
        │      └─ SQLite DB (unoclaw.db)
        ▼
 OpenAI-Compatible LLM
```

## Supported LLMs

Because UnoClaw uses the standard OpenAI SDK with a configurable `base_url`, it supports **virtually any Large Language Model** that exposes an OpenAI-compatible API endpoint. 

This means you are not locked into a single provider. You can seamlessly switch between local open-source models and powerful cloud APIs just by changing two lines in your `config.json`.

### Local Inference Engines (Free & Private)
If you have the hardware, you can run models entirely locally. Just point UnoClaw's `base_url` to your local server:
- **Ollama:** `http://localhost:11434/v1` (Supports Llama 3, Qwen, Mistral, Phi, etc.)
- **LM Studio:** `http://localhost:1234/v1`
- **vLLM:** `http://localhost:8000/v1`
- **Llama.cpp (Server):** `http://localhost:8080/v1`
- **Text-Generation-WebUI (Oobabooga):** `http://localhost:5000/v1`

### Cloud API Providers
If you want to use hosted models, just paste your API key and their base URL into the config:
- **OpenAI:** GPT-4o, GPT-4-turbo, GPT-3.5
- **Groq:** Ultra-fast inference for open-source models (Llama 3, Mixtral)
- **OpenRouter:** Access to hundreds of models including Claude, Gemini, and DeepSeek through a single unified API.
- **Together AI:** Hosted open-source models.
- **DeepSeek:** Direct API access to DeepSeek models.
- **Mistral API:** Direct access to Mistral Large, Nemo, etc.

### Minimum Model Requirements
To fully utilize UnoClaw's features, the model you choose **must support Tool Calling (Function Calling)**. 
- *Recommended Open-Source:* Qwen 2.5 (Instruct), Llama 3.1 (Instruct), or Mistral Nemo. 
- *Recommended Cloud:* GPT-4o, Claude 3.5 Sonnet (via OpenRouter), or Groq-hosted Llama 3.1.

## Configuration

Settings live in `config.json`. Missing required fields (like `llm`) will produce a clear validation error on startup.

```json5
{
  "telegram": {
    "token": "YOUR_BOT_TOKEN",
    "allowed_usernames": ["your_handle"]
  },
  "llm": {
    "base_url": "http://localhost:8088/v1",
    "model": "qwen2.5-7b-instruct",
    "api_key": "not-needed"
  },
  "workspace": {
    "path": ".",
    "restrict": true
  },
  "max_context_tokens": 8000,
  "max_context_messages": 40
}
```

### Context Limits & Soft Token Budgets
To prevent runaway API costs and context-window crashes, UnoClaw manages conversation history using a soft token budget:
- `max_context_tokens`: UnoClaw estimates the token count of your active conversation. If it exceeds this limit, it automatically prunes the oldest messages (while always preserving your system prompts).
- `max_context_messages`: The absolute maximum number of back-and-forth messages kept in the active LLM context before older messages are trimmed.

*Note: For the full schema, check `config.example.json`.*

## The System Prompt (`AGENT.md` & `SKILLS.md`)

UnoClaw builds its system prompt dynamically on startup by reading two markdown files from the `docs/` directory. You can (and should) edit these to completely customize your assistant.

### `docs/AGENT.md` (Core Personality & Rules)
This file defines *who* the agent is, its core rules, and its constraints. Use this file to set the agent's behavior:
* **Personality:** e.g., "You are a sarcastic but highly skilled DevOps engineer."
* **Formatting Rules:** e.g., "Always provide code snippets without markdown blocks."
* **Environment Context:** Tell the LLM what OS it is running on! Add a line like `You are running on Windows 11 using PowerShell.` or `You are running on Ubuntu Linux 22.04.` to ensure it uses the correct syntax (`dir` vs `ls`) when executing autonomous shell commands.

### `docs/SKILLS.md` (Tool Documentation)
This file defines *what* the agent can do. It is appended directly below the `AGENT.md` text and contains the documentation for your Native Tools and the step-by-step logic for your Composite Skills (detailed in the next section).

## Extending UnoClaw (Adding Skills & Tools)

UnoClaw is designed to be highly hackable. You can give it new superpowers in two ways: by writing plain English workflows (Composite Skills) or by writing native Python functions (Native Tools).

### 1. The "No-Code" Way: Composite Skills
Because UnoClaw connects to powerful LLMs, you do not need to write a new Python script for every minor feature. You can simply teach the agent a "workflow" by editing the `SKILLS.md` file and instructing it to use its existing tools (like `read_web` or `read_file`).

To add a new skill, just append a clear, step-by-step instruction block to `SKILLS.md`.

**Example: Adding a Bitcoin Price Tracker**
Paste the following into your `SKILLS.md` file. UnoClaw will read this and instantly know how to pull real-time crypto prices without any new Python code:

```markdown
### get_bitcoin_price_usd
* **Trigger:** When the user asks for the current Bitcoin or BTC price.
* **Execution Workflow:** 1. Call the `read_web` tool with the URL: `https://min-api.cryptocompare.com/data/generateAvg?fsym=BTC&tsym=USD&e=coinbase`
    2. Analyze the returned JSON text.
    3. Locate the `RAW` object, and extract the numeric value associated with the `PRICE` field.
    4. Respond to the user using exactly this format: `BTC price is <PRICE> USD`.
```

### 2. The Python Way: Native Tools
If you need UnoClaw to interact with a specific local database, control hardware, or execute complex logic, you can easily add a native tool directly inside `unoclaw.py`.

**Step 1: Define your Python function**
Write your function inside `unoclaw.py`. **Crucially**, you must include type hints and a clear docstring. UnoClaw parses this to automatically generate the tool schema for the LLM.

```python
def get_system_uptime() -> str:
    """
    Returns the current uptime of the host machine.
    Call this when the user asks how long the server has been running.
    """
    import uptime
    return f"System has been running for {uptime.uptime()} seconds."
```

**Step 2: Register the tool**
Find the `available_tools` dictionary in `unoclaw.py` and map your new function:

```python
available_tools = {
    "execute_command": execute_command,
    "read_file": read_file,
    "write_file": write_file,
    "read_web": read_web,
    "get_system_uptime": get_system_uptime, # <-- Your new tool registered here
}
```

**Step 3: Document the tool for the LLM**
Finally, open your `AGENT.md` or `SKILLS.md` file and add an entry so the LLM knows the tool exists, what it does, and what parameters it requires. 

Add this to `SKILLS.md` under the Native Tools section:

```markdown
### get_system_uptime
* **Description:** Returns the current uptime of the host machine in seconds. Use this when asked about server status or uptime.
* **Parameters:** None.
```

## Security model (important)

UnoClaw connects to your host environment. Treat tool access with care!

- **Workspace restriction:** When `workspace.restrict` is `true`, the agent cannot access files outside `workspace.path`, run `cd` commands with absolute paths, or make network requests.
- **Allowed usernames:** In Telegram mode, only users listed in `telegram.allowed_usernames` can interact with the bot. Any other user is silently ignored.
- **Shell access:** The `execute_command` tool runs arbitrary shell commands. Use workspace restriction and allowed-user lists to limit exposure.
- **No credential storage:** Never commit `config.json` to version control.

## Project Structure

```text
unoclaw/
├── LICENSE                    # License file
├── README.md                  # This file
├── pyproject.toml             # Build configuration
├── .gitignore
├── assets/
│   └── unoclaw_text_logo.png  # UnoClaw logo
├── tests/
│   └── test_unoclaw.py        # Test suite (pytest)
└── unoclaw/            
    ├── __init__.py
    ├── main.py                # The entire agent — single file
    ├── config.example.json    # Template configuration
    └── docs/           
        ├── AGENT.md           # Auto-loaded agent instructions
        └── SKILLS.md          # Auto-loaded agent skills
```
