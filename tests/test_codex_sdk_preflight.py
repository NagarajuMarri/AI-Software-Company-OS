from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from runtime.coding_providers.codex_preflight_cli import run
from runtime.coding_providers.codex_sdk_preflight import (
    CodexAuthenticationMode,
    CodexBillingSource,
    CodexSdkPreflight,
    CodexSdkPreflightConfiguration,
    CodexSdkPreflightStatus,
)
from runtime.coding_providers.errors import (
    ProviderConfigurationError,
    ProviderPolicyError,
    ProviderStateError,
)


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)
KEY = "test-credential-do-not-disclose"
EMAIL = "customer@example.test"


class FakeSandbox:
    read_only = "read-only"


class FakeResult:
    final_response = "ASCOS_CODEX_PREFLIGHT_OK"


class FakeThread:
    def __init__(self, observed):
        self.observed = observed

    def run(self, prompt):
        self.observed["prompt"] = prompt
        return FakeResult()


class FakeCodex:
    def __init__(self, observed, account_type, account_plan):
        self.observed = observed
        self.account_type = account_type
        self.account_plan = account_plan

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.observed["closed"] = True

    def thread_start(self, **kwargs):
        self.observed["thread"] = kwargs
        return FakeThread(self.observed)

    def account(self):
        root = SimpleNamespace(type=self.account_type)
        if self.account_type == "chatgpt":
            root.plan_type = SimpleNamespace(value=self.account_plan)
            root.email = EMAIL
        return SimpleNamespace(account=SimpleNamespace(root=root))

    def login_api_key(self, api_key):
        self.observed["api_key_login"] = api_key
        self.account_type = "apiKey"


def bindings(observed=None, *, account_type="apiKey", account_plan="prolite"):
    observed = observed if observed is not None else {}

    def codex(configuration):
        observed["sdk_configuration"] = configuration
        return FakeCodex(observed, account_type, account_plan)

    return SimpleNamespace(
        Codex=codex,
        CodexConfig=lambda **values: SimpleNamespace(**values),
        Sandbox=FakeSandbox,
    )


def configuration(workspace: Path, **values):
    return CodexSdkPreflightConfiguration(
        workspace_root=workspace,
        model=values.pop("model", "gpt-5.6-terra"),
        authentication_mode=values.pop(
            "authentication_mode", CodexAuthenticationMode.PLATFORM_API_KEY
        ),
        enabled=values.pop("enabled", True),
        live_operation_confirmed=values.pop("live_operation_confirmed", True),
        **values,
    )


def checker(
    *,
    observed=None,
    snapshots=None,
    environment=None,
    account_type="apiKey",
    account_plan="prolite",
):
    snapshots = list(snapshots or ["clean-digest"])
    last = snapshots[-1]

    def observe(_workspace):
        return snapshots.pop(0) if snapshots else last

    return CodexSdkPreflight(
        environment={"OPENAI_API_KEY": KEY} if environment is None else environment,
        sdk_loader=lambda: bindings(
            observed,
            account_type=account_type,
            account_plan=account_plan,
        ),
        workspace_observer=observe,
        clock=lambda: NOW,
    )


def test_static_preflight_reports_safe_platform_configuration_readiness(tmp_path):
    result = checker().inspect(configuration(tmp_path))

    assert result.status == CodexSdkPreflightStatus.CONFIGURATION_READY
    assert result.provider_id == "openai-codex-sdk"
    assert result.authentication_mode == CodexAuthenticationMode.PLATFORM_API_KEY
    assert result.billing_source == CodexBillingSource.OPENAI_PLATFORM
    assert result.credential_environment == "OPENAI_API_KEY"
    assert result.credential_available is True
    assert result.account_plan is None
    assert result.sandbox == "read-only"
    assert KEY not in repr(result)
    assert EMAIL not in repr(result)


def test_static_preflight_reports_chatgpt_plan_without_using_api_key(tmp_path):
    observed = {}
    result = checker(
        observed=observed,
        environment={},
        account_type="chatgpt",
        account_plan="prolite",
    ).inspect(
        configuration(
            tmp_path,
            authentication_mode=CodexAuthenticationMode.CHATGPT_SUBSCRIPTION,
        )
    )

    assert result.authentication_mode == CodexAuthenticationMode.CHATGPT_SUBSCRIPTION
    assert result.billing_source == CodexBillingSource.CHATGPT_PLAN
    assert result.credential_environment is None
    assert result.account_plan == "prolite"
    assert observed["sdk_configuration"].env == {
        "CODEX_ACCESS_TOKEN": "",
        "CODEX_API_KEY": "",
        "OPENAI_API_KEY": "",
    }
    assert KEY not in repr(result)
    assert EMAIL not in repr(result)


def test_chatgpt_mode_clears_conflicting_billing_credentials(tmp_path):
    observed = {}
    result = checker(
        observed=observed,
        environment={
            "OPENAI_API_KEY": KEY,
            "CODEX_API_KEY": "another-secret",
            "CODEX_ACCESS_TOKEN": "access-secret",
        },
        account_type="chatgpt",
    ).inspect(
        configuration(
            tmp_path,
            authentication_mode=CodexAuthenticationMode.CHATGPT_SUBSCRIPTION,
        )
    )

    assert observed["sdk_configuration"].env == {
        "CODEX_ACCESS_TOKEN": "",
        "CODEX_API_KEY": "",
        "OPENAI_API_KEY": "",
    }
    assert "another-secret" not in repr(result)
    assert "access-secret" not in repr(result)


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"enabled": False}, "disabled"),
        ({"environment": {}}, "credential"),
    ],
)
def test_static_preflight_fails_closed(tmp_path, values, message):
    environment = values.pop("environment", {"OPENAI_API_KEY": KEY})
    with pytest.raises(ProviderConfigurationError, match=message):
        checker(environment=environment).inspect(configuration(tmp_path, **values))


def test_static_preflight_requires_installed_sdk(tmp_path):
    preflight = CodexSdkPreflight(
        environment={"OPENAI_API_KEY": KEY},
        sdk_loader=lambda: (_ for _ in ()).throw(ModuleNotFoundError("missing")),
        workspace_observer=lambda _workspace: "digest",
    )

    with pytest.raises(ProviderConfigurationError, match="optional dependency"):
        preflight.inspect(configuration(tmp_path))


def test_configuration_rejects_nonstandard_credential_environment(tmp_path):
    with pytest.raises(ProviderConfigurationError, match="must be OPENAI_API_KEY"):
        configuration(tmp_path, api_key_environment="CUSTOM_API_KEY")


def test_chatgpt_preflight_rejects_account_that_does_not_match_billing_mode(tmp_path):
    with pytest.raises(ProviderConfigurationError, match="billing mode"):
        checker(account_type="apiKey").inspect(
            configuration(
                tmp_path,
                authentication_mode=CodexAuthenticationMode.CHATGPT_SUBSCRIPTION,
            )
        )


def test_workspace_symlink_and_filesystem_root_are_rejected(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are unavailable")
    with pytest.raises(ProviderConfigurationError, match="symbolic link"):
        checker().inspect(configuration(link))
    with pytest.raises(ProviderConfigurationError, match="filesystem root"):
        checker().inspect(configuration(Path(Path.cwd().anchor)))


def test_live_preflight_requires_two_independent_confirmations(tmp_path):
    with pytest.raises(ProviderPolicyError, match="persistently"):
        checker().run_live_check(
            configuration(tmp_path, live_operation_confirmed=False),
            confirm_usage_consumption=True,
        )
    with pytest.raises(ProviderPolicyError, match="usage-consumption"):
        checker().run_live_check(configuration(tmp_path))


def test_live_preflight_uses_read_only_codex_and_preserves_workspace(tmp_path):
    observed = {}
    result = checker(observed=observed, snapshots=["before", "before"]).run_live_check(
        configuration(tmp_path),
        confirm_usage_consumption=True,
    )

    assert result.status == CodexSdkPreflightStatus.LIVE_VERIFIED
    assert observed["thread"] == {
        "model": "gpt-5.6-terra",
        "sandbox": "read-only",
        "cwd": str(tmp_path.resolve()),
    }
    assert "Do not inspect" in observed["prompt"]
    assert observed["closed"] is True
    environment = observed["sdk_configuration"].env
    assert environment["CODEX_API_KEY"] == ""
    assert environment["OPENAI_API_KEY"] == ""
    assert environment["CODEX_ACCESS_TOKEN"] == ""
    assert observed["api_key_login"] == KEY
    assert "CODEX_HOME" in environment
    assert not Path(environment["CODEX_HOME"]).exists()
    assert KEY not in repr(result)


def test_live_preflight_rejects_workspace_change_and_unexpected_response(tmp_path):
    with pytest.raises(ProviderPolicyError, match="changed"):
        checker(snapshots=["before", "after"]).run_live_check(
            configuration(tmp_path), confirm_usage_consumption=True
        )

    class WrongResult:
        final_response = "not the token"

    class WrongCodex:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def thread_start(self, **_kwargs):
            return SimpleNamespace(run=lambda _prompt: WrongResult())

        def login_api_key(self, _api_key):
            return None

    wrong = SimpleNamespace(
        Codex=lambda _configuration: WrongCodex(),
        CodexConfig=lambda **values: SimpleNamespace(**values),
        Sandbox=FakeSandbox,
    )
    WrongCodex.account = lambda self: SimpleNamespace(
        account=SimpleNamespace(root=SimpleNamespace(type="apiKey"))
    )
    preflight = CodexSdkPreflight(
        environment={"OPENAI_API_KEY": KEY},
        sdk_loader=lambda: wrong,
        workspace_observer=lambda _workspace: "same",
    )
    with pytest.raises(ProviderStateError, match="unexpected"):
        preflight.run_live_check(configuration(tmp_path), confirm_usage_consumption=True)


def test_live_preflight_redacts_credentials_from_sdk_errors(tmp_path):
    class FailingCodex:
        def __enter__(self):
            raise RuntimeError(f"credential={KEY}")

        def __exit__(self, *_args):
            return None

    failed = SimpleNamespace(
        Codex=lambda _configuration: FailingCodex(),
        CodexConfig=lambda **values: SimpleNamespace(**values),
        Sandbox=FakeSandbox,
    )
    preflight = CodexSdkPreflight(
        environment={"OPENAI_API_KEY": KEY},
        sdk_loader=lambda: failed,
        workspace_observer=lambda _workspace: "same",
    )
    with pytest.raises(ProviderStateError) as observed:
        preflight.run_live_check(configuration(tmp_path), confirm_usage_consumption=True)
    assert KEY not in str(observed.value)


def test_cli_output_contains_no_credential_value(tmp_path):
    value = run(
        (
            "--workspace",
            str(tmp_path),
            "--model",
            "gpt-5.6-terra",
            "--auth-mode",
            "platform-api-key",
            "--enable-live-provider",
        ),
        preflight=checker(),
    )

    assert value["status"] == "CONFIGURATION_READY"
    assert value["authentication_mode"] == "platform-api-key"
    assert value["billing_source"] == "openai-platform"
    assert KEY not in repr(value)


def test_cli_reports_chatgpt_billing_without_credential_environment(tmp_path):
    value = run(
        (
            "--workspace",
            str(tmp_path),
            "--model",
            "gpt-5.6-terra",
            "--auth-mode",
            "chatgpt-subscription",
            "--enable-live-provider",
        ),
        preflight=checker(account_type="chatgpt"),
    )

    assert value["billing_source"] == "chatgpt-plan"
    assert value["credential_environment"] is None
    assert value["account_plan"] == "prolite"
    assert EMAIL not in repr(value)
