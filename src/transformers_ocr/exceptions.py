# Copyright: Ren Tatsumoto <tatsu at autistici.org> and contributors
# Copyright: fkzys and contributors
# License: GNU GPL, version 3 or later; http://www.gnu.org/licenses/gpl.html

"""All custom exceptions in one place."""


class MissingProgram(RuntimeError):
    pass


class StopRequested(Exception):
    pass


class ScreenshotCancelled(RuntimeError):
    pass
