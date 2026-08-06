from unittest.mock import MagicMock, call

import pytest

from parking_chatbot import cli


def run_cli(
    monkeypatch: pytest.MonkeyPatch,
    inputs: list[str | BaseException],
    responses: list[str | BaseException] | None = None,
) -> tuple[MagicMock, MagicMock]:
    chatbot = MagicMock()
    if responses is not None:
        chatbot.chat.side_effect = responses
    chatbot_class = MagicMock(return_value=chatbot)
    monkeypatch.setattr(cli, "create_stage1_chatbot", chatbot_class)
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=inputs))

    cli.main([])

    return chatbot_class, chatbot


def test_normal_message_is_passed_to_chatbot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, chatbot = run_cli(
        monkeypatch,
        ["hello", "exit"],
        ["Hello!"],
    )

    chatbot.chat.assert_called_once_with("hello")


def test_chatbot_response_is_printed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_cli(monkeypatch, ["hello", "exit"], ["Hello!"])

    assert "Bot: Hello!" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["exit", "quit", " EXIT ", "QUIT"])
def test_exit_commands_stop_program(
    command: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, chatbot = run_cli(monkeypatch, [command])

    assert "Goodbye!" in capsys.readouterr().out
    chatbot.chat.assert_not_called()


def test_empty_message_error_is_printed(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    run_cli(
        monkeypatch,
        ["", "exit"],
        [ValueError("message must not be empty")],
    )

    assert "Bot: message must not be empty" in capsys.readouterr().out


@pytest.mark.parametrize("error", [KeyboardInterrupt(), EOFError()])
def test_terminal_interrupt_exits_cleanly(
    error: BaseException,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, chatbot = run_cli(monkeypatch, [error])

    assert "Goodbye!" in capsys.readouterr().out
    chatbot.chat.assert_not_called()


def test_one_chatbot_instance_is_reused_for_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chatbot_class, chatbot = run_cli(
        monkeypatch,
        ["first", "second", "quit"],
        ["First response", "Second response"],
    )

    chatbot_class.assert_called_once_with()
    assert chatbot.chat.call_args_list == [call("first"), call("second")]


def test_stage2_mode_uses_application_factory_and_closes_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chatbot = MagicMock()
    application = MagicMock()
    application.chatbot = chatbot
    application_factory = MagicMock(return_value=application)
    monkeypatch.setattr(cli, "create_stage2_application", application_factory)
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=["exit"]))

    cli.main(["--with-admin-approval"])

    application_factory.assert_called_once_with()
    application.close.assert_called_once_with()
    chatbot.chat.assert_not_called()


def test_stage3_mode_uses_application_factory_and_closes_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chatbot = MagicMock()
    application = MagicMock()
    application.chatbot = chatbot
    application_factory = MagicMock(return_value=application)
    monkeypatch.setattr(cli, "create_stage3_application", application_factory)
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=[EOFError()]))

    cli.main(["--with-confirmed-processing"])

    application_factory.assert_called_once_with()
    application.close.assert_called_once_with()
    chatbot.chat.assert_not_called()


def test_stage_flags_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(["--with-admin-approval", "--with-confirmed-processing"])

    assert caught.value.code == 2


@pytest.mark.parametrize(
    ("flag", "factory_name"),
    [
        ("--with-admin-approval", "create_stage2_application"),
        ("--with-confirmed-processing", "create_stage3_application"),
    ],
)
@pytest.mark.parametrize("terminal_input", ["exit", EOFError(), KeyboardInterrupt()])
def test_application_modes_close_for_every_terminal_exit(
    flag: str,
    factory_name: str,
    terminal_input: str | BaseException,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = MagicMock()
    application.chatbot = MagicMock()
    application_factory = MagicMock(return_value=application)
    monkeypatch.setattr(cli, factory_name, application_factory)
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=[terminal_input]))

    cli.main([flag])

    application.close.assert_called_once_with()


def test_stage4_mode_routes_messages_with_one_stable_thread_id(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    application = MagicMock()
    application.approval_poll_interval_seconds = 2.0
    application.orchestration.start_or_continue.side_effect = [
        {"response": "First"},
        {"response": "Second"},
    ]
    application_factory = MagicMock(return_value=application)
    monitor = MagicMock()
    monitor_factory = MagicMock(return_value=monitor)
    monkeypatch.setattr(cli, "create_stage4_application", application_factory)
    monkeypatch.setattr(cli, "ApprovalMonitor", monitor_factory)
    monkeypatch.setattr(cli, "uuid4", MagicMock(return_value="stable-thread"))
    monkeypatch.setattr(
        "builtins.input", MagicMock(side_effect=["first", "second", "exit"])
    )

    cli.main(["--with-langgraph"])

    assert application.orchestration.start_or_continue.call_args_list == [
        call("stable-thread", "first"),
        call("stable-thread", "second"),
    ]
    assert "Bot: First" in capsys.readouterr().out
    monitor.close.assert_called_once_with()
    application.close.assert_called_once_with()


def test_stage4_pending_result_starts_monitor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = MagicMock()
    application.approval_poll_interval_seconds = 2.0
    application.orchestration.start_or_continue.return_value = {
        "response": "pending",
        "approval_status": "pending",
    }
    monitor = MagicMock()
    monkeypatch.setattr(
        cli, "create_stage4_application", MagicMock(return_value=application)
    )
    monkeypatch.setattr(cli, "ApprovalMonitor", MagicMock(return_value=monitor))
    monkeypatch.setattr(cli, "uuid4", MagicMock(return_value="thread-1"))
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=["reserve", "exit"]))

    cli.main(["--with-langgraph"])

    monitor.start.assert_called_once_with("thread-1")


def test_stage4_background_notification_starts_on_clean_line(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    application = MagicMock()
    application.approval_poll_interval_seconds = 2.0
    monitor_factory = MagicMock()

    def create_monitor(
        orchestration: object,
        output: object,
        *,
        interval_seconds: float,
    ) -> MagicMock:
        assert callable(output)
        output("Your reservation has been approved and recorded. Request ID: abc.")
        return MagicMock()

    monitor_factory.side_effect = create_monitor
    monkeypatch.setattr(
        cli,
        "create_stage4_application",
        MagicMock(return_value=application),
    )
    monkeypatch.setattr(cli, "ApprovalMonitor", monitor_factory)
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=["exit"]))

    cli.main(["--with-langgraph"])

    output = capsys.readouterr().out
    assert (
        "\nBot: Your reservation has been approved and recorded. Request ID: abc."
        in output
    )


@pytest.mark.parametrize("terminal_input", ["exit", EOFError(), KeyboardInterrupt()])
def test_stage4_closes_monitor_and_clients_on_every_exit(
    terminal_input: str | BaseException,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = MagicMock()
    application.approval_poll_interval_seconds = 2.0
    monitor = MagicMock()
    monkeypatch.setattr(
        cli, "create_stage4_application", MagicMock(return_value=application)
    )
    monkeypatch.setattr(cli, "ApprovalMonitor", MagicMock(return_value=monitor))
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=[terminal_input]))

    cli.main(["--with-langgraph"])

    monitor.close.assert_called_once_with()
    application.close.assert_called_once_with()


@pytest.mark.parametrize(
    "flags",
    [
        ["--with-langgraph", "--with-admin-approval"],
        ["--with-langgraph", "--with-confirmed-processing"],
    ],
)
def test_stage4_flag_is_mutually_exclusive(flags: list[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(flags)

    assert caught.value.code == 2
