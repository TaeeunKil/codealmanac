import json
import os
import tempfile
from pathlib import Path

from pydantic import Field, field_validator

from agentworkmemory.core import AgentWorkMemoryModel
from agentworkmemory.services.curators.models import ReasoningEffort

CONFIG_FILE_NAME = "config.json"
DATABASE_FILE_NAME = "agentworkmemory.db"


class ImprovementProposerSettings(AgentWorkMemoryModel):
    model: str = "gpt-5.6-luna"
    reasoning_effort: ReasoningEffort = ReasoningEffort.XHIGH

    @field_validator("model")
    @classmethod
    def nonblank_model(cls, value: str) -> str:
        model = value.strip()
        if not model:
            raise ValueError("improvement proposer model must not be blank")
        return model


class AgentWorkMemoryConfig(AgentWorkMemoryModel):
    state_dir: Path
    vault_path: Path | None = None
    improvement_proposer: ImprovementProposerSettings = Field(
        default_factory=ImprovementProposerSettings
    )

    @field_validator("state_dir", "vault_path")
    @classmethod
    def absolute_paths(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        return value.expanduser().resolve()

    @property
    def database_path(self) -> Path:
        return self.state_dir / DATABASE_FILE_NAME

    @property
    def config_path(self) -> Path:
        return self.state_dir / CONFIG_FILE_NAME


def default_state_dir() -> Path:
    configured = os.environ.get("AGENTWORKMEMORY_STATE_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and local_app_data:
        return (Path(local_app_data) / "AgentWorkMemory").resolve()
    xdg_state_home = os.environ.get("XDG_STATE_HOME")
    if xdg_state_home:
        return (Path(xdg_state_home) / "agentworkmemory").expanduser().resolve()
    return (Path.home() / ".local" / "state" / "agentworkmemory").resolve()


def load_config(state_dir: Path | None = None) -> AgentWorkMemoryConfig:
    resolved_state = (state_dir or default_state_dir()).expanduser().resolve()
    config_path = resolved_state / CONFIG_FILE_NAME
    vault_path: Path | None = None
    proposer_settings = ImprovementProposerSettings()
    if config_path.is_file():
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        configured_vault = raw.get("vault_path")
        if isinstance(configured_vault, str) and configured_vault.strip():
            vault_path = Path(configured_vault)
        configured_proposer = raw.get("improvement_proposer")
        if configured_proposer is not None:
            proposer_settings = ImprovementProposerSettings.model_validate(
                configured_proposer
            )
    return AgentWorkMemoryConfig(
        state_dir=resolved_state,
        vault_path=vault_path,
        improvement_proposer=proposer_settings,
    )


def save_config(config: AgentWorkMemoryConfig) -> None:
    config.state_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "vault_path": str(config.vault_path) if config.vault_path is not None else None,
        "improvement_proposer": config.improvement_proposer.model_dump(mode="json"),
    }
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=config.state_dir,
            prefix=f".{CONFIG_FILE_NAME}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary = Path(file.name)
            file.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, config.config_path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def configure_improvement_proposer(
    config: AgentWorkMemoryConfig,
    *,
    model: str | None = None,
    reasoning_effort: ReasoningEffort | None = None,
) -> AgentWorkMemoryConfig:
    updated_settings = ImprovementProposerSettings(
        model=(
            config.improvement_proposer.model
            if model is None
            else model
        ),
        reasoning_effort=(
            config.improvement_proposer.reasoning_effort
            if reasoning_effort is None
            else reasoning_effort
        ),
    )
    updated = AgentWorkMemoryConfig(
        state_dir=config.state_dir,
        vault_path=config.vault_path,
        improvement_proposer=updated_settings,
    )
    save_config(updated)
    return updated
