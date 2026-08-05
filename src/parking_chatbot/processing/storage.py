import json
import threading
from contextlib import suppress
from pathlib import Path
from uuid import uuid4

from parking_chatbot.processing.models import ConfirmedReservation

_FILE_WRITE_LOCK = threading.Lock()


class ConfirmedReservationStorageError(RuntimeError):
    pass


class ConfirmedReservationConflictError(ConfirmedReservationStorageError):
    pass


class ConfirmedReservationFileRepository:
    def __init__(self, output_path: Path) -> None:
        self._output_path = output_path
        self._index_path = output_path.with_name(f"{output_path.name}.index.json")

    def append(self, reservation: ConfirmedReservation) -> bool:
        request_id = str(reservation.approval_request_id)
        line = reservation.to_file_line()

        with _FILE_WRITE_LOCK:
            index = self._load_index()
            existing_line = index.get(request_id)
            if existing_line is not None:
                if existing_line == line:
                    return False
                raise ConfirmedReservationConflictError(
                    f"approval request {request_id} already has different data"
                )

            previous_index = index.copy()
            updated_index = {**index, request_id: line}
            index_existed = self._index_path.exists()

            try:
                self._output_path.parent.mkdir(parents=True, exist_ok=True)
                self._write_index_atomically(updated_index)
            except OSError as error:
                raise ConfirmedReservationStorageError(
                    "could not store confirmed reservation"
                ) from error

            try:
                self._append_line(line)
            except OSError as error:
                try:
                    self._restore_index(previous_index, index_existed)
                except OSError as restore_error:
                    raise ConfirmedReservationStorageError(
                        "could not store confirmed reservation"
                    ) from restore_error
                raise ConfirmedReservationStorageError(
                    "could not store confirmed reservation"
                ) from error
        return True

    def _append_line(self, line: str) -> None:
        output_existed = self._output_path.exists()
        original_size = self._output_path.stat().st_size if output_existed else 0
        try:
            with self._output_path.open("a", encoding="utf-8") as output_file:
                output_file.write(line)
        except OSError as error:
            try:
                if output_existed:
                    with self._output_path.open("r+b") as output_file:
                        output_file.truncate(original_size)
                else:
                    self._output_path.unlink(missing_ok=True)
            except OSError as restore_error:
                raise restore_error from error
            raise

    def _write_index_atomically(self, index: dict[str, str]) -> None:
        temporary_path = self._index_path.with_name(
            f".{self._index_path.name}.{uuid4().hex}.tmp"
        )
        try:
            temporary_path.write_text(
                json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temporary_path.replace(self._index_path)
        finally:
            with suppress(OSError):
                temporary_path.unlink(missing_ok=True)

    def _restore_index(
        self,
        previous_index: dict[str, str],
        index_existed: bool,
    ) -> None:
        if index_existed:
            self._write_index_atomically(previous_index)
        else:
            self._index_path.unlink(missing_ok=True)

    def _load_index(self) -> dict[str, str]:
        if not self._index_path.exists():
            return {}
        try:
            index = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConfirmedReservationStorageError(
                "could not load confirmed reservation index"
            ) from error
        if not isinstance(index, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in index.items()
        ):
            raise ConfirmedReservationStorageError(
                "confirmed reservation index has an invalid format"
            )
        return index
