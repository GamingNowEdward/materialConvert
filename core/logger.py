class Logger:

    def __init__(self):
        self._lines = []
        self._callback = None

    def set_callback(self, callback):
        self._callback = callback

    def log(self, message, error=False):
        self._lines.append(message)
        if self._callback:
            self._callback(message, error=error)

    def get_lines(self):
        return list(self._lines)

    def clear(self):
        self._lines.clear()
