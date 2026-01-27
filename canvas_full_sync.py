import os
import re
import json
from canvasapi import Canvas
from ics import Calendar, Event
from datetime import datetime, timedelta

# --- LOAD SCHEDULE FROM SECRET ---
def load_schedule():
    """
    Loads the user's class schedule from the 'MY_TIMETABLE' secret.
    Expected format: {"CS 363": [1, 3], "MATH 205": [0, 2, 4]}
    """
    timetable_str = os.environ.get("MY_TIMETABLE", "{}")
    try:
        return json.loads(timetable_str)
    except json.JSONDecodeError:
        print("⚠️ Warning: Could not parse MY_TIMETABLE. Check your JSON format.")
        return {}

MY_SCHEDULE = load_schedule()

def get_next_class_date(course_code, posted_date_obj):
    """
    Finds the next class date based on MY_SCHEDULE.
    """
    if not MY_SCHEDULE:
        return None

    # Clean up course code match
    base_code = None
    for key in MY_SCHEDULE:
        if key in course_code:
            base_code = key
            break
    
    if not base_code:
        return None 

    class_days = sorted(MY_SCHEDULE[base_code])
    posted_day_idx = posted_date_obj.weekday()
    
    # Find next day
    days_ahead = 0
    for day in class_days:
        if day > posted_day_idx:
            days_ahead = day - posted_day_idx
            break
    
    if days_ahead == 0:
        days_ahead = (7 - posted_day_idx) + class_days[0]
        
    return posted_date_obj + timedelta(days=days_ahead)

def find_date_in_text(text, default_date_str, course_code=""):
    if not text:
        return datetime.strptime(default_date_str, "%Y-%m-%d")

    posted_date_obj = datetime.strptime(default_date_str[:10], "%Y-%m-%d")
    current_year = datetime.now().year

    # 1. "Next Class" Logic
    if re.search(r"\b(next\s+class|next\s+lecture|next\s+session)\b", text, re.IGNORECASE):
        next_class_date = get_next_class_date(course_code, posted_date_obj)
        if next_class_date:
            print(f"   ✨ Found 'Next Class' in {course_code}: Moved to {next_class_date.date()}")
            return next_class_date

    # 2. Explicit Date Logic (Regex)
    pattern1 = r"(\d{1,2})(?:st|nd|rd|th)?\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*,?\s*(\d{4})?"
    pattern2 = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\s*,?\s*(\d{4})?"

    match1 = re.search(pattern1, text, re.IGNORECASE)
    match2 = re.search(pattern2, text, re.IGNORECASE)

    try:
        day, month_str, year_str = 0, "", ""
        if match1:
            day, month_str, year_str = int(match1.group(1)), match1.group(2), match1.group(3)
        elif match2:
            month_str, day, year_str = match2.group(1), int(match2.group(2)), match2.group(3)
        else:
            return posted_date_obj

        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
        }
        month = months[month_str.lower()[:3]]
        
        if year_str:
            year = int(year_str)
        else:
            if month < datetime.now().month and (datetime.now().month - month) > 6:
                year = current_year + 1
            else:
                year = current_year

        return datetime(year, month, day)

    except Exception:
        return posted_date_obj

def main():
    API_URL = os.environ["CANVAS_API_URL"]
    API_KEY = os.environ["CANVAS_API_KEY"]
    canvas = Canvas(API_URL, API_KEY)
    cal = Calendar()
    
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    print("🔄 Syncing...")

    courses = canvas.get_courses(enrollment_state='active')
    
    for course in courses:
        try:
            # Assignments
            for assign in course.get_assignments(bucket='upcoming'):
                if assign.due_at:
                    e = Event()
                    e.name = f"📝 {assign.name} ({course.course_code})"
                    e.begin = assign.due_at
                    e.description = assign.html_url
                    cal.events.add(e)
            
            # Announcements
# B. Announcements (Updated to read the MESSAGE body too)
            for ann in course.get_discussion_topics(only_announcements=True):
                if ann.posted_at and ann.posted_at > start_date:
                    e = Event()
                    
                    # Combine Title + Message so we don't miss dates hidden in the text
                    full_text = f"{ann.title} {ann.message}"
                    
                    # PASS THE FULL TEXT HERE
                    parsed_date = find_date_in_text(full_text, ann.posted_at, course.course_code)
                    
                    e.name = f"📢 {ann.title} ({course.course_code})"
                    e.begin = parsed_date
                    e.make_all_day()
                    e.description = f"Originally Posted: {ann.posted_at[:10]}\n{ann.html_url}\n\n{ann.message[:200]}..."
                    cal.events.add(e)

        except Exception as e:
            pass

    # Generic Calendar Events
    try:
        user = canvas.get_current_user()
        for event in user.get_calendar_events(start_date=start_date):
            e = Event()
            e.name = f"🗓️ {event.title}"
            e.begin = event.start_at
            cal.events.add(e)
    except:
        pass

    with open('my_schedule.ics', 'w', encoding='utf-8') as f:
        f.writelines(cal)
    
    print("✅ Success!")

if __name__ == "__main__":
    main()

