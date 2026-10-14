from dataclasses import asdict, dataclass, field, fields
from typing import Any


@dataclass
class Host:
    id: str
    label: str
    hostname: str
    alias: str | None = None
    user: str = ""
    port: int = 22
    port_explicit: bool = True
    identities: list[str] = field(default_factory=list)
    jump: str = ""
    config_path: str = ""
    extra_args: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    favorite: bool = False
    hidden: bool = False
    production: bool = False
    custom: bool = False
    last_used: float = 0.0
    uses: int = 0
    order: int = 0
    overrides: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Host":
        return cls(**{f.name: data[f.name] for f in fields(cls) if f.name in data})

    @property
    def destination(self) -> str:
        return f"{self.user}@{self.hostname}" if self.user else self.hostname

    @property
    def history(self) -> bool:
        return any(s.startswith("history:") for s in self.sources)


@dataclass
class LaunchRequest:
    host: Host
    command: str | None = None
