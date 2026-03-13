"""UnoClaw — minimalistic AI assistant with tool-calling, Telegram & CLI.

A single-file AI agent powered by an OpenAI-compatible LLM.
Supports sandboxed shell commands, file I/O, web fetching, persistent
SQLite memory and an agentic background task scheduler.
"""

import argparse
import asyncio
import json
import logging
import re
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from openai import OpenAI
from pydantic import BaseModel, Field, ValidationError

try:
    from telegram import Update
    from telegram.ext import ApplicationBuilder, MessageHandler, filters
except ImportError:
    Update = None  # Telegram features will be disabled if python-telegram-bot is not installed

__version__ = "0.1.1"
logger = logging.getLogger("unoclaw")


# ---------------------------------------------------------------------------
# --- Configuration Models ---
# ---------------------------------------------------------------------------
class TelegramCfg(BaseModel):
    token: str = ""
    allowed_usernames: list[str] = []


class LLMCfg(BaseModel):
    base_url: str
    api_key: str = "not-needed"
    model: str


class LoggingCfg(BaseModel):
    enabled: bool = True
    file: str = "unoclaw.log"
    level: str = "INFO"


class WorkspaceCfg(BaseModel):
    path: str = "."
    restrict: bool = False


class MemoryCfg(BaseModel):
    search_max_results: int = 10


class AppConfig(BaseModel):
    telegram: TelegramCfg = TelegramCfg()
    llm: LLMCfg
    system_prompt: str = "You are UnoClaw - personal AI assistant. Use your tools to help the user."
    logging: LoggingCfg = LoggingCfg()
    workspace: WorkspaceCfg = WorkspaceCfg()
    scheduler_interval: int = 10
    memory: MemoryCfg = MemoryCfg()
    db_name: str = "unoclaw.db"
    max_context_messages: int = Field(40, description="Max messages kept per chat")
    max_context_tokens: int = Field(8000, description="Soft token budget for conversation history")
    tools_schema: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# --- Globals ---
# ---------------------------------------------------------------------------
WORKSPACE_ROOT: Path = Path(".")
WORKSPACE_RESTRICT: bool = False
DB_PATH: Path = Path("unoclaw.db")
TG_TOKEN = ""


# ---------------------------------------------------------------------------
# --- Database & Memory Logic ---
# ---------------------------------------------------------------------------
def init_db(db_path: str):
    """Initialize the SQLite schema for memory and scheduling."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT,
                command TEXT NOT NULL,
                due_date DATETIME,
                repeat_seconds INTEGER,
                last_run DATETIME
            )
        """)


def save_memory(content: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO memory (content) VALUES (?)", (content,))


def search_memory(query: str, limit: int) -> str:
    """Basic keyword LIKE search against memory."""
    keywords = [w for w in query.split() if len(w) > 3][:4]
    if not keywords:
        return ""

    conditions = " OR ".join(["content LIKE ?"] * len(keywords))
    params = [f"%{k}%" for k in keywords]

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            f"SELECT content FROM memory WHERE ({conditions}) ORDER BY timestamp DESC LIMIT ?",
            params + [limit],
        )
        return "\n---\n".join(r[0] for r in cur.fetchall())


# ---------------------------------------------------------------------------
# --- Native Tools ---
# ---------------------------------------------------------------------------
def _in_workspace(path: str) -> bool:
    try:
        return Path(path).resolve().is_relative_to(WORKSPACE_ROOT.resolve())
    except Exception:
        return False


def execute_command(command: str) -> str:
    try:
        if WORKSPACE_RESTRICT and re.search(r"[A-Za-z]:\\|^/|\bcd\b\s+", command):
            return "Error: command disallowed under workspace restriction"
        res = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=WORKSPACE_ROOT if WORKSPACE_RESTRICT else None,
        )
        return ((res.stdout or "") + (res.stderr or "")).strip() or "[Success]"
    except Exception as e:
        return f"Error: {e}"


def read_file(path: str) -> str:
    try:
        if WORKSPACE_RESTRICT and not _in_workspace(path):
            return "Error: disallowed"
        with Path(path).open("r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error: {e}"


def write_file(path: str, content: str) -> str:
    try:
        if WORKSPACE_RESTRICT and not _in_workspace(path):
            return "Error: disallowed"
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with Path(path).open("w", encoding="utf-8") as f:
            f.write(content)
        return "[Written]"
    except Exception as e:
        return f"Error: {e}"


def read_web(url: str) -> str:
    try:
        req = Request(url, headers={"User-Agent": f"unoclaw/{__version__}"})
        with urlopen(req, timeout=10) as r:
            return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    except Exception as e:
        return f"Error: {e}"


def add_task(
    description: str, prompt: str, delay_seconds: int = 0, repeat_seconds: int = None
) -> str:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                "INSERT INTO tasks (description, command, due_date, repeat_seconds) VALUES (?, ?, datetime('now', 'localtime', ?), ?)",
                (description, prompt, f"+{delay_seconds or 0} seconds", repeat_seconds),
            )
            conn.commit()
            return f"[Task added with ID: {cur.lastrowid}. Will trigger in {delay_seconds or 0} seconds]"
    except Exception as e:
        return f"Error: {e}"


def list_tasks() -> str:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.execute(
                "SELECT id, description, command, due_date, repeat_seconds, last_run FROM tasks"
            )
            rows = cur.fetchall()
            if not rows:
                return "No tasks scheduled."
            return "\n".join(
                [
                    f"[{r[0]}] {r[1]} | Cmd: {r[2]} | Due: {r[3]} | Repeat: {r[4]}s | Last: {r[5]}"
                    for r in rows
                ]
            )
    except Exception as e:
        return f"Error: {e}"


def remove_task(task_id: int) -> str:
    logger.debug(f"Attempting to remove task {task_id}")
    try:
        with sqlite3.connect(DB_PATH) as conn:
            if task_id == 0:
                conn.execute("DELETE FROM tasks")
            else:
                conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()
            return f"[Task {task_id} removed]"
    except Exception as e:
        return f"Error: {e}"


TOOLS_MAP = {
    "execute_command": execute_command,
    "read_file": read_file,
    "write_file": write_file,
    "read_web": read_web,
    "add_task": add_task,
    "list_tasks": list_tasks,
    "remove_task": remove_task,
}


# ---------------------------------------------------------------------------
# --- Background Scheduler ---
# ---------------------------------------------------------------------------
def _notify(text: str):
    active_chats = list(_chats.keys())
    if not active_chats:
        return

    chat_id = active_chats[0]
    if not TG_TOKEN:
        print(f"\n[Task notification] {text}\nYou: ", end="", flush=True)
        return

    try:
        req = Request(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data=json.dumps({"chat_id": chat_id, "text": text}).encode(),
            headers={"Content-Type": "application/json"},
        )
        urlopen(req, timeout=5)
    except Exception as e:
        logger.error(f"Notify err: {e}")


def _scheduler_loop(interval: int, client: OpenAI, cfg: AppConfig):
    while True:
        try:
            active_chats = list(_chats.keys())
            chat_id = (
                active_chats[0] if active_chats else 0
            )  # Use 0 for CLI mode or if no active Telegram chats

            with sqlite3.connect(DB_PATH) as conn:
                cur = conn.execute("""
                    SELECT id, command, repeat_seconds FROM tasks 
                    WHERE (last_run IS NULL AND (due_date IS NULL OR due_date <= datetime('now','localtime')))
                       OR (last_run IS NOT NULL AND repeat_seconds IS NOT NULL 
                           AND datetime(last_run, '+' || repeat_seconds || ' seconds') <= datetime('now','localtime'))
                """)
                for tid, prompt, rep in cur.fetchall():
                    logger.info(f"Triggering Agent Task {tid} -> {prompt}")

                    if chat_id is not None:
                        # The scheduler literally messages the LLM in the background!
                        agent_prompt = f"[SYSTEM: AUTOMATED BACKGROUND TASK TRIGGERED]: {prompt}. Execute this and summarize the result."
                        res = asyncio.run(run_agent(chat_id, agent_prompt, client, cfg))
                        _notify(f"🔔 Task [{tid}] completed:\n\n{res}")

                    if rep:
                        conn.execute(
                            "UPDATE tasks SET last_run = datetime('now','localtime') WHERE id = ?",
                            (tid,),
                        )
                    else:
                        conn.execute("DELETE FROM tasks WHERE id = ?", (tid,))
                conn.commit()
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
        time.sleep(interval)


# ---------------------------------------------------------------------------
# --- Agent Core ---
# ---------------------------------------------------------------------------
_chats: dict[int, list[dict[str, Any]]] = {}


def _est_tokens(messages: list) -> int:
    """Estimate token count using ~4 chars per token heuristic."""
    return sum(len(json.dumps(m)) for m in messages) // 4


def _trim_context(history: list, max_messages: int, max_tokens: int) -> list:
    """Keep fixed slots [0,1] (system prompts) + trim conversation by count then tokens."""
    prefix, convo = history[:2], history[2:]
    convo = convo[-max_messages:]
    while _est_tokens(prefix + convo) > max_tokens and len(convo) > 1:
        convo.pop(0)
    return prefix + convo


async def run_agent(chat_id: int, text: str, client: OpenAI, cfg: AppConfig) -> str:
    if chat_id not in _chats:
        _chats[chat_id] = [
            {"role": "system", "content": cfg.system_prompt},
            {"role": "system", "content": ""},
        ]

    parts = [
        f"RELEVANT MEMORY:\n{m}" for m in [search_memory(text, cfg.memory.search_max_results)] if m
    ]
    _chats[chat_id][1] = {"role": "system", "content": "\n\n".join(parts)}
    _chats[chat_id].append({"role": "user", "content": text})

    while True:
        try:
            _chats[chat_id] = _trim_context(
                _chats[chat_id], cfg.max_context_messages, cfg.max_context_tokens
            )
            res = client.chat.completions.create(
                model=cfg.llm.model,
                messages=_chats[chat_id],
                tools=cfg.tools_schema,
                tool_choice="auto",
            )
            msg = res.choices[0].message

            # Convert object to pure dict immediately to prevent Pydantic parsing crashes later
            msg_dict = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                msg_dict["tool_calls"] = [tc.model_dump() for tc in msg.tool_calls]
            _chats[chat_id].append(msg_dict)

            if not msg.tool_calls:
                if msg.content:
                    save_memory(f"User: {text}\nAgent: {msg.content}")
                return msg.content or ""

            for tc in msg.tool_calls:
                fn = getattr(tc, "function", tc)
                name = (
                    fn.get("name") if isinstance(fn, dict) else getattr(fn, "name", None)
                ) or "error"
                raw = (
                    fn.get("arguments") if isinstance(fn, dict) else getattr(fn, "arguments", None)
                )
                args = raw if isinstance(raw, dict) else (json.loads(raw) if raw else {})

                result = await asyncio.to_thread(
                    TOOLS_MAP.get(name, lambda **k: f"Unknown tool: {name}"),
                    **(args or {}),
                )
                logger.debug(f"Tool {name} -> {str(result)[:100]}")

                _chats[chat_id].append(
                    {
                        "role": "tool",
                        "tool_call_id": getattr(tc, "id", None),
                        "name": name,
                        "content": str(result),
                    }
                )
        except Exception as e:
            return f"LLM Error: {e}"


# ---------------------------------------------------------------------------
# --- Telegram & CLI Lifecycle ---
# ---------------------------------------------------------------------------
async def _tg_handle(update: "Update", ctx: Any):
    bd = ctx.application.bot_data
    if update.effective_user.username not in bd["cfg"].telegram.allowed_usernames:
        return
    await ctx.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    reply = await run_agent(update.effective_chat.id, update.message.text, bd["client"], bd["cfg"])
    await update.message.reply_text(reply)


def main():
    global WORKSPACE_ROOT, WORKSPACE_RESTRICT, DB_PATH, TG_TOKEN

    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", default="config.json")
    cfg_path = Path(parser.parse_args().config)

    try:
        with cfg_path.open(encoding="utf-8") as f:
            raw_cfg = json.load(f)
    except FileNotFoundError:
        logger.error("Config file not found: %s", cfg_path)
        exit(1)
    except Exception as e:
        logger.error("Failed to load config %s: %s", cfg_path, e)
        exit(1)

    try:
        cfg = AppConfig(**raw_cfg)
    except ValidationError as e:
        exit(f"Config error:\n{e}")

    if not cfg.tools_schema:
        logger.warning("No tools schema found in config.")

    level = getattr(logging, cfg.logging.level.upper(), logging.INFO)
    handlers = [logging.StreamHandler()]

    if cfg.logging.enabled:
        log_path = WORKSPACE_ROOT / cfg.logging.file
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    logging.basicConfig(
        level=level, format="%(asctime)s %(levelname)s %(message)s", handlers=handlers
    )

    WORKSPACE_ROOT = Path(cfg.workspace.path).resolve()
    WORKSPACE_RESTRICT = cfg.workspace.restrict
    DB_PATH = WORKSPACE_ROOT / cfg.db_name
    TG_TOKEN = cfg.telegram.token

    init_db(DB_PATH)
    client = OpenAI(base_url=cfg.llm.base_url, api_key=cfg.llm.api_key)

    # Start the background task scheduler
    threading.Thread(
        target=_scheduler_loop, args=(cfg.scheduler_interval, client, cfg), daemon=True
    ).start()

    logger.info(f"UnoClaw {__version__} loaded. DB: {DB_PATH}")

    # Auto-inject AGENT.md and SKILLS.md into the system prompt
    for doc in ["docs/AGENT.md", "docs/SKILLS.md"]:
        doc_path = Path(__file__).parent / doc
        if doc_path.exists():
            with doc_path.open(encoding="utf-8") as f:
                cfg.system_prompt += "\n\n" + f.read()

    if cfg.telegram.token and Update and "YOUR_TELEGRAM_BOT_TOKEN" not in cfg.telegram.token:
        app = ApplicationBuilder().token(cfg.telegram.token).build()
        app.bot_data.update({"cfg": cfg, "client": client})
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _tg_handle))
        app.run_polling()
    else:
        print("CLI mode active. Ctrl-C to exit.")
        try:
            while True:
                if text := input("You: ").strip():
                    print("Bot:", asyncio.run(run_agent(0, text, client, cfg)))
        except KeyboardInterrupt:
            print("\nOffline.")


if __name__ == "__main__":
    main()
