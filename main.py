import argparse
import hashlib
import json
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import xlrd
from icalendar import Alarm, Calendar, Event

WEEK_TOKEN = re.compile(r"(\d+)(?:-(\d+))?周")

TIME_SLOTS_BY_SEASON = {
    "summer": [
        (1, "08:00", "08:50"),
        (2, "09:00", "09:50"),
        (3, "10:10", "11:00"),
        (4, "11:10", "12:00"),
        (5, "14:30", "15:20"),
        (6, "15:30", "16:20"),
        (7, "16:40", "17:30"),
        (8, "17:40", "18:30"),
        (9, "19:40", "20:30"),
        (10, "20:40", "21:30"),
        (11, "21:40", "22:30"),
    ],
    "winter": [
        (1, "08:00", "08:50"),
        (2, "09:00", "09:50"),
        (3, "10:10", "11:00"),
        (4, "11:10", "12:00"),
        (5, "14:00", "14:50"),
        (6, "15:00", "15:50"),
        (7, "16:10", "17:00"),
        (8, "17:10", "18:00"),
        (9, "19:10", "20:00"),
        (10, "20:10", "21:00"),
        (11, "21:10", "22:00"),
    ],
}

CONFIG = {
    "semesterTotalWeeks": 16,
    "defaultClassDuration": 50,
    "defaultBreakDuration": 10,
    "firstDayOfWeek": 1,
}

ALARM_LEAD_MINUTES = 10

LEGACY_JSON = Path("课表.json")


def clean(value):
    return str(value).replace("\u3000", " ").replace("，", ",").replace("\n", " ").strip()


def parse_weeks(text):
    weeks = set()
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        match = WEEK_TOKEN.fullmatch(token)
        if not match:
            raise ValueError(f"无法解析周次片段: {token!r} (完整字段: {text!r})")
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        if start > end:
            raise ValueError(f"周次区间无效: {token!r} (完整字段: {text!r})")
        weeks.update(range(start, end + 1))
    if not weeks:
        raise ValueError(f"周次为空: {text!r}")
    return sorted(weeks)


def parse_int(value, field, context):
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field} 不是整数: {value!r} ({context})") from exc


def build_courses(sheet):
    if sheet.ncols < 10:
        raise ValueError(f"列数不足: {sheet.ncols}")
    grouped = {}
    for row in range(1, sheet.nrows):
        cells = [clean(sheet.cell_value(row, col)) for col in range(sheet.ncols)]
        if not any(cells):
            continue
        name = cells[1]
        week_text = cells[4]
        day = parse_int(cells[5], "上课星期", name)
        start_section = parse_int(cells[6], "开始节次", name)
        end_section = parse_int(cells[7], "结束节次", name)
        teacher = cells[8]
        position = cells[9]
        key = (name, teacher, position, day, start_section, end_section)
        weeks = grouped.setdefault(key, set())
        weeks.update(parse_weeks(week_text))
    total_weeks = CONFIG["semesterTotalWeeks"]
    courses = []
    for key, weeks in grouped.items():
        if max(weeks) > total_weeks:
            raise ValueError(f"周次超出学期总周数 {total_weeks}: {key} {sorted(weeks)}")
        name, teacher, position, day, start_section, end_section = key
        courses.append(
            {
                "name": name,
                "teacher": teacher,
                "position": position,
                "day": day,
                "startSection": start_section,
                "endSection": end_section,
                "weeks": sorted(weeks),
            }
        )
    courses.sort(key=lambda c: (c["day"], c["startSection"], c["name"]))
    return courses


def build_json(courses, time_slots, start_date):
    config = dict(CONFIG)
    if start_date is not None:
        config["semesterStartDate"] = start_date.isoformat()
    return {
        "courses": courses,
        "timeSlots": [
            {"number": number, "startTime": start, "endTime": end, "alias": None}
            for number, start, end in time_slots
        ],
        "config": config,
    }


def build_ics(courses, time_slots, start_date):
    tz = ZoneInfo("Asia/Shanghai")
    section_start = {number: start for number, start, _ in time_slots}
    section_end = {number: end for number, _, end in time_slots}
    total_slots = len(time_slots)
    calendar = Calendar()
    calendar.add("prodid", "-//collate-xjtu-timetable//CN")
    calendar.add("version", "2.0")
    calendar.add("calscale", "GREGORIAN")
    calendar.add("x-wr-calname", "课表")
    calendar.add("x-wr-timezone", "Asia/Shanghai")
    event_count = 0
    for course in courses:
        if course["endSection"] > total_slots:
            raise ValueError(f"节次超出时间段定义: {course}")
        for week in course["weeks"]:
            day = start_date + timedelta(days=(week - 1) * 7 + course["day"] - 1)
            dt_start = datetime.combine(day, time.fromisoformat(section_start[course["startSection"]]), tzinfo=tz)
            dt_end = datetime.combine(day, time.fromisoformat(section_end[course["endSection"]]), tzinfo=tz)
            digest = hashlib.sha1(
                "|".join(
                    [
                        course["name"],
                        course["teacher"],
                        course["position"],
                        str(course["day"]),
                        str(course["startSection"]),
                        str(course["endSection"]),
                        str(week),
                        day.isoformat(),
                    ]
                ).encode("utf-8")
            ).hexdigest()
            event = Event()
            event.add("uid", f"{digest}@collate-xjtu-timetable")
            event.add("summary", course["name"])
            if course["position"]:
                event.add("location", course["position"])
            if course["teacher"]:
                event.add("description", course["teacher"])
            event.add("dtstart", dt_start)
            event.add("dtend", dt_end)
            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", "上课提醒")
            alarm.add("trigger", timedelta(minutes=-ALARM_LEAD_MINUTES))
            event.add_component(alarm)
            calendar.add_component(event)
            event_count += 1
    calendar.add_missing_timezones()
    return calendar, event_count


def parse_start_date(text):
    try:
        start_date = date.fromisoformat(text)
    except ValueError as exc:
        raise SystemExit(f"--start-date 格式错误, 应为 YYYY-MM-DD: {text!r}") from exc
    if start_date.weekday() != 0:
        raise SystemExit(f"--start-date 必须是周一: {start_date} 是星期{start_date.weekday() + 1}")
    return start_date


SEASON_LABEL = {
    "summer": "夏季(5/1-10/1)",
    "winter": "冬季(10/1-次年5/1)",
}


def auto_season(today):
    if (5, 1) <= (today.month, today.day) < (10, 1):
        return "summer"
    return "winter"


def parse_args():
    parser = argparse.ArgumentParser(description="将西交课表.xls转换为课表JSON/ICS")
    parser.add_argument(
        "--season",
        choices=sorted(TIME_SLOTS_BY_SEASON),
        default=None,
        help="作息季节: summer=5/1-10/1, winter=10/1-次年5/1; 不指定时按当天日期自动判断",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        metavar="YYYY-MM-DD",
        help="第1周周一的日期; 提供后额外导出ICS并写入semesterStartDate",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    today = date.today()
    season = args.season or auto_season(today)
    source = "手动指定" if args.season else "自动判断"
    print(f"使用{SEASON_LABEL[season]}作息: {source} (今天 {today})")
    start_date = parse_start_date(args.start_date) if args.start_date else None
    if LEGACY_JSON.exists():
        LEGACY_JSON.unlink()
        print(f"已删除旧文件: {LEGACY_JSON}")
    workbook = xlrd.open_workbook("课表.xls")
    courses = build_courses(workbook.sheet_by_index(0))
    time_slots = TIME_SLOTS_BY_SEASON[season]
    data = build_json(courses, time_slots, start_date)
    Path("timetable.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"共输出 {len(courses)} 条课程记录 -> timetable.json")
    if start_date is None:
        print("未提供 --start-date, 跳过ICS导出")
        return
    calendar, event_count = build_ics(courses, time_slots, start_date)
    Path("timetable.ics").write_bytes(calendar.to_ical())
    print(f"共导出 {event_count} 个日历事件 -> timetable.ics")


if __name__ == "__main__":
    main()
