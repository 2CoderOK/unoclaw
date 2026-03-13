"""Tests for UnoClaw — run with: python -m pytest test_unoclaw.py -v"""

import os
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

# Import the module under test
import unoclaw.main as unoclaw


# ---------------------------------------------------------------------------
# Fixtures & State Reset
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def setup_test_env(tmp_path):
    """Reset module-level state and create a fresh SQLite DB for each test."""
    db_file = str(tmp_path / "test_unoclaw.db")

    unoclaw.WORKSPACE_ROOT = str(tmp_path)
    unoclaw.WORKSPACE_RESTRICT = False
    unoclaw.DB_PATH = db_file
    unoclaw._chats.clear()

    # Initialize fresh schema
    unoclaw.init_db(db_file)

    yield  # Run the test
    # tmp_path automatically cleans up the database file and files after the test


# ---------------------------------------------------------------------------
# Config Validation
# ---------------------------------------------------------------------------
class TestAppConfig:
    def test_valid_config(self):
        cfg = unoclaw.AppConfig(llm={"base_url": "http://localhost:8088/v1", "model": "test-model"})
        assert cfg.llm.model == "test-model"
        assert cfg.max_context_messages == 40

    def test_missing_llm_raises(self):
        with pytest.raises(ValidationError):
            unoclaw.AppConfig()  # llm is required

    def test_defaults(self):
        cfg = unoclaw.AppConfig(llm={"base_url": "http://localhost/v1", "model": "m"})
        assert cfg.telegram.token == ""
        assert cfg.workspace.restrict is False
        assert cfg.scheduler_interval == 10
        assert cfg.logging.level == "INFO"


# ---------------------------------------------------------------------------
# Shell & Web Tools
# ---------------------------------------------------------------------------
class TestStandardTools:
    def test_execute_command_success(self):
        result = unoclaw.execute_command("echo hello")
        assert "hello" in result.lower()

    def test_execute_command_workspace_restrict(self):
        unoclaw.WORKSPACE_RESTRICT = True
        # Attempting to navigate outside or absolute paths should be blocked
        result = unoclaw.execute_command("cd /tmp" if os.name != "nt" else "cd C:\\")
        assert "disallowed" in result.lower()

    def test_read_and_write_file(self, tmp_path):
        p = tmp_path / "test.txt"

        # Write
        res_write = unoclaw.write_file(str(p), "test content 123")
        assert res_write == "[Written]"

        # Read
        res_read = unoclaw.read_file(str(p))
        assert res_read == "test content 123"

    def test_read_file_not_found(self):
        result = unoclaw.read_file("/nonexistent/file_path.txt")
        assert "Error:" in result

    def test_workspace_restrict_blocks_outside(self, tmp_path):
        unoclaw.WORKSPACE_ROOT = str(tmp_path / "sandbox")
        unoclaw.WORKSPACE_RESTRICT = True
        os.makedirs(unoclaw.WORKSPACE_ROOT, exist_ok=True)

        outside_file = tmp_path / "outside.txt"
        result = unoclaw.read_file(str(outside_file))
        assert "disallowed" in result.lower()

    @patch("unoclaw.main.urlopen")
    def test_read_web_success(self, mock_urlopen):
        # Mock the urllib response
        mock_response = MagicMock()
        mock_response.read.return_value = b"Fake webpage content"
        mock_response.headers.get_content_charset.return_value = "utf-8"

        # Make the context manager work
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = unoclaw.read_web("https://example.com")
        assert "Fake webpage content" in result


# ---------------------------------------------------------------------------
# SQLite Memory Tools
# ---------------------------------------------------------------------------
class TestMemory:
    def test_save_and_search_memory(self):
        unoclaw.save_memory("User asked for the python version 3.10")
        unoclaw.save_memory("User likes chocolate cake")

        # Test finding existing memory
        result = unoclaw.search_memory("python version", limit=5)
        assert "3.10" in result
        assert "chocolate" not in result

    def test_search_memory_no_match_returns_empty(self):
        unoclaw.save_memory("User likes chocolate cake")
        result = unoclaw.search_memory("quantum physics", limit=5)
        assert result == ""


# ---------------------------------------------------------------------------
# SQLite Task Scheduler Tools
# ---------------------------------------------------------------------------
class TestTaskParsing:
    def test_add_list_and_remove_tasks(self):
        # Add a task
        res_add = unoclaw.add_task("test task", "echo hi", delay_seconds=60)
        assert "Task added with ID:" in res_add

        # List tasks
        tasks = unoclaw.list_tasks()
        assert "test task" in tasks
        assert "echo hi" in tasks

        # Parse the ID out of the first line (e.g. "[1] test task ...")
        task_id = int(tasks.split("]")[0].replace("[", ""))

        # Remove task
        res_remove = unoclaw.remove_task(task_id)
        assert "removed" in res_remove

        # Verify it's gone
        tasks_empty = unoclaw.list_tasks()
        assert "No tasks scheduled." in tasks_empty

    def test_remove_all_tasks(self):
        unoclaw.add_task("task1", "echo 1")
        unoclaw.add_task("task2", "echo 2")
        unoclaw.remove_task(0)  # 0 is the special code for "delete all"
        assert unoclaw.list_tasks() == "No tasks scheduled."


# ---------------------------------------------------------------------------
# Context Trimming Logic
# ---------------------------------------------------------------------------
class TestContextTrimming:
    def test_est_tokens(self):
        msgs = [{"role": "user", "content": "hello world!"}]
        # Approx: '{"role": "user", "content": "hello world!"}' is ~45 chars -> ~11 tokens
        tokens = unoclaw._est_tokens(msgs)
        assert tokens > 5 and tokens < 20

    def test_trim_context_by_count(self):
        history = [
            {"role": "system", "content": "sys1"},
            {"role": "system", "content": "sys2"},
            {"role": "user", "content": "msg1"},
            {"role": "user", "content": "msg2"},
            {"role": "user", "content": "msg3"},
        ]

        # Keep 2 system + 2 recent messages
        trimmed = unoclaw._trim_context(history, max_messages=2, max_tokens=1000)
        assert len(trimmed) == 4
        assert trimmed[0]["content"] == "sys1"
        assert trimmed[1]["content"] == "sys2"
        assert trimmed[2]["content"] == "msg2"
        assert trimmed[3]["content"] == "msg3"


# ---------------------------------------------------------------------------
# Agent Loop (Mocked LLM)
# ---------------------------------------------------------------------------
class TestAgent:
    @pytest.mark.asyncio
    async def test_run_agent_simple_reply(self):
        """Mock the OpenAI client to return a simple text reply."""

        # Setup mock LLM response
        mock_msg = MagicMock()
        mock_msg.role = "assistant"
        mock_msg.content = "Hello, human!"
        mock_msg.tool_calls = None

        mock_choice = MagicMock()
        mock_choice.message = mock_msg

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        cfg = unoclaw.AppConfig(
            llm={"base_url": "http://localhost/v1", "model": "test"},
        )

        reply = await unoclaw.run_agent(99, "hi", mock_client, cfg)

        # Verify the reply is correct
        assert reply == "Hello, human!"

        # Verify it auto-saved to SQLite memory
        mem = unoclaw.search_memory("Hello, human!", limit=1)
        assert "Hello, human!" in mem

    @pytest.mark.asyncio
    async def test_run_agent_llm_error(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("API Timeout")

        cfg = unoclaw.AppConfig(
            llm={"base_url": "http://localhost/v1", "model": "test"},
        )

        reply = await unoclaw.run_agent(99, "hi", mock_client, cfg)
        assert "LLM Error: API Timeout" in reply
