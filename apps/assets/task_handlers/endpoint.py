from .backup.manager import AccountBackupExecutionManager
from .backup.handlers import AccountBackupHandler


class ExecutionManager:
    manager_type = {
        'backup': AccountBackupExecutionManager
    }

    def __new__(cls, execution):
        manager = cls.manager_type[execution.manager_name]
        return manager(execution)


class TaskHandler:
    handler_type = {
        'backup': AccountBackupHandler
    }

    def __new__(cls, task):
        handler = cls.handler_type[task.handler_name]
        return handler(task)
