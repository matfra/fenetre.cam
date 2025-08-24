import logging


class ModuleColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG: "\x1b[37m",
        logging.INFO: "\x1b[36m",
        logging.WARNING: "\x1b[33m",
        logging.ERROR: "\x1b[31m",
        logging.CRITICAL: "\x1b[35m",
    }

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        color = self.COLORS.get(record.levelno)
        if not color:
            return base
        if "]" not in base:
            return f"{color}{base}\x1b[0m"
        header, message = base.split("]", 1)
        header += "]"
        return f"{color}{header}\x1b[0m{message}"
