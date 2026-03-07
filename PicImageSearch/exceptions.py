class ParsingError(Exception):
    def __init__(self, message: str, engine: str, details: str = ""):
        self.engine: str = engine
        full_msg = f"[{engine}] {message}"
        if details:
            full_msg += f"\n Details: {details}"
        super().__init__(full_msg)
