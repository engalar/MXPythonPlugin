import logging
import anyio
import uvicorn
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from mcp.server.fastmcp import FastMCP

# --- Globals that are safe (constants and stateless functions) ---
port = 8004

# region logging (No changes needed here, as it's configuration)
# PostMessage("backend:clear", '')
# ShowDevTools()

class PostMessageHandler(logging.Handler):
    def __init__(self, post_message_func):
        super().__init__()
        self.post_message_func = post_message_func

    def emit(self, record):
        try:
            message = self.format(record)
            self.post_message_func("backend:info", message)
        except Exception:
            self.handleError(record)

LOG_LEVEL = logging.INFO
log_formatter = logging.Formatter(
    '{"level": "%(levelname)s", "time": "%(asctime)s", "logger": "%(name)s", "message": "%(message)s"}'
)
post_message_handler = PostMessageHandler(PostMessage)
post_message_handler.setLevel(LOG_LEVEL)
post_message_handler.setFormatter(log_formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(
    "%(levelname)-8s %(asctime)s [%(name)s] - %(message)s"
))

loggers_to_modify = ["uvicorn", "uvicorn.error", "uvicorn.access", "my_app"]
for logger_name in loggers_to_modify:
    logger = logging.getLogger(logger_name)
    logger.setLevel(LOG_LEVEL)
    if logger.hasHandlers():
        logger.handlers.clear()
    logger.addHandler(post_message_handler)
    logger.addHandler(console_handler)
    logger.propagate = False
# endregion

# --- Main application logic encapsulated in a function ---
async def main_app_logic():
    """
    Sets up, runs, and tears down the entire application for a single execution.
    This prevents state from leaking between runs.
    """
    PostMessage("backend:clear", '')  # Clear console at the start of each run

    # 1. Create fresh instances of all stateful objects INSIDE the function.
    mcp = FastMCP("mendix-modular-copilot")

    # Define tools on the new mcp instance
    @mcp.tool()
    def add(a: int, b: int) -> int:
        """Add two numbers"""
        return a + b

    # 2. Define the lifespan context manager. It will capture the 'mcp'
    #    instance from this function's scope.
    async def lifespan(app: Starlette):
        """Application lifespan handler."""
        PostMessage("backend:info", "应用启动... 正在启动 MCP session manager...")
        async with mcp.session_manager.run():
            PostMessage("backend:info", "MCP session manager 已启动，服务器准备就绪。")
            yield  # Server runs here
        PostMessage("backend:info", "应用关闭... 正在清理 MCP session manager。")

    # 3. Create the Starlette app and Uvicorn config using the fresh objects.
    app = Starlette(
        routes=[
            Mount("/a", app=mcp.streamable_http_app()),
            Route("/b", lambda r: JSONResponse({"status": "ok"})),
        ],
        lifespan=lifespan
    )

    config = uvicorn.Config(app=app, host="127.0.0.1",
                            port=port, log_config=None, timeout_graceful_shutdown=0)

    server = uvicorn.Server(config)

    # 4. The server and cancellation logic remains the same, but now operates
    #    on the locally created 'server' object.
    async def monitor_cancellation():
        """Checks for cancellation and triggers a graceful server shutdown."""
        while not cancellation_token.IsCancellationRequested:
            await anyio.sleep(1)
        PostMessage("backend:info", "检测到取消请求，正在关闭服务器...")
        server.should_exit = True

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(server.serve)
        task_group.start_soon(monitor_cancellation)

    PostMessage("backend:info", "服务器已关闭。")


# --- Main execution block ---
try:
    # Each time the script is run, it calls the main async function.
    anyio.run(main_app_logic)
except KeyboardInterrupt:
    PostMessage("backend:info", "Ctrl+C 按下，退出。")
finally:
    # This logic correctly reports the final status.
    # Note: 'execution_id' might not be defined if the script fails early.
    exec_id = locals().get('execution_id', 'unknown')
    if 'cancellation_token' in locals() and cancellation_token.IsCancellationRequested:
        PostMessage("backend:info", f"\n[ID:{exec_id}][Python] Cancellation detected. Uvicorn has been shut down.")
    else:
        PostMessage("backend:info", f"[ID:{exec_id}][Python] Uvicorn server shut down normally. Script finished.")

#endregion