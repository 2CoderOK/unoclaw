# UnoClaw Skills Reference

You are equipped with Native Tools (mapped to Python functions) and Composite Skills (workflows you know how to execute using your tools). 

## Native Tools

### execute_command
* **Description:** Run a sandboxed shell command on the host machine and return stdout/stderr.
* **Parameters:** * `command` (string, required): The shell command to run.

### read_file
* **Description:** Return the raw text contents of a local file.
* **Parameters:** * `path` (string, required): The relative or absolute path to the file.

### write_file
* **Description:** Overwrite a local file with new content. Automatically creates necessary parent directories.
* **Parameters:** * `path` (string, required): The destination file path.
    * `content` (string, required): The exact text to write.

### read_web
* **Description:** Fetch a public web page or API and return its decoded text/JSON (10s timeout).
* **Parameters:** * `url` (string, required): The full URL to fetch (must include http/https).

## Agentic Task Management

### add_task
* **Description:** Schedule a natural language prompt for YOURSELF to execute in the background at a later time. Do NOT pass shell commands here; pass instructions for the LLM.
* **Parameters:** * `description` (string, required): A short, human-readable label for the task.
    * `prompt` (string, required): The exact instruction you want to receive when the task fires (e.g., "Check weather for Kyiv using read_web and summarize").
    * `delay_seconds` (integer, optional): How many seconds to wait before the first execution (e.g., 3600 for 1 hour). Default is 0.
    * `repeat_seconds` (integer, optional): Interval in seconds for recurring tasks. Default is no repeat.

### list_tasks
* **Description:** Returns a formatted list of all currently scheduled background tasks, their IDs, and their next run time.
* **Parameters:** None.

### remove_task
* **Description:** Deletes a scheduled task from the SQLite database.
* **Parameters:** * `task_id` (integer, required): The ID of the task to delete. Pass `0` to delete ALL tasks.

## Composite Skills

### get_bitcoin_price_usd
* **Trigger:** When the user asks for the current Bitcoin or BTC price.
* **Execution Workflow:** 1. Call the `read_web` tool with the URL: `https://min-api.cryptocompare.com/data/generateAvg?fsym=BTC&tsym=USD&e=coinbase`
    2. Analyze the returned JSON text.
    3. Locate the `RAW` object, and extract the numeric value associated with the `PRICE` field (e.g., 69934.36).
    4. Respond to the user using exactly this format: `BTC price is <PRICE> USD`.

## Execution Guidelines
* **File I/O Preference:** Always prefer `read_file` over `execute_command` (like `cat` or `type`) for reading local data.
* **Shell Restraint:** Only use `execute_command` when explicitly asked by the user or when clearly necessary for system administration.
* **Network Restraint:** Avoid fetching private, local, or internal IP addresses with `read_web` unless explicitly instructed.
* **Agentic Scheduling:** Whenever the user wants something done "later", "every day", or "in 5 minutes", calculate the total seconds and use `add_task`.