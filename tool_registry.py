from system_actions import (
    close_app,
    open_app,
    close_external_app,
    shutdown_pc,
    restart_pc,
    kill_process
)


class ToolRegistry:

    def __init__(self):

        self.tools = {}

    def register(self, name, func):

        self.tools[name] = func

    def get(self, name):

        return self.tools.get(name)

    def list_tools(self):

        return list(self.tools.keys())


# ---------- GLOBAL REGISTRY ----------

registry = ToolRegistry()


# ---------- REGISTER SYSTEM ACTIONS ----------

registry.register("close_app",          close_app)

registry.register("open_app",           open_app)

registry.register("close_external_app", close_external_app)

registry.register("shutdown_pc",        shutdown_pc)

registry.register("restart_pc",         restart_pc)

registry.register("kill_process",       kill_process)