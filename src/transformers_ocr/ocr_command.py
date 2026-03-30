# Copyright: Ren Tatsumoto <tatsu at autistici.org> and contributors
# Copyright: fkzys and contributors
# License: GNU GPL, version 3 or later; http://www.gnu.org/licenses/gpl.html

"""Validated data contract for the FIFO protocol."""

import dataclasses
import json

VALID_ACTIONS = frozenset({"recognize", "hold", "stop"})


@dataclasses.dataclass
class OcrCommand:
    action: str
    file_path: str | None
    delete_after: bool = False

    def as_json(self) -> str:
        return json.dumps(dataclasses.asdict(self))

    def validate(self) -> "OcrCommand":
        if self.action not in VALID_ACTIONS:
            raise ValueError(f"Invalid action: {self.action!r}")
        if self.action != "stop" and not self.file_path:
            raise ValueError(
                f"file_path is required for action {self.action!r}"
            )
        if self.file_path is not None and not isinstance(self.file_path, str):
            raise TypeError(
                f"file_path must be a string, got {type(self.file_path)}"
            )
        return self
