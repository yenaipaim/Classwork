"""内置工具：当前时间与闰年判断。

两者都是无副作用的纯函数，返回值直接作为工具结果文本。
"""

from __future__ import annotations

from datetime import datetime

from ..errors import ToolError

WEEKDAYS = "一二三四五六日"


def get_date() -> str:
    """返回本地日期、时间、星期与 UTC 偏移，例如 ``2026-08-15 09:30:00 星期六（UTC+0800）``。"""
    now = datetime.now().astimezone()
    return "%s 星期%s（UTC%s）" % (
        now.strftime("%Y-%m-%d %H:%M:%S"),
        WEEKDAYS[now.weekday()],
        now.strftime("%z"),
    )


def is_leap_year(year: int | str) -> str:
    """判断年份是否为闰年；兼容模型把年份写成字符串的情况。"""
    if isinstance(year, str):
        text = year.strip()
        if text.lstrip("-").isdigit():
            year = int(text)
    if isinstance(year, bool) or not isinstance(year, int):
        raise ToolError("参数错误：年份必须是整数")
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    if leap:
        return "%d 年是闰年" % year
    return "%d 年不是闰年" % year