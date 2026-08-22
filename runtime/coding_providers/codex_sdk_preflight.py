"""Fail-closed configuration and live preflight for the local Codex SDK."""

from __future__ import annotations

import hashlib
import importlib
import os
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from runtime.coding_providers.errors import (
    ProviderConfigurationError,
    ProviderPolicyError,
    ProviderStateError,
)


_PROVIDER_ID = "openai-codex-sdk"
_PREFLIGHT_TOKEN = "ASCOS_CODEX_PREFLIGHT_OK"
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ENVIRONMENT_NAME = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class CodexSdkPreflightStatus(str, Enum):
    CONFIGURATION_READY = "CONFIGURATION_READY"
    LIVE_VERIFIED = "LIVE_VERIFIED"


class CodexAuthenticationMode(str, Enum):
    CHATGPT_SUBSCRIPTION = "chatgpt-subscription"
    PLATFORM_API_KEY = "platform-api-key"


class CodexBillingSource(str, Enum):
    CHATGPT_PLAN = "chatgpt-plan"
    OPENAI_PLATFORM = "openai-platform"


@dataclass(frozen=True)
class CodexSdkPreflightConfiguration:
    """Operator-selected inputs. No credential value is represented here."""

    workspace_root: Path
    model: str
    authentication_mode: CodexAuthenticationMode
    enabled: bool = False
    live_operation_confirmed: bool = False
    api_key_environment: str = "OPENAI_API_KEY"
    maximum_response_characters: int = 256

    def __post_init__(self) -> None:
        if not isinstance(self.workspace_root, Path):
            raise ProviderConfigurationError("Codex workspace root must be a Path")
        if not isinstance(self.model, str) or not _MODEL.fullmatch(self.model):
            raise ProviderConfigurationError("Approved Codex model identifier is invalid")
        if not isinstance(self.authentication_mode, CodexAuthenticationMode):
            raise ProviderConfigurationError("Codex authentication mode is invalid")
        if not isinstance(self.api_key_environment, str) or not _ENVIRONMENT_NAME.fullmatch(
            self.api_key_environment
        ):
            raise ProviderConfigurationError("Codex credential environment name is invalid")
        if self.api_key_environment != "OPENAI_API_KEY":
            raise ProviderConfigurationError(
                "Codex SDK credential environment must be OPENAI_API_KEY"
            )
        if not 64 <= self.maximum_response_characters <= 4_096:
            raise ProviderConfigurationError("Codex preflight response limit is invalid")


@dataclass(frozen=True)
class CodexSdkPreflightResult:
    provider_id: str
    model: str
    status: CodexSdkPreflightStatus
    authentication_mode: CodexAuthenticationMode
    billing_source: CodexBillingSource
    credential_environment: str | None
    credential_available: bool
    account_plan: str | None
    sdk_available: bool
    sandbox: str
    workspace_digest: str
    checked_at: datetime


class CodexSdkPreflight:
    """Prove that Codex can be invoked without granting product-write authority."""

    def __init__(
        self,
        *,
        environment=None,
        sdk_loader=None,
        workspace_observer=None,
        clock=None,
    ) -> None:
        self.environment = dict(os.environ if environment is None else environment)
        self.sdk_loader = sdk_loader or _load_codex_sdk
        self.workspace_observer = workspace_observer or _git_workspace_digest
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def inspect(self, configuration: CodexSdkPreflightConfiguration) -> CodexSdkPreflightResult:
        workspace = self._validate(configuration)
        bindings = self._load_sdk()
        if configuration.authentication_mode == CodexAuthenticationMode.PLATFORM_API_KEY:
            return self._result(
                configuration,
                status=CodexSdkPreflightStatus.CONFIGURATION_READY,
                workspace_digest=self.workspace_observer(workspace),
                account_plan=None,
            )
        with self._verified_codex(bindings, configuration) as (_codex, account_plan):
            return self._result(
                configuration,
                status=CodexSdkPreflightStatus.CONFIGURATION_READY,
                workspace_digest=self.workspace_observer(workspace),
                account_plan=account_plan,
            )

    def run_live_check(
        self,
        configuration: CodexSdkPreflightConfiguration,
        *,
        confirm_usage_consumption: bool = False,
    ) -> CodexSdkPreflightResult:
        workspace = self._validate(configuration)
        if not configuration.live_operation_confirmed:
            raise ProviderPolicyError("Live Codex operation is not persistently authorized")
        if not confirm_usage_consumption:
            raise ProviderPolicyError("A separate usage-consumption confirmation is required")
        bindings = self._load_sdk()
        before = self.workspace_observer(workspace)
        try:
            with self._verified_codex(bindings, configuration) as (codex, account_plan):
                thread = codex.thread_start(
                    model=configuration.model,
                    sandbox=bindings.Sandbox.read_only,
                    cwd=str(workspace),
                )
                result = thread.run(
                    "Reply with exactly ASCOS_CODEX_PREFLIGHT_OK. "
                    "Do not inspect, create, edit, delete, or execute any file."
                )
            response = str(result.final_response)
        except Exception as error:
            raise ProviderStateError(
                f"Codex SDK preflight failed ({type(error).__name__})"
            ) from error
        if len(response) > configuration.maximum_response_characters:
            raise ProviderStateError("Codex SDK preflight response exceeded its limit")
        if response.strip() != _PREFLIGHT_TOKEN:
            raise ProviderStateError("Codex SDK preflight returned an unexpected response")
        after = self.workspace_observer(workspace)
        if after != before:
            raise ProviderPolicyError("Codex SDK preflight changed the read-only workspace")
        return self._result(
            configuration,
            status=CodexSdkPreflightStatus.LIVE_VERIFIED,
            workspace_digest=after,
            account_plan=account_plan,
        )

    def _validate(self, configuration: CodexSdkPreflightConfiguration) -> Path:
        if not configuration.enabled:
            raise ProviderConfigurationError("Codex SDK provider is disabled")
        if configuration.authentication_mode == CodexAuthenticationMode.PLATFORM_API_KEY:
            credential = self.environment.get(configuration.api_key_environment)
            if not credential:
                raise ProviderConfigurationError(
                    "Configured Codex Platform API credential is unavailable"
                )
        path = configuration.workspace_root.expanduser()
        if path.is_symlink():
            raise ProviderConfigurationError("Codex workspace cannot be a symbolic link")
        try:
            workspace = path.resolve(strict=True)
        except (FileNotFoundError, OSError) as error:
            raise ProviderConfigurationError("Codex workspace does not exist") from error
        if not workspace.is_dir():
            raise ProviderConfigurationError("Codex workspace is not a directory")
        if workspace == Path(workspace.anchor):
            raise ProviderConfigurationError("Codex workspace cannot be a filesystem root")
        return workspace

    def _load_sdk(self):
        try:
            bindings = self.sdk_loader()
        except (ImportError, ModuleNotFoundError) as error:
            raise ProviderConfigurationError(
                "Codex SDK is unavailable; install the codex optional dependency"
            ) from error
        if (
            not hasattr(bindings, "Codex")
            or not hasattr(bindings, "CodexConfig")
            or not hasattr(bindings, "Sandbox")
        ):
            raise ProviderConfigurationError("Codex SDK bindings are invalid")
        if not hasattr(bindings.Sandbox, "read_only"):
            raise ProviderConfigurationError("Codex SDK read-only sandbox is unavailable")
        return bindings

    @contextmanager
    def _verified_codex(self, bindings, configuration):
        stack = ExitStack()
        try:
            environment = {
                "CODEX_ACCESS_TOKEN": "",
                "CODEX_API_KEY": "",
                "OPENAI_API_KEY": "",
            }
            if configuration.authentication_mode == CodexAuthenticationMode.PLATFORM_API_KEY:
                codex_home = stack.enter_context(
                    TemporaryDirectory(prefix="ascos-codex-preflight-")
                )
                environment.update(
                    {
                        "CODEX_API_KEY": self.environment[configuration.api_key_environment],
                        "CODEX_HOME": codex_home,
                    }
                )
            sdk_configuration = bindings.CodexConfig(env=environment)
            codex = stack.enter_context(bindings.Codex(sdk_configuration))
            account_plan = (
                self._verify_chatgpt_account(codex)
                if configuration.authentication_mode == CodexAuthenticationMode.CHATGPT_SUBSCRIPTION
                else None
            )
        except (ProviderConfigurationError, ProviderPolicyError):
            stack.close()
            raise
        except Exception as error:
            stack.close()
            raise ProviderConfigurationError(
                f"Codex authentication inspection failed ({type(error).__name__})"
            ) from error
        try:
            yield codex, account_plan
        finally:
            stack.close()

    def _verify_chatgpt_account(self, codex) -> str:
        response = codex.account()
        account = getattr(response, "account", None)
        root = getattr(account, "root", None)
        actual_type = getattr(root, "type", None)
        if actual_type != "chatgpt":
            raise ProviderConfigurationError(
                "Active Codex account does not match the explicitly selected billing mode"
            )
        plan = getattr(root, "plan_type", None)
        value = getattr(plan, "value", plan)
        if not isinstance(value, str) or not value:
            return "unknown"
        return value

    def _result(
        self,
        configuration: CodexSdkPreflightConfiguration,
        *,
        status: CodexSdkPreflightStatus,
        workspace_digest: str,
        account_plan: str | None,
    ) -> CodexSdkPreflightResult:
        chatgpt = configuration.authentication_mode == CodexAuthenticationMode.CHATGPT_SUBSCRIPTION
        return CodexSdkPreflightResult(
            provider_id=_PROVIDER_ID,
            model=configuration.model,
            status=status,
            authentication_mode=configuration.authentication_mode,
            billing_source=(
                CodexBillingSource.CHATGPT_PLAN if chatgpt else CodexBillingSource.OPENAI_PLATFORM
            ),
            credential_environment=(None if chatgpt else configuration.api_key_environment),
            credential_available=True,
            account_plan=account_plan,
            sdk_available=True,
            sandbox="read-only",
            workspace_digest=workspace_digest,
            checked_at=self.clock(),
        )


def _load_codex_sdk():
    return importlib.import_module("openai_codex")


def _git_workspace_digest(workspace: Path) -> str:
    environment = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
    }
    observations = []
    for arguments in (
        ("git", "rev-parse", "HEAD"),
        ("git", "status", "--porcelain=v1", "--untracked-files=all"),
    ):
        try:
            result = subprocess.run(
                arguments,
                cwd=workspace,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ProviderConfigurationError("Codex workspace Git inspection failed") from error
        if result.returncode != 0:
            raise ProviderConfigurationError("Codex workspace is not an inspectable Git repository")
        observations.append(result.stdout)
    return hashlib.sha256("\0".join(observations).encode("utf-8")).hexdigest()
