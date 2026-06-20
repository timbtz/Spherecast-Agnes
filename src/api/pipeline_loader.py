from pathlib import Path
import yaml

from orchestration.api.pipeline_def import Pipeline, PipelineNode

_PIPELINES_DIR = Path(__file__).parent.parent / "pipelines"


def load(name: str) -> Pipeline:
    path = _PIPELINES_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Pipeline not found: {name}")
    raw = yaml.safe_load(path.read_text())
    nodes = [
        PipelineNode(
            id=n["id"],
            agent_class=n.get("agent_class"),
            tool_class=n.get("tool_class"),
            depends_on=n.get("depends_on", []),
            when=n.get("when"),
        )
        for n in raw.get("nodes", [])
    ]
    return Pipeline(name=raw["name"], trigger=raw.get("trigger", "manual"), nodes=nodes)


def list_pipelines() -> list[str]:
    return [p.stem for p in _PIPELINES_DIR.glob("*.yaml")]
