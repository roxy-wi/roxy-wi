"""Safe command construction and local process execution helpers."""

from dataclasses import dataclass
import os
import re
import shlex
import subprocess
from typing import Iterable, Iterator, Optional, Sequence, Union

from app.modules.roxywi import logger


CommandArgument = Union[str, int, os.PathLike]
_REMOTE_EXECUTABLE = re.compile(r'^[A-Za-z0-9_./+-]+$')
_DEFAULT_OUTPUT_LIMIT = 1024 * 1024


@dataclass(frozen=True)
class CommandResult:
    args: tuple[str, ...]
    stdout: str
    stderr: str
    return_code: int
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    @property
    def stdout_lines(self) -> list[str]:
        return self.stdout.splitlines()

    @property
    def succeeded(self) -> bool:
        return not self.timed_out and self.return_code == 0


def _normalize_arguments(args: Sequence[CommandArgument]) -> tuple[str, ...]:
    if isinstance(args, (str, bytes)):
        raise TypeError('Command arguments must be a sequence, not a shell command string')

    normalized = tuple(os.fspath(argument) if isinstance(argument, os.PathLike) else str(argument) for argument in args)
    if not normalized or not normalized[0]:
        raise ValueError('Command executable cannot be empty')
    for argument in normalized:
        if any(character in argument for character in ('\x00', '\n', '\r')):
            raise ValueError('Command arguments cannot contain NUL or newline characters')
    return normalized


def _limit_output(output: Optional[str], limit: int) -> tuple[str, bool]:
    output = output or ''
    if isinstance(output, bytes):
        output = output.decode('utf-8', errors='backslashreplace')
    if limit <= 0 or len(output) <= limit:
        return output, False
    return f'{output[:limit]}\n[output truncated]', True


def run_local(
    args: Sequence[CommandArgument],
    *,
    timeout: Optional[float] = 30,
    input_text: Optional[str] = None,
    output_limit: int = _DEFAULT_OUTPUT_LIMIT,
    environment: Optional[dict[str, str]] = None,
) -> CommandResult:
    """Execute one local process without invoking a command shell."""
    normalized_args = _normalize_arguments(args)
    try:
        completed = subprocess.run(
            normalized_args,
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='backslashreplace',
            timeout=timeout,
            env=environment,
            shell=False,
            check=False,
        )
        stdout, stdout_truncated = _limit_output(completed.stdout, output_limit)
        stderr, stderr_truncated = _limit_output(completed.stderr, output_limit)
        return CommandResult(
            args=normalized_args,
            stdout=stdout,
            stderr=stderr,
            return_code=completed.returncode,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )
    except subprocess.TimeoutExpired as exception:
        stdout, stdout_truncated = _limit_output(exception.stdout, output_limit)
        stderr, stderr_truncated = _limit_output(exception.stderr, output_limit)
        return CommandResult(
            args=normalized_args,
            stdout=stdout,
            stderr=stderr or f'Command timed out after {timeout} seconds',
            return_code=-1,
            timed_out=True,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )
    except OSError as exception:
        logger.error('Cannot start local command', error_type=type(exception).__name__)
        return CommandResult(
            args=normalized_args,
            stdout='',
            stderr='error: Cannot start the local command\n',
            return_code=127,
        )


def stream_local(args: Sequence[CommandArgument]) -> Iterator[str]:
    """Stream combined stdout/stderr from one local process without a shell."""
    normalized_args = _normalize_arguments(args)
    process = subprocess.Popen(
        normalized_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='backslashreplace',
        shell=False,
    )
    try:
        if process.stdout is not None:
            yield from iter(process.stdout.readline, '')
    finally:
        if process.stdout is not None:
            process.stdout.close()
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def build_remote_command(
    executable: str,
    args: Iterable[CommandArgument] = (),
    *,
    sudo: bool = False,
    merge_stderr: bool = False,
) -> str:
    """Build a remote POSIX command while treating every argument as data."""
    if not executable or not _REMOTE_EXECUTABLE.fullmatch(executable):
        raise ValueError(f'Invalid remote executable: {executable!r}')
    normalized = _normalize_arguments((executable, *tuple(args)))
    command = shlex.join(normalized)
    if sudo:
        command = f'sudo {command}'
    if merge_stderr:
        command = f'{command} 2>&1'
    return command


def build_remote_pipeline(
    commands: Iterable[tuple[str, Iterable[CommandArgument]]],
    *,
    merge_stderr: bool = False,
) -> str:
    """Build a pipeline from independently quoted remote commands."""
    command_parts = [
        build_remote_command(executable, args)
        for executable, args in commands
    ]
    if not command_parts:
        raise ValueError('Remote pipeline cannot be empty')
    command = ' | '.join(command_parts)
    if merge_stderr:
        command = f'{command} 2>&1'
    return command
