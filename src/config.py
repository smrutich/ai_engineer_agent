"""Configuration and settings for the AI Engineer Agent system."""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class LLMConfig:
    """LLM provider configuration — mixed model strategy."""

    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    # Model assignments per agent role
    code_model: str = "gpt-4o"  # Builder agent — code generation
    reasoning_model: str = "claude-haiku-4-5-20251001"  # Solutions agent — architecture
    summarization_model: str = "claude-haiku-4-5-20251001"  # Comms agent — long context
    sql_model: str = "gpt-4o"  # Data agent — SQL and dbt


@dataclass
class SlackConfig:
    bot_token: str = field(default_factory=lambda: os.getenv("SLACK_BOT_TOKEN", ""))
    user_token: str = field(default_factory=lambda: os.getenv("SLACK_USER_TOKEN", ""))
    app_token: str = field(default_factory=lambda: os.getenv("SLACK_APP_TOKEN", ""))
    user_id: str = field(default_factory=lambda: os.getenv("SLACK_USER_ID", ""))


@dataclass
class OutlookConfig:
    client_id: str = field(default_factory=lambda: os.getenv("MS_GRAPH_CLIENT_ID", ""))
    client_secret: str = field(default_factory=lambda: os.getenv("MS_GRAPH_CLIENT_SECRET", ""))
    tenant_id: str = field(default_factory=lambda: os.getenv("MS_GRAPH_TENANT_ID", ""))
    redirect_uri: str = field(
        default_factory=lambda: os.getenv("MS_GRAPH_REDIRECT_URI", "http://localhost:8000/callback")
    )

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.tenant_id)


@dataclass
class GitHubConfig:
    token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))


@dataclass
class JiraConfig:
    base_url: str = field(default_factory=lambda: os.getenv("JIRA_BASE_URL", ""))
    email: str = field(default_factory=lambda: os.getenv("JIRA_EMAIL", ""))
    api_token: str = field(default_factory=lambda: os.getenv("JIRA_API_TOKEN", ""))

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.api_token)


@dataclass
class SnowflakeConfig:
    account: str = field(default_factory=lambda: os.getenv("SNOWFLAKE_ACCOUNT", ""))
    user: str = field(default_factory=lambda: os.getenv("SNOWFLAKE_USER", ""))
    password: str = field(default_factory=lambda: os.getenv("SNOWFLAKE_PASSWORD", ""))
    warehouse: str = field(default_factory=lambda: os.getenv("SNOWFLAKE_WAREHOUSE", ""))
    database: str = field(default_factory=lambda: os.getenv("SNOWFLAKE_DATABASE", ""))
    schema: str = field(default_factory=lambda: os.getenv("SNOWFLAKE_SCHEMA", ""))


@dataclass
class Settings:
    """Root settings object."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    slack: SlackConfig = field(default_factory=SlackConfig)
    outlook: OutlookConfig = field(default_factory=OutlookConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    jira: JiraConfig = field(default_factory=JiraConfig)
    snowflake: SnowflakeConfig = field(default_factory=SnowflakeConfig)
    pending_actions_path: str = "pending_actions.json"


settings = Settings()
