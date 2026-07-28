import os
from dataclasses import dataclass


@dataclass
class DatabaseSettings:
    """MySQL connection settings, read from the environment.

    Kept independent of the YAML-based `Config` (source/target email, LLM,
    language): those describe the learner's newsletter pipeline, this
    describes infrastructure, and the two change for unrelated reasons.
    """

    host: str = "localhost"
    port: int = 3306
    user: str = "polyglot"
    password: str = "polyglot"
    database: str = "polyglot"
    charset: str = "utf8mb4"

    @classmethod
    def from_env(cls) -> "DatabaseSettings":
        return cls(
            host=os.environ.get("DB_HOST", "localhost"),
            port=int(os.environ.get("DB_PORT", "3306")),
            user=os.environ.get("DB_USER", "polyglot"),
            password=os.environ.get("DB_PASSWORD", "polyglot"),
            database=os.environ.get("DB_NAME", "polyglot"),
            charset=os.environ.get("DB_CHARSET", "utf8mb4"),
        )

    @property
    def url(self) -> str:
        return (
            f"mysql+pymysql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}?charset={self.charset}"
        )
