# Assistant - AI Personal Desktop Assistant

A feature-rich, local AI-powered personal assistant desktop application built with Python and PyQt5, integrated with Ollama for running open-source language models locally.

## 🎯 Overview

Assistant is a desktop application that provides an intelligent conversational interface to help you with tasks, searches, scheduling, and more. It runs entirely on your local machine using Ollama, ensuring your conversations remain private and on-device.

### Key Features

- **🤖 Local LLM Integration**: Uses Ollama with support for models like Qwen2.5:7b
- **💬 Conversation Management**: Full conversation history with session persistence
- **🧠 Memory System**: Stores important information and integrates with prompts
- **🔊 Text-to-Speech**: Built-in TTS for audio responses
- **🎯 Intent Detection**: Intelligent intent recognition for user commands
- **🛠️ Extensible Tools**: Registry system for adding new tools and capabilities
- **📧 Plugin Support**: Gmail plugin and plugin manager for extensibility
- **🔍 Smart Search**: Conversation search and file search tools
- **♿ Accessibility**: Full accessibility support for screen readers and keyboard navigation
- **⌨️ Global Hotkeys**: Quick access to assistant from anywhere on your system
- **🔐 Privacy-First**: All processing happens locally, no cloud dependencies
- **📊 Health Monitoring**: Built-in health checks and crash recovery

## 📋 Requirements

- Python 3.8+
- Windows OS (primary support)
- 4GB RAM minimum (8GB+ recommended)
- Ollama installed and running

## 🚀 Installation

### 1. Install Ollama

Download and install [Ollama](https://ollama.ai) from the official website.

### 2. Clone and Setup

```bash
cd e:\Assistant
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Model

Update `config.json` to specify your preferred model:

```json
{
  "model": "qwen2.5:7b",
  "auto_start": false,
  "theme": "dark",
  "notifications": true,
  "stream_responses": true
}
```

### 4. Run Ollama

```bash
ollama serve
```

In a separate terminal, pull your desired model:

```bash
ollama pull qwen2.5:7b
```

### 5. Start the Assistant

```bash
python main.py
```

Or execute the batch file:

```bash
run.bat
```

---

## 📚 Complete Codebase Documentation for AI Integration

This section contains detailed architectural information, data structures, and implementation details for AI systems to fully understand and work with the codebase.

### Architecture Overview

```
User Input
    ↓
[Intent Detection Engine] → classifies user intent + confidence
    ↓
[Command Router] → route to tool or LLM
    │
    ├→ [Tool Registry] → system actions, file ops, etc.
    │
    └→ [LLM Pipeline]
         ├→ [Memory Service] → load relevant context
         ├→ [Conversation Service] → build message history
         └→ [Prompt Builder] → combine memory + history + user input
              ↓
         [Ollama/LLM] → generate response
              ↓
         [Response Storage] → save to session
              ↓
         [TTS Service] (optional) → speak response
              ↓
         User Output
```

---

## 🔄 Core Workflow and Data Flow

### 1. Main Entry Point (`main.py`)

The application starts by suppressing Qt warnings and loading the UI:

```python
import os
import sys
import ctypes

# Redirect stderr to suppress Qt C++ warnings on Windows
if sys.platform == "win32":
    _devnull = open(os.devnull, "w")
    _old_stderr_fd = os.dup(2)
    os.dup2(_devnull.fileno(), 2)

os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.qpa.window=false"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

from ui.main_window import main  # UI loads here

# Restore stderr
if sys.platform == "win32":
    os.dup2(_old_stderr_fd, 2)
    os.close(_old_stderr_fd)
    _devnull.close()

main()
```

**Key Points:**
- Disables Qt C++ debug output on Windows
- Enables High DPI scaling for modern displays
- Loads PyQt5 UI after error redirection

---

### 2. Assistant Core Logic (`core/assistant.py`)

#### Memory Prompt Building

The assistant augments user input with stored memory context:

```python
def build_memory_prompt(user_input):
    """
    Loads user memory and creates a prompt that includes:
    - System prompt (you are a personal assistant)
    - User's stored memory (name, preferences, etc.)
    - Current user message
    """
    memory_data = load_memory()  # Returns dict from memory.json
    
    if not memory_data:
        return user_input
    
    memory_lines = []
    for key, value in memory_data.items():
        memory_lines.append(f"{key}: {value}")
    
    memory_text = "\n".join(memory_lines)
    
    prompt = f"""
You are a personal assistant.

Use stored memory when relevant.

Memory:

{memory_text}

User message:

{user_input}

Respond naturally.
"""
    return prompt.strip()
```

**Data Structures:**
- `memory_data`: Dictionary with keys like `name`, `role`, `location`, `age`, `likes`
- `prompt`: String combining system instructions + memory + user input

#### LLM Communication

```python
def ask_llm(user_input):
    """
    Main LLM communication pipeline:
    1. Build augmented prompt with memory
    2. Fetch conversation history
    3. Call Ollama API
    4. Store response in session
    """
    prompt = build_memory_prompt(user_input)
    history = get_history()  # List of {"role": "user"|"assistant", "content": "..."}
    
    messages = history + [
        {
            "role": "user",
            "content": prompt
        }
    ]
    
    # Call Ollama backend (localhost:11434)
    response = ollama.chat(
        model=MODEL,  # e.g., "qwen2.5:7b"
        messages=messages
    )
    
    assistant_reply = response["message"]["content"]
    
    # Save to active session
    add_message("assistant", assistant_reply)
    
    return assistant_reply
```

**Message Format (OpenAI-compatible):**
```json
{
  "role": "user" | "assistant",
  "content": "message text"
}
```

#### Command Router

```python
def handle_command(text):
    """
    Routes commands to either tools or LLM:
    1. Add message to conversation history
    2. Detect user intent
    3. Lookup tool in registry
    4. Execute tool or fallback to LLM
    """
    text_lower = text.lower().strip()
    add_message("user", text)
    
    intent = detect_intent(text_lower)  # Returns (intent_name, confidence)
    tool = registry.get(intent)  # Look up in tool registry
    
    if tool:
        return tool(text)  # Execute tool function
    
    return ask_llm(text)  # Fallback to LLM
```

---

### 3. Intent Detection Engine (`core/intent_engine.py`)

The intent engine classifies user commands with pattern matching:

```python
def detect_intent(text):
    """
    Pattern-based intent detection.
    Returns: (intent_name: str, confidence: float)
    Confidence: 0.0 = unknown, 1.0 = certain
    """
    text = text.lower().strip()
    
    # Exit intents
    if text in ["exit", "quit"]:
        return "exit", 1.0
    
    # Memory intents
    if text.startswith("remember"):
        return "remember", 0.97
    
    if any(phrase in text for phrase in ["show memory", "what do you remember"]):
        return "show_memory", 0.97
    
    # Task management intents
    if any(phrase in text for phrase in ["show tasks", "list tasks", "view tasks"]):
        return "task_management", 0.95
    
    # Scheduler intents
    if text.startswith("remind me"):
        return "schedule_task", 0.97
    
    if " in " in text and any(unit in text for unit in ["seconds", "minutes"]):
        return "schedule_task", 0.85
    
    if "every" in text:
        return "schedule_task", 0.80
    
    if " at " in text and any(word in text for word in ["run", "remind", "schedule"]):
        return "schedule_task", 0.88
    
    # Weather intents
    if any(phrase in text for phrase in [
        "weather in", "weather for", "weather today",
        "what's the weather", "current weather"
    ]):
        return "weather", 0.90
    
    # File operations
    if any(phrase in text for phrase in ["find file", "search files", "where is"]):
        return "file_search", 0.85
    
    # Fallback: return unknown intent with low confidence
    return "unknown", 0.0
```

**Intent Patterns Table:**

| Pattern | Intent | Confidence | Handler |
|---------|--------|------------|---------|
| `exit`, `quit` | `exit` | 1.0 | System exit |
| starts with `remember` | `remember` | 0.97 | Memory service |
| `show memory`, `what do you remember` | `show_memory` | 0.97 | Memory service |
| `show/list/view tasks` | `task_management` | 0.95 | Scheduler |
| starts with `remind me` | `schedule_task` | 0.97 | Scheduler |
| contains `in` + time units | `schedule_task` | 0.85 | Scheduler |
| contains `weather in/for/today` | `weather` | 0.90 | Weather API |
| contains `find/search file` | `file_search` | 0.85 | File tools |

---

### 4. Conversation Service (`services/conversation_service.py`)

Multi-session conversation persistence with automatic history management.

#### Session File Structure

Each session is stored as a JSON file in `data/sessions/session_<uuid>.json`:

```json
{
  "id": "session_abc123def456",
  "title": "Chat about Python",
  "created": "2025-01-01 09:00",
  "updated": "2025-01-01 09:05",
  "messages": [
    {
      "role": "user",
      "content": "How do I write a loop in Python?"
    },
    {
      "role": "assistant",
      "content": "In Python, you use the for loop...\n\nfor i in range(10):\n    print(i)"
    },
    {
      "role": "user",
      "content": "What about while loops?"
    },
    {
      "role": "assistant",
      "content": "While loops execute as long as a condition is true..."
    }
  ]
}
```

#### API Functions

```python
def get_active_session_id() -> str:
    """
    Returns current active session ID.
    Creates new session if none exists.
    Checks config.json for 'active_session' key.
    """

def new_session(title: str = "") -> str:
    """
    Creates brand-new conversation session.
    Returns: session_id (format: "session_<12_hex_chars>")
    Updates config.json to make this active session.
    """
    sid = "session_" + uuid.uuid4().hex[:12]
    data = {
        "id": sid,
        "title": title or "New Chat",
        "created": _now(),
        "updated": _now(),
        "messages": []
    }
    _write_session(data)
    set_setting("active_session", sid)
    return sid

def add_message(role: str, content: str) -> None:
    """
    Appends message to active session.
    Maintains MAX_MESSAGES (20) sliding window.
    
    Parameters:
    - role: "user" | "assistant"
    - content: message text
    """
    sid = get_active_session_id()
    data = _read_session(sid)
    
    if not data:
        data = {
            "id": sid,
            "title": "New Chat",
            "created": _now(),
            "updated": _now(),
            "messages": []
        }
    
    data["messages"].append({
        "role": role,
        "content": content
    })
    
    # Trim to MAX_MESSAGES (sliding window)
    if len(data["messages"]) > MAX_MESSAGES:
        data["messages"] = data["messages"][-MAX_MESSAGES:]
    
    data["updated"] = _now()
    _write_session(data)

def get_history() -> list:
    """
    Returns current active session message history.
    Format: [{"role": "user"|"assistant", "content": "..."}, ...]
    """
    sid = get_active_session_id()
    data = _read_session(sid)
    return data.get("messages", [])
```

---

### 5. Memory Service (`services/memory_service.py`)

Persistent user memory extracted from conversations.

#### Memory File Structure (`memory.json`)

```json
{
  "profile": {
    "name": "John Doe",
    "role": "Software Engineer",
    "field_of_study": "Computer Science",
    "location": "San Francisco",
    "age": "28",
    "likes": "Python programming",
    "preferences": "dark mode",
    "custom_field": "custom value"
  }
}
```

#### API Functions

```python
def load_memory() -> dict:
    """Loads current memory.json. Returns {} if not found."""

def save_memory(key: str, value: str) -> None:
    """
    Updates memory["profile"][key] = value
    Automatically creates "profile" nested dict if needed.
    """
    memory = load_memory()
    if "profile" not in memory:
        memory["profile"] = {}
    memory["profile"][key] = value
    _write_memory(memory)

def get_memory(key: str) -> str:
    """
    Retrieves memory value.
    Checks nested profile first, then flat (backwards compat).
    """
    memory = load_memory()
    profile = memory.get("profile", {})
    if key in profile:
        return profile[key]
    return memory.get(key)

def maybe_store_memory(text: str) -> None:
    """
    Auto-extracts user info from messages.
    Called after user sends message.
    
    Patterns extracted:
    - "my name is <name>" → saves as "name"
    - "i am a/an <role>" / "i work as <role>" → saves as "role"
    - "i study <field>" → saves as "field_of_study"
    - "i live in <location>" → saves as "location"
    - "i am <age> years old" → saves as "age"
    - "i prefer <preference>" → saves as "preference"
    - "i like <likes>" → saves as "likes"
    """
    text_lower = text.lower().strip()
    
    # Example: "i live in Paris" → extract "Paris"
    if "i live in" in text_lower:
        location = text.split("i live in", 1)[-1].strip().rstrip(".!,")
        save_memory("location", location)
    
    # Similar patterns for other fields...
```

---

### 6. Tool Registry System (`tools/registry.py`)

Extensible command routing system for system actions and custom tools.

```python
class ToolRegistry:
    """
    Central registry for all available tools/commands.
    Maps intent names to handler functions.
    """
    
    def __init__(self):
        self.tools = {}  # intent_name → function
    
    def register(self, name: str, func):
        """Register a new tool: registry.register("my_tool", my_handler_func)"""
        self.tools[name] = func
    
    def get(self, name: str):
        """Retrieve tool if exists, else None"""
        return self.tools.get(name)
    
    def list_tools(self) -> list:
        """Get all registered tool names"""
        return list(self.tools.keys())

# Global registry instance
registry = ToolRegistry()

# Pre-registered system tools
registry.register("close_app", close_app)
registry.register("close_external_app", close_external_app)
registry.register("shutdown_pc", shutdown_pc)
registry.register("restart_pc", restart_pc)
registry.register("kill_process", kill_process)
```

#### Registering Custom Tools

```python
# In any service module
from tools.registry import registry

@registry.register("custom_tool")
def my_custom_tool(text: str) -> str:
    # Parse text, execute action, return result
    return f"Executed custom tool with: {text}"

# Or register after definition
def weather_lookup(location: str) -> dict:
    """Fetch weather for location"""
    return {"location": location, "temp": 72, "condition": "sunny"}

registry.register("weather", weather_lookup)
```

---

### 7. Text-to-Speech Service (`services/tts_service.py`)

Offline TTS using pyttsx3 with thread-safe operations.

#### Architecture

```python
import threading
import pyttsx3

_lock         = threading.Lock()
_speaking     = False
_tts_thread   = None
_rate         = 175        # words per minute
_volume       = 1.0        # 0.0 to 1.0

def _do_speak(text: str):
    """
    Creates fresh pyttsx3 engine for each call.
    Required on Windows SAPI5 to avoid cutoffs.
    """
    global _speaking
    
    if not text or not text.strip():
        return
    
    cleaned = _clean_text(text)  # Collapse newlines/whitespace
    if not cleaned:
        return
    
    with _lock:
        _speaking = True
        try:
            engine = pyttsx3.init()  # Fresh engine each time
            engine.setProperty("rate", _rate)
            engine.setProperty("volume", _volume)
            engine.say(cleaned)
            engine.runAndWait()
            engine.stop()
        except Exception as e:
            print(f"[tts] speak error: {e}")
        finally:
            _speaking = False
```

#### Public API

```python
def speak(text: str) -> None:
    """
    Blocking TTS. Waits until speech finishes.
    Usage: speak("Hello world")
    """
    _do_speak(text)

def speak_async(text: str) -> None:
    """
    Non-blocking TTS in background thread.
    Multiple calls queue sequentially.
    Usage: speak_async("Hello in background")
    """
    global _tts_thread
    
    if not text or not text.strip():
        return
    
    prev_thread = _tts_thread
    
    def _run():
        # Wait for previous speech to finish
        if prev_thread is not None and prev_thread.is_alive():
            prev_thread.join()
        _do_speak(text)
    
    _tts_thread = threading.Thread(target=_run, daemon=True)
    _tts_thread.start()

def stop() -> None:
    """Stop current speech immediately"""

def set_rate(rate: int) -> None:
    """Set speech rate in words per minute (default 175)"""
    global _rate
    _rate = rate

def set_volume(vol: float) -> None:
    """Set volume 0.0 to 1.0 (default 1.0)"""
    global _volume
    _volume = vol

def is_speaking() -> bool:
    """Check if currently speaking"""
    global _speaking
    return _speaking
```

---

### 8. Configuration System (`core/config.py`)

Centralized settings management with defaults and thread-safe access.

#### Configuration Schema

```python
DEFAULT_CONFIG = {
    "model": "qwen2.5:3b",                    # LLM model name
    "auto_start": False,                       # Auto-launch on Windows boot
    "theme": "dark",                           # UI theme ("dark", "light")
    "notifications": True,                     # Show desktop notifications
    "max_history": 20,                         # Max messages per session
    "window_minimize_to_tray": True,          # Minimize behavior
    "active_session": None,                    # Current session UUID
    "tts_default": True,                       # TTS enabled by default
    "stream_responses": True,                  # Stream LLM responses
    "show_typing_indicator": True,            # Show typing animation
    "memory_enabled": True,                    # Enable memory system
    "memory_in_prompt": True,                  # Include memory in LLM prompts
    "hotkey_enabled": True,                    # Global hotkey support
    "log_conversations": True,                 # Save conversation logs
    "log_errors": True                         # Save error logs
}
```

#### API Functions

```python
def resource_path(filename: str) -> str:
    """
    Returns platform-aware resource path.
    For packaged apps (.exe): returns relative to executable dir.
    For dev: returns relative to current working directory.
    """
    if getattr(sys, "frozen", False):  # Packaged as .exe
        base = os.path.dirname(sys.executable)
    else:  # Running from source
        base = os.getcwd()
    return os.path.join(base, filename)

def load_config() -> dict:
    """
    Load config.json with defaults and thread safety.
    Fills in any missing keys from DEFAULT_CONFIG.
    Returns: dict with all config values
    """

def get_setting(key: str) -> any:
    """
    Get single config setting with fallback to default.
    Usage: model = get_setting("model")
    """

def set_setting(key: str, value: any) -> None:
    """
    Update single config setting and save to disk.
    Usage: set_setting("model", "qwen2.5:7b")
    """

def save_config(config: dict) -> None:
    """Save entire config dict to config.json"""
```

---

### 9. Plugin System (`core/plugin_manager.py`)

Auto-discovery and loading of plugins from `plugins/` directory.

#### Plugin Structure

Every plugin file must define:

```python
# plugins/my_plugin.py

PLUGIN_NAME    = "my_plugin"                    # Unique identifier
PLUGIN_INTENTS = ["my_intent", "another_intent"]  # Handled intents
PLUGIN_VERSION = "1.0.0"                        # Semantic version
PLUGIN_AUTHOR  = "Your Name"                    # Author info
PLUGIN_DESC    = "Short description"            # What it does

def handle(text: str) -> str:
    """Required: main handler for all intents"""
    return f"Handled: {text}"

# Optional: handler for specific intents
def handle_intent(intent: str, text: str) -> str:
    """If defined, called with specific intent instead of handle()"""
    if intent == "my_intent":
        return "Special handling for my_intent"
    return handle(text)
```

#### Plugin Manager API

```python
class PluginManager:
    def __init__(self, registry=None):
        self._plugins: dict = {}        # name → PluginInfo
        self._intent_map: dict = {}     # intent → plugin_name
        self._errors: list = []
    
    def load_all() -> int:
        """
        Scan plugins/ and load all valid .py files.
        Returns: number of plugins loaded
        Populates _plugins and _intent_map dicts.
        """
    
    def dispatch(intent: str, text: str) -> str:
        """
        Route intent to appropriate plugin handler.
        Returns: plugin.handle() result or error message.
        """
    
    def list_plugins() -> list:
        """Returns list of loaded PluginInfo objects"""
    
    def get_plugin(name: str) -> PluginInfo:
        """Get plugin metadata by name"""

class PluginInfo:
    """Plugin metadata container"""
    name: str               # Plugin name
    intents: list[str]      # Handled intents
    handler: callable       # Main handler function
    module: types.ModuleType  # Loaded Python module
    version: str            # Version string
    author: str             # Author name
    desc: str               # Description
```

#### Example: Gmail Plugin (`plugins/gmail_plugin.py`)

```python
PLUGIN_NAME    = "gmail"
PLUGIN_VERSION = "1.0.0"
PLUGIN_AUTHOR  = "Nova AI"
PLUGIN_DESC    = "Send emails via Gmail"
PLUGIN_INTENTS = ["send_email", "send_gmail", "email"]

import os
import re
import smtplib
from email.mime.text import MIMEText

GMAIL_USER     = os.getenv("GMAIL_USER", "")      # your@gmail.com
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS", "")  # 16-char app password

def _parse(text: str) -> tuple[str, str, str]:
    """
    Parse email command.
    Input: "email to john@example.com subject Meeting body Let's talk"
    Output: ("john@example.com", "Meeting", "Let's talk")
    """
    to_match  = re.search(r'\bto\s+([\w.@+\-]+)', text, re.IGNORECASE)
    sub_match = re.search(r'\bsubject\s+(.+?)(?:\s+body\s+|\s*$)', text, re.IGNORECASE)
    bod_match = re.search(r'\bbody\s+(.+)', text, re.IGNORECASE)
    
    if not to_match:
        raise ValueError("No recipient. Use: email to someone@gmail.com subject ... body ...")
    
    return (
        to_match.group(1),
        sub_match.group(1).strip() if sub_match else "(no subject)",
        bod_match.group(1).strip() if bod_match else ""
    )

def handle(text: str) -> str:
    """
    Send email via Gmail SMTP.
    Requires GMAIL_USER and GMAIL_APP_PASS environment variables.
    """
    if not GMAIL_USER or not GMAIL_APP_PASS:
        return "⚠️ Gmail not configured. Set GMAIL_USER and GMAIL_APP_PASS."
    
    try:
        to, subject, body = _parse(text)
    except ValueError as e:
        return f"⚠️ {e}"
    
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = GMAIL_USER
        msg["To"] = to
        
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASS)
            server.send_message(msg)
        
        return f"✓ Email sent to {to}"
    except Exception as e:
        return f"✗ Failed to send: {e}"
```

---
    Required on Windows SAPI5 to avoid cutoffs.
    """
    global _speaking
    
    if not text or not text.strip():
        return
    
    cleaned = _clean_text(text)  # Collapse newlines/whitespace
    if not cleaned:
        return
    
    with _lock:
        _speaking = True
        try:
            engine = pyttsx3.init()  # Fresh engine each time
            engine.setProperty("rate", _rate)
            engine.setProperty("volume", _volume)
            engine.say(cleaned)
            engine.runAndWait()
            engine.stop()
        except Exception as e:
            print(f"[tts] speak error: {e}")
        finally:
            _speaking = False
```

#### Public API

```python
def speak(text: str) -> None:
    """
    Blocking TTS. Waits until speech finishes.
    Usage: speak("Hello world")
    """
    _do_speak(text)

def speak_async(text: str) -> None:
    """
    Non-blocking TTS in background thread.
    Multiple calls queue sequentially.
    Usage: speak_async("Hello in background")
    """
    global _tts_thread
    
    if not text or not text.strip():
        return
    
    prev_thread = _tts_thread
    
    def _run():
        # Wait for previous speech to finish
        if prev_thread is not None and prev_thread.is_alive():
            prev_thread.join()
        _do_speak(text)
    
    _tts_thread = threading.Thread(target=_run, daemon=True)
    _tts_thread.start()

def stop() -> None:
    """Stop current speech immediately"""

def set_rate(rate: int) -> None:
    """Set speech rate in words per minute (default 175)"""
    global _rate
    _rate = rate

def set_volume(vol: float) -> None:
    """Set volume 0.0 to 1.0 (default 1.0)"""
    global _volume
    _volume = vol

def is_speaking() -> bool:
    """Check if currently speaking"""
    global _speaking
    return _speaking
```

---

### 8. Configuration System (`core/config.py`)

Centralized settings management with defaults and thread-safe access.

#### Configuration Schema

```python
DEFAULT_CONFIG = {
    "model": "qwen2.5:3b",                    # LLM model name
    "auto_start": False,                       # Auto-launch on Windows boot
    "theme": "dark",                           # UI theme ("dark", "light")
    "notifications": True,                     # Show desktop notifications
    "max_history": 20,                         # Max messages per session
    "window_minimize_to_tray": True,          # Minimize behavior
    "active_session": None,                    # Current session UUID
    "tts_default": True,                       # TTS enabled by default
    "stream_responses": True,                  # Stream LLM responses
    "show_typing_indicator": True,            # Show typing animation
    "memory_enabled": True,                    # Enable memory system
    "memory_in_prompt": True,                  # Include memory in LLM prompts
    "hotkey_enabled": True,                    # Global hotkey support
    "log_conversations": True,                 # Save conversation logs
    "log_errors": True                         # Save error logs
}
```

#### API Functions

```python
def resource_path(filename: str) -> str:
    """
    Returns platform-aware resource path.
    For packaged apps (.exe): returns relative to executable dir.
    For dev: returns relative to current working directory.
    """
    if getattr(sys, "frozen", False):  # Packaged as .exe
        base = os.path.dirname(sys.executable)
    else:  # Running from source
        base = os.getcwd()
    return os.path.join(base, filename)

def load_config() -> dict:
    """
    Load config.json with defaults and thread safety.
    Fills in any missing keys from DEFAULT_CONFIG.
    Returns: dict with all config values
    """

def get_setting(key: str) -> any:
    """
    Get single config setting with fallback to default.
    Usage: model = get_setting("model")
    """

def set_setting(key: str, value: any) -> None:
    """
    Update single config setting and save to disk.
    Usage: set_setting("model", "qwen2.5:7b")
    """

def save_config(config: dict) -> None:
    """Save entire config dict to config.json"""
```

---

### 9. Plugin System (`core/plugin_manager.py`)

Auto-discovery and loading of plugins from `plugins/` directory.

#### Plugin Structure

Every plugin file must define:

```python
# plugins/my_plugin.py

PLUGIN_NAME    = "my_plugin"                    # Unique identifier
PLUGIN_INTENTS = ["my_intent", "another_intent"]  # Handled intents
PLUGIN_VERSION = "1.0.0"                        # Semantic version
PLUGIN_AUTHOR  = "Your Name"                    # Author info
PLUGIN_DESC    = "Short description"            # What it does

def handle(text: str) -> str:
    """Required: main handler for all intents"""
    return f"Handled: {text}"

# Optional: handler for specific intents
def handle_intent(intent: str, text: str) -> str:
    """If defined, called with specific intent instead of handle()"""
    if intent == "my_intent":
        return "Special handling for my_intent"
    return handle(text)
```

#### Plugin Manager API

```python
class PluginManager:
    def __init__(self, registry=None):
        self._plugins: dict = {}        # name → PluginInfo
        self._intent_map: dict = {}     # intent → plugin_name
        self._errors: list = []
    
    def load_all() -> int:
        """
        Scan plugins/ and load all valid .py files.
        Returns: number of plugins loaded
        Populates _plugins and _intent_map dicts.
        """
    
    def dispatch(intent: str, text: str) -> str:
        """
        Route intent to appropriate plugin handler.
        Returns: plugin.handle() result or error message.
        """
    
    def list_plugins() -> list:
        """Returns list of loaded PluginInfo objects"""
    
    def get_plugin(name: str) -> PluginInfo:
        """Get plugin metadata by name"""

class PluginInfo:
    """Plugin metadata container"""
    name: str               # Plugin name
    intents: list[str]      # Handled intents
    handler: callable       # Main handler function
    module: types.ModuleType  # Loaded Python module
    version: str            # Version string
    author: str             # Author name
    desc: str               # Description
```

#### Example: Gmail Plugin (`plugins/gmail_plugin.py`)

```python
PLUGIN_NAME    = "gmail"
PLUGIN_VERSION = "1.0.0"
PLUGIN_AUTHOR  = "Nova AI"
PLUGIN_DESC    = "Send emails via Gmail"
PLUGIN_INTENTS = ["send_email", "send_gmail", "email"]

import os
import re
import smtplib
from email.mime.text import MIMEText

GMAIL_USER     = os.getenv("GMAIL_USER", "")      # your@gmail.com
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS", "")  # 16-char app password

def _parse(text: str) -> tuple[str, str, str]:
    """
    Parse email command.
    Input: "email to john@example.com subject Meeting body Let's talk"
    Output: ("john@example.com", "Meeting", "Let's talk")
    """
    to_match  = re.search(r'\bto\s+([\w.@+\-]+)', text, re.IGNORECASE)
    sub_match = re.search(r'\bsubject\s+(.+?)(?:\s+body\s+|\s*$)', text, re.IGNORECASE)
    bod_match = re.search(r'\bbody\s+(.+)', text, re.IGNORECASE)
    
    if not to_match:
        raise ValueError("No recipient. Use: email to someone@gmail.com subject ... body ...")
    
    return (
        to_match.group(1),
        sub_match.group(1).strip() if sub_match else "(no subject)",
        bod_match.group(1).strip() if bod_match else ""
    )

def handle(text: str) -> str:
    """
    Send email via Gmail SMTP.
    Requires GMAIL_USER and GMAIL_APP_PASS environment variables.
    """
    if not GMAIL_USER or not GMAIL_APP_PASS:
        return "⚠️ Gmail not configured. Set GMAIL_USER and GMAIL_APP_PASS."
    
    try:
        to, subject, body = _parse(text)
    except ValueError as e:
        return f"⚠️ {e}"
    
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = GMAIL_USER
        msg["To"] = to
        
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASS)
            server.send_message(msg)
        
        return f"✓ Email sent to {to}"
    except Exception as e:
        return f"✗ Failed to send: {e}"
```

---



---

## 🧠 Complete Data Flow Examples

### Example 1: User Says "Remember my email is john@example.com"

```
1. User Input: "Remember my email is john@example.com"
   ↓
2. main_window.py captures input and calls handle_command()
   ↓
3. handle_command() calls add_message("user", text)
   → Saves to data/sessions/session_abc123.json
   ↓
4. detect_intent("remember my email is john@example.com")
   → Returns ("remember", 0.97)
   ↓
5. registry.get("remember") is looked up
   → Returns memory_handler function
   ↓
6. memory_handler("Remember my email is john@example.com")
   → maybe_store_memory() extracts "john@example.com"
   → Saves to memory.json under profile.email
   ↓
7. Response sent to user: "✓ Saved email: john@example.com"
   ↓
8. add_message("assistant", response)
   → Saved to session
```

**Files Modified:**
- `data/sessions/session_abc123.json` - User message added
- `memory.json` - Email stored in profile

---

### Example 2: User Asks "What's the weather in London?"

```
1. User Input: "What's the weather in London?"
   ↓
2. detect_intent("what's the weather in london?")
   → Finds "weather in" pattern
   → Returns ("weather", 0.90)
   ↓
3. registry.get("weather") looks up weather tool
   → If exists, call it; else fallback to LLM
   ↓
4. Fallback to LLM:
   ├─ build_memory_prompt(user_input)
   │  ├─ load_memory() → loads profile data
   │  ├─ Build augmented prompt:
   │  │  "You are a personal assistant.
   │  │   Memory: name: John, location: NYC
   │  │   User message: What's the weather in London?"
   │  └─ Returns augmented prompt
   │
   ├─ get_history() → gets last 20 messages
   │  └─ Returns: [{"role": "user", "content": "..."}, ...]
   │
   ├─ Combine history + new message
   │  └─ messages = [history items + {"role": "user", "content": augmented_prompt}]
   │
   ├─ ollama.chat(model="qwen2.5:7b", messages=messages)
   │  └─ API Call to localhost:11434
   │     Request: POST /api/chat
   │     Response: {"message": {"content": "The weather in London is..."}}
   │
   ├─ assistant_reply = response["message"]["content"]
   │
   └─ add_message("assistant", assistant_reply)
      └─ Saved to session
```

**Message Format Sent to Ollama:**
```json
{
  "model": "qwen2.5:7b",
  "messages": [
    {"role": "user", "content": "Previous user message"},
    {"role": "assistant", "content": "Previous assistant response"},
    {"role": "user", "content": "You are a personal assistant.\n\nMemory:\nname: John\nlocation: NYC\n\nUser message:\nWhat's the weather in London?\n\nRespond naturally."}
  ],
  "stream": true
}
```

---

### Example 3: Creating a Custom Plugin

```python
# plugins/calculator_plugin.py

PLUGIN_NAME    = "calculator"
PLUGIN_VERSION = "1.0.0"
PLUGIN_AUTHOR  = "Your Name"
PLUGIN_DESC    = "Simple math calculator"
PLUGIN_INTENTS = ["calculate", "math", "add", "multiply"]

import re

def _parse_expression(text: str) -> tuple:
    """Extract math expression from text"""
    # "calculate 5 + 3" → (5, +, 3)
    match = re.search(r'(\d+)\s*([\+\-\*/])\s*(\d+)', text)
    if not match:
        raise ValueError("Invalid math expression")
    return float(match.group(1)), match.group(2), float(match.group(3))

def handle(text: str) -> str:
    try:
        a, op, b = _parse_expression(text)
        if op == '+':
            result = a + b
        elif op == '-':
            result = a - b
        elif op == '*':
            result = a * b
        elif op == '/':
            if b == 0:
                return "Cannot divide by zero!"
            result = a / b
        return f"{a} {op} {b} = {result}"
    except ValueError as e:
        return f"Error: {e}"

def handle_intent(intent: str, text: str) -> str:
    """Optional: handle specific intents differently"""
    if intent == "add":
        # Special handling for add intent
        return handle(f"calculate {text}")
    return handle(text)
```

**Usage Flow:**
1. User: "calculate 10 + 5"
2. Intent detected: ("calculate", 0.95)
3. Plugin dispatched: calculator_plugin.handle()
4. Response: "10 + 5 = 15"

---

## 📁 Detailed Project Structure with File Descriptions

```
Assistant/
├── core/                              # Core application logic
│   ├── __init__.py
│   ├── assistant.py                   # Main LLM interface, memory prompt building
│   ├── intent_engine.py              # Pattern-based intent detection (80+ patterns)
│   ├── config.py                     # Config loading, resource paths, thread-safe getters
│   ├── logger.py                     # Centralized logging with file rotation
│   ├── plugin_manager.py             # Plugin discovery, loading, dispatch
│   ├── response_formatter.py         # Format LLM responses for display
│   ├── crash_recovery.py             # Session recovery on crash
│   ├── result_extractor.py           # Extract structured data from responses
│   ├── shutdown_manager.py           # Graceful shutdown procedures
│   ├── session_restore.py            # Load previous session on startup
│   ├── startup.py                    # Application startup sequence
│   ├── run_python.py                 # Execute Python code snippets
│   └── downloader.py                 # Download models and resources
│
├── ui/                                # PyQt5 User Interface
│   ├── __init__.py
│   ├── command_palette.py            # Command search/execution dialog
│   ├── confirmation_dialog.py        # User confirmation prompts
│   ├── main_window.py                # Main PyQt5 window (messages, input, buttons)
│   ├── tray.py                       # System tray icon and menu
│   └── [accessibility]/              # Accessibility features for screen readers
│
├── services/                          # Cross-cutting services
│   ├── __init__.py
│   ├── accessibility_service.py     # NVDA/JAWS screen reader support
│   ├── conversation_service.py      # Session persistence, message storage
│   ├── health_monitor.py            # Monitor app health, uptime, errors
│   ├── hotkey_service.py            # Global keyboard shortcuts (Win+M, etc.)
│   ├── log_reader.py                # Read and analyze log files
│   ├── memory_service.py            # Extract/store user memory
│   ├── scheduler_service.py         # Schedule tasks, reminders, recurring jobs
│   └── tts_service.py               # Text-to-speech (pyttsx3 backend)
│
├── tools/                             # Tool/command registry and implementations
│   ├── __init__.py
│   ├── registry.py                  # Tool registry (Central command mapping)
│   ├── tools_manager.py             # Tool loading and initialization
│   ├── result_processor.py          # Process tool execution results
│   ├── conversation_search_tools.py # Search conversation history
│   ├── export_tools.py              # Export to PDF, CSV, JSON
│   ├── file_tools.py                # File open, save, delete operations
│   ├── screen_tools.py              # Screen capture, screenshot
│   ├── system_info_tools.py         # CPU, RAM, disk, network info
│   ├── system_tools.py              # Close app, restart, shutdown
│   ├── time_tools.py                # Time, date, timezone utilities
│   └── [more_tools]/                # Additional specialized tools
│
├── plugins/                           # Plugin system
│   ├── __init__.py
│   ├── gmail_plugin.py              # Send emails via Gmail SMTP
│   ├── plugin_manager.py            # Plugin loading facade
│   └── [custom_plugins]/            # User-created plugins
│
├── models/                            # LLM model management
│   ├── __init__.py
│   ├── downloader.py                # Download models from Ollama
│   └── ollama_setup.py              # Setup Ollama, check connectivity
│
├── patches/                           # UI and compatibility patches
│   ├── __init__.py
│   ├── modern_gui_accessibility_patch.py
│   ├── patch_intent_accessibility.py
│   └── tools_manager_accessibility_addon.py
│
├── data/                              # Data storage
│   ├── __init__.py
│   └── sessions/                    # Session files: session_<uuid>.json
│
├── logs/                              # Application logs directory
│   ├── error.log                    # Error log
│   ├── app.log                      # Debug/info log
│   └── [rotated logs]/
│
├── config.json                        # Configuration file (model, theme, settings)
├── memory.json                        # User profile memory storage
├── conversation.json                  # Deprecated (now uses sessions/)
├── main.py                            # Entry point - loads UI
├── main.pyw                           # Windows entry point (no console)
├── run.bat                            # Batch file to start app
├── requirements.txt                   # Python dependencies
├── tasks.json                         # VS Code task configuration
└── installer.iss                      # InnoSetup installer script
```

---

## 🔧 How to Extend the System

### Adding a New Intent

1. Add pattern to `core/intent_engine.py`:

```python
def detect_intent(text):
    # ... existing code ...
    
    # Add your new pattern
    if any(phrase in text for phrase in ["your pattern", "alternative pattern"]):
        return "your_intent", 0.85
```

2. Create handler in `tools/` or `services/`:

```python
# tools/my_tools.py
def handle_my_intent(text: str) -> str:
    # Process the text
    result = your_logic(text)
    return result
```

3. Register tool:

```python
# In tools/registry.py
registry.register("your_intent", handle_my_intent)
```

---

### Adding Automatic Memory Extraction

In `services/memory_service.py`, add pattern to `maybe_store_memory()`:

```python
def maybe_store_memory(text):
    text_lower = text.lower().strip()
    
    # New extraction pattern
    if "i work for" in text_lower:
        company = text.split("i work for", 1)[-1].strip().rstrip(".!,")
        save_memory("company", company)
```

---

### Creating a New Service

1. Create file in `services/`:

```python
# services/my_service.py

def initialize():
    """Called once at startup"""
    pass

def do_something(param):
    """Main functionality"""
    return result
```

2. Import and call from main:

```python
# In core/startup.py
from services.my_service import initialize
initialize()
```

---

## 🌐 Ollama Integration Details

### Communication Protocol

The app uses the Ollama Python SDK to communicate with Ollama backend:

```python
import ollama

# Connection details
# - Host: localhost
# - Port: 11434
# - Endpoint: /api/chat

# Chat API Call
response = ollama.chat(
    model="qwen2.5:7b",
    messages=[
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "How are you?"}
    ],
    stream=False  # Set True for streaming responses
)

# Response format
response = {
    "model": "qwen2.5:7b",
    "created_at": "2025-01-01T12:00:00",
    "message": {
        "role": "assistant",
        "content": "I'm doing great, thanks for asking!"
    },
    "done": True,
    "total_duration": 1234567890,
    "load_duration": 123456,
    "prompt_eval_count": 10,
    "eval_count": 50
}
```

### Supported Models

- `qwen2.5:3b` - Small, fast, recommended for real-time
- `qwen2.5:7b` - Medium, balanced quality/speed
- `qwen2.5:14b` - Large, higher quality
- `llama2:7b` - Alternative model
- `mistral:7b` - Specialized model

Pull new models with:
```bash
ollama pull qwen2.5:14b
```

---

## 📊 Session File Format Reference

```json
{
  "id": "session_a1b2c3d4e5f6",
  "title": "Conversation about Python",
  "created": "2025-01-15 14:30",
  "updated": "2025-01-15 14:45",
  "messages": [
    {
      "role": "user",
      "content": "How do I create a list in Python?"
    },
    {
      "role": "assistant",
      "content": "In Python, you create a list using square brackets.\n\nExample:\n```python\nmy_list = [1, 2, 3, 4, 5]\n```"
    },
    {
      "role": "user",
      "content": "What about adding items?"
    },
    {
      "role": "assistant",
      "content": "You can add items using the .append() method:\n\n```python\nmy_list.append(6)\n# Now: [1, 2, 3, 4, 5, 6]\n```"
    }
  ]
}
```

**Constraints:**
- Max messages per session: 20 (sliding window)
- Older messages automatically removed
- Session ID format: `session_` + 12 hex characters
- Timestamps in format: `YYYY-MM-DD HH:MM`

---

## 💾 Memory File Format Reference

```json
{
  "profile": {
    "name": "John Doe",
    "age": "32",
    "role": "Senior Software Engineer",
    "company": "Tech Corp",
    "location": "San Francisco, CA",
    "field_of_study": "Computer Science",
    "likes": "Python programming, AI, hiking",
    "preferences": "dark mode, quiet environment",
    "email": "john@example.com",
    "custom_field_1": "any custom value",
    "custom_field_2": "more custom data"
  }
}
```

**Memory Extraction Patterns:**
1. `"my name is <name>"` → saves as `name`
2. `"i am/work as <role>"` → saves as `role`
3. `"i study <field>"` → saves as `field_of_study`
4. `"i live in <location>"` → saves as `location`
5. `"i am <age> years old"` → saves as `age`
6. `"i work for <company>"` → saves as `company`
7. `"i prefer <preference>"` → saves as `preferences`
8. `"i like <likes>"` → saves as `likes`

---

## 🐛 Debugging Guide

### Enable Debug Logging

Edit `core/logger.py` to set log level to DEBUG:

```python
logging.basicConfig(level=logging.DEBUG)
```

### Check Ollama Connection

```python
import ollama
try:
    response = ollama.list()
    print(response)  # Should show available models
except Exception as e:
    print(f"Ollama not running: {e}")
```

### Inspect Session Files

```python
import json
with open("data/sessions/session_abc123.json") as f:
    session = json.load(f)
    print(json.dumps(session, indent=2))
```

### Test LLM Response

```python
from core.assistant import ask_llm
response = ask_llm("What is Python?")
print(response)
```

---

## 📁 File Dependency Graph

```
main.py
  ├── ui/main_window.py
  │   ├── core/config.py
  │   ├── core/assistant.py
  │   │   ├── core/intent_engine.py
  │   │   ├── services/conversation_service.py
  │   │   │   └── core/config.py
  │   │   ├── services/memory_service.py
  │   │   │   └── core/config.py
  │   │   └── tools/registry.py
  │   ├── services/tts_service.py
  │   ├── services/hotkey_service.py
  │   └── core/plugin_manager.py
```

---

## 🛠️ Development Examples

### Example: Adding Weather Support

**Step 1:** Add intent pattern in `core/intent_engine.py`
```python
if any(phrase in text for phrase in ["weather in", "weather for", "temperature"]):
    return "weather", 0.90
```

**Step 2:** Create weather tool in `tools/weather_tools.py`
```python
import requests

def get_weather(location: str) -> dict:
    """Fetch weather from OpenWeatherMap API"""
    api_key = os.getenv("OPENWEATHER_API_KEY")
    url = f"https://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric"
    response = requests.get(url)
    data = response.json()
    return {
        "location": data["name"],
        "temperature": data["main"]["temp"],
        "condition": data["weather"][0]["main"],
        "humidity": data["main"]["humidity"]
    }

def handle_weather(text: str) -> str:
    """Parse location from text and fetch weather"""
    # Extract location: "weather in London" → "London"
    location = text.replace("weather in", "").replace("weather for", "").strip()
    
    try:
        weather = get_weather(location)
        return f"📍 {weather['location']}: {weather['temperature']}°C, {weather['condition']}"
    except Exception as e:
        return f"Unable to fetch weather: {e}"
```

**Step 3:** Register in `tools/registry.py`
```python
from tools.weather_tools import handle_weather
registry.register("weather", handle_weather)
```

**Usage:**
```
User: "weather in London"
→ Intent: ("weather", 0.90)
→ Tool dispatched: handle_weather()
→ Response: "📍 London: 15°C, Cloudy"
```

---

### Example: Custom Memory Pattern

Add to `services/memory_service.py`:

```python
def maybe_store_memory(text):
    text_lower = text.lower().strip()
    
    # Your custom pattern
    if "my phone number is" in text_lower:
        phone = text.split("my phone number is", 1)[-1].strip().rstrip(".!,")
        save_memory("phone_number", phone)
    
    # Multiple word patterns
    if "i work for" in text_lower:
        company = text.split("i work for", 1)[-1].strip().rstrip(".!,")
        save_memory("employer", company)
    
    # Append to list
    if "my hobbies are" in text_lower:
        hobbies = text.split("my hobbies are", 1)[-1].strip().rstrip(".!,")
        existing = get_memory("hobbies") or ""
        combined = f"{existing}, {hobbies}".lstrip(", ")
        save_memory("hobbies", combined)
```

---

## 🔌 Plugin Development Checklist

Creating a new plugin? Follow this checklist:

```python
# plugins/awesome_plugin.py

# ✅ 1. Define metadata (REQUIRED)
PLUGIN_NAME    = "awesome_plugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_AUTHOR  = "Your Name"
PLUGIN_DESC    = "What this plugin does"
PLUGIN_INTENTS = ["intent1", "intent2"]  # Required

# ✅ 2. Implement main handler (REQUIRED)
def handle(text: str) -> str:
    """
    Main handler called when plugin is dispatched.
    Must return a string response.
    """
    # Parse text
    # Execute logic
    # Return result
    return f"Handled: {text}"

# ✅ 3. (Optional) Implement intent-specific handler
def handle_intent(intent: str, text: str) -> str:
    """
    Optional: called if you want custom logic per intent.
    Falls back to handle() if not implemented.
    """
    if intent == "intent1":
        return "Special handling for intent1"
    elif intent == "intent2":
        return "Special handling for intent2"
    return handle(text)

# ✅ 4. (Optional) Error handling
def handle(text: str) -> str:
    try:
        result = your_logic(text)
        return result
    except ValueError as e:
        return f"⚠️ Invalid input: {e}"
    except Exception as e:
        return f"❌ Error: {e}"

# ✅ 5. (Optional) Initialize on load
def initialize():
    """Called when plugin is loaded"""
    print(f"[{PLUGIN_NAME}] Initializing...")
    # Setup code here
```

---

## 🔍 Testing Guide

### Test Intent Detection

```python
from core.intent_engine import detect_intent

test_cases = [
    ("remember my email is test@example.com", "remember"),
    ("weather in Paris", "weather"),
    ("show tasks", "task_management"),
    ("remind me in 5 minutes", "schedule_task"),
    ("what is python", "unknown"),
]

for text, expected_intent in test_cases:
    intent, confidence = detect_intent(text)
    status = "✓" if intent == expected_intent else "✗"
    print(f"{status} '{text}' → {intent} ({confidence})")
```

### Test Memory Extraction

```python
from services.memory_service import maybe_store_memory, get_memory, load_memory

# Clear memory
import os
os.remove("memory.json")

# Test extraction
maybe_store_memory("My name is Alice")
maybe_store_memory("I live in New York")
maybe_store_memory("I work as a doctor")

memory = load_memory()
print(json.dumps(memory, indent=2))
# Expected:
# {
#   "profile": {
#     "name": "Alice",
#     "location": "New York",
#     "role": "doctor"
#   }
# }
```

### Test Plugin Loading

```python
from core.plugin_manager import PluginManager

pm = PluginManager()
loaded_count = pm.load_all()
print(f"Loaded {loaded_count} plugins")

plugins = pm.list_plugins()
for plugin in plugins:
    print(f"- {plugin.name} v{plugin.version} ({', '.join(plugin.intents)})")

# Test dispatch
result = pm.dispatch("gmail", "email to test@example.com subject Hi body Hello")
print(result)
```

---

## 📈 Performance Optimization

### 1. Reduce Model Size

```json
{
  "model": "qwen2.5:3b"
}
```
- 3B model: ~2GB, faster responses
- 7B model: ~4GB, better quality
- 14B model: ~8GB+, best quality but slower

### 2. Optimize History Length

```json
{
  "max_history": 10
}
```
- Fewer messages = faster processing
- Default: 20, try 10 for speed

### 3. Disable Unnecessary Features

```json
{
  "stream_responses": false,
  "show_typing_indicator": false,
  "memory_in_prompt": false
}
```

### 4. Profile Performance

```python
import time

def time_function(func, *args):
    start = time.time()
    result = func(*args)
    duration = time.time() - start
    print(f"{func.__name__} took {duration:.2f}s")
    return result

# Test
time_function(detect_intent, "weather in London")
time_function(ask_llm, "What is Python?")
time_function(get_history)
```

---

## 🚨 Error Handling Patterns

### Pattern 1: Graceful Degradation

```python
# Try to use feature, fallback if unavailable
def speak_or_print(text: str):
    try:
        from services.tts_service import speak
        speak(text)
    except Exception:
        print(text)  # Fallback to text
```

### Pattern 2: Validation

```python
def add_memory_safe(key: str, value: str) -> bool:
    if not key or not value:
        return False
    if len(key) > 100 or len(value) > 1000:
        return False
    try:
        save_memory(key, value)
        return True
    except Exception:
        return False
```

### Pattern 3: Retry Logic

```python
def ask_llm_with_retry(text: str, max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        try:
            return ask_llm(text)
        except ConnectionError:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            raise
```

---

## 📞 Support Resources

- **Ollama Docs**: https://ollama.ai/docs
- **PyQt5 Docs**: https://www.riverbankcomputing.com/static/Docs/PyQt5/
- **OpenAI Chat Format**: https://platform.openai.com/docs/guides/gpt/chat-completions

---

## 📋 Troubleshooting Reference Table

| Problem | Cause | Solution |
|---------|-------|----------|
| "Ollama refused connection" | Ollama not running | Run `ollama serve` |
| "Model not found" | Model not installed | Run `ollama pull qwen2.5:7b` |
| "GUI not launching" | Qt import error | `pip install PyQt5` |
| "Memory not saving" | File permissions | Check `memory.json` writable |
| "Plugin not loading" | Syntax error in plugin | Check plugin file for errors |
| "Intent not detected" | Pattern not matching | Debug with `detect_intent()` |
| "TTS not working" | pyttsx3 not installed | `pip install pyttsx3` |
| "Sessions not found" | Corrupted JSON | Delete `data/sessions/` and restart |

---

## 🎯 Quick Reference

### Key Python Imports

```python
# Core
from core.assistant import ask_llm, build_memory_prompt
from core.config import get_setting, set_setting
from core.intent_engine import detect_intent
from core.plugin_manager import PluginManager

# Services
from services.conversation_service import add_message, get_history
from services.memory_service import load_memory, save_memory, get_memory
from services.tts_service import speak, speak_async, stop

# Tools
from tools.registry import registry
```

### Common Config Operations

```python
# Read settings
model = get_setting("model")
theme = get_setting("theme")

# Write settings
set_setting("model", "qwen2.5:14b")
set_setting("theme", "light")
```

### Common Memory Operations

```python
# Get user info
name = get_memory("name")
location = get_memory("location")

# Save user info
save_memory("email", "user@example.com")
save_memory("phone", "555-1234")
```

### Common Conversation Operations

```python
# Get last 20 messages
messages = get_history()

# Add new messages
add_message("user", "Hello")
add_message("assistant", "Hi there!")

# Create new session
from services.conversation_service import new_session
sid = new_session("My New Chat")
```

---

## 📦 Dependencies Summary

| Package | Purpose | Version |
|---------|---------|---------|
| PyQt5 | GUI framework | 5.15+ |
| ollama | LLM API client | Latest |
| pyttsx3 | Text-to-speech | 2.90+ |
| keyboard | Global hotkeys | 0.13+ |
| requests | HTTP client | 2.28+ |
| python-pptx | Presentations | 0.6+ |
| pyperclip | Clipboard | 1.8+ |

---

## 🎓 Learning Path for New Developers

1. **Understand Core Loop** → Read `core/assistant.py`
2. **Learn Intent System** → Read `core/intent_engine.py`
3. **Explore Data Storage** → Check `services/conversation_service.py`
4. **Try Adding Tool** → Create `tools/my_tool.py`
5. **Build Plugin** → Create `plugins/my_plugin.py`
6. **Modify UI** → Edit `ui/main_window.py`

---

## 📝 License

[Specify your license here - MIT, GPL, Apache, etc.]

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Write tests
5. Submit a pull request

## 👨‍💻 Author

Created for personal productivity and local AI integration.

---

**Last Updated:** April 6, 2026
**Version:** 1.0.0
**Status:** Active Development

For the most up-to-date information, check the repository commits and issue tracker.

## 🛠️ Development

### Adding a New Tool

```python
# In tools/my_tools.py
from tools.registry import register_tool

@register_tool("search_files")
def search_files(directory, pattern):
    """Search for files matching a pattern."""
    # Implementation here
    return results
```

### Adding a New Service

```python
# Create services/my_service.py
def initialize_service():
    """Initialize the service"""
    pass

def my_function():
    """Service functionality"""
    pass
```

### Creating a Plugin

```python
# In plugins/my_plugin.py
class MyPlugin:
    def __init__(self):
        self.name = "MyPlugin"
        self.version = "1.0.0"
    
    def activate(self):
        """Called when plugin is activated"""
        pass
    
    def deactivate(self):
        """Called when plugin is deactivated"""
        pass
```

## 🔄 Workflow

1. **User Input**: User types or speaks a command
2. **Intent Detection**: `intent_engine` analyzes the input
3. **Memory Loading**: Relevant memory is retrieved
4. **Prompt Building**: Combines user input with memory context
5. **LLM Processing**: Ollama processes the request locally
6. **Tool Execution**: If needed, tools are executed
7. **Response Formatting**: Response is formatted for display
8. **Output**: Display text, TTS, or take system actions

## 📝 Logging

Application logs are stored in the `logs/` directory. Check error logs for troubleshooting:

```python
from core.logger import get_logger

logger = get_logger("module_name")
logger.info("Information message")
logger.error("Error message")
```

## 🐛 Troubleshooting

### Ollama Connection Error
- Ensure Ollama is running: `ollama serve`
- Check if model is installed: `ollama list`
- Verify localhost:11434 is accessible

### GUI Not Appearing
- Run with `main.pyw` instead of `main.py`
- Check Qt installation: `pip install PyQt5`
- Verify High DPI scaling settings in config

### Memory Issues
- Check `memory.json` for corruption
- Review logs in `logs/` directory
- Restart the application and Ollama

## 🚀 Performance Tips

- Use lighter models (e.g., qwen2.5:7b instead of larger models)
- Enable response streaming for faster perceived performance
- Configure appropriate `max_history` based on RAM
- Monitor system resource usage with health monitor

## 📦 Dependencies

Key dependencies (see requirements.txt for full list):
- **PyQt5**: GUI framework
- **ollama**: Ollama Python SDK
- **pyttsx3** or **edge-tts**: Text-to-speech
- **python-pptx**: Presentation tools
- **requests**: HTTP client
- **pyperclip**: Clipboard management
- **keyboard**: Global hotkey support

## 📄 License

[Add your license here]

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Commit changes: `git commit -am 'Add new feature'`
3. Push to branch: `git push origin feature/my-feature`
4. Submit a pull request

## 📞 Support

For issues, questions, or suggestions, please:
- Check existing issues in the repository
- Review the logs in `logs/` directory
- Test with the latest Ollama version
- Verify all dependencies are installed

## 🔮 Future Enhancements

- [ ] Multi-language support
- [ ] Voice command recognition
- [ ] More plugin integrations (Slack, Discord, etc.)
- [ ] Advanced analytics dashboard
- [ ] Cloud sync options (opt-in)
- [ ] Model fine-tuning capabilities
- [ ] Advanced scheduling and automation

---

**Built with ❤️ for productivity and privacy**
