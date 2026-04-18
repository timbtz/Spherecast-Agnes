from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).parent.parent.parent


@dataclass
class AgnesContext:
    run_id: str
    pipeline_name: str
    trigger_source: str
    trigger_payload: dict[str, Any] = field(default_factory=dict)
    node_outputs: dict[str, Any] = field(default_factory=dict)  # node_id → output dict
    enriched_db_path: Path = field(default_factory=lambda: _PROJECT_ROOT / "db_enriched.sqlite")
    orchestration_db_path: Path = field(default_factory=lambda: _PROJECT_ROOT / "orchestration.db")

    def get(self, node_id: str, default: Any = None) -> Any:
        return self.node_outputs.get(node_id, default)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "pipeline_name": self.pipeline_name,
            "trigger_source": self.trigger_source,
            "trigger_payload": self.trigger_payload,
            "node_outputs": self.node_outputs,
        }
