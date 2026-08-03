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
