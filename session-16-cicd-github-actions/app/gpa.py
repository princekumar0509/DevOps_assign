"""Grade-point maths on a 10-point scale (the scale my university uses)."""

GRADE_POINTS = {"O": 10, "A+": 9, "A": 8, "B+": 7, "B": 6, "C": 5, "P": 4, "F": 0}


def grade_point(grade):
    """Return the grade point for a letter grade, case-insensitively."""
    key = str(grade).strip().upper()
    if key not in GRADE_POINTS:
        raise ValueError(f"unknown grade '{grade}', expected one of {', '.join(GRADE_POINTS)}")
    return GRADE_POINTS[key]


def sgpa(courses):
    """Credit-weighted average of one semester.

    courses: iterable of {"grade": "A+", "credits": 4}
    """
    courses = list(courses)
    if not courses:
        raise ValueError("at least one course is required")
    total_credits = 0
    weighted = 0
    for course in courses:
        credits = course.get("credits")
        if not isinstance(credits, (int, float)) or credits <= 0:
            raise ValueError("credits must be a positive number")
        total_credits += credits
        weighted += credits * grade_point(course.get("grade", ""))
    return round(weighted / total_credits, 2)


def cgpa(semesters):
    """Credit-weighted average across semesters.

    semesters: iterable of {"sgpa": 8.5, "credits": 22}
    """
    semesters = list(semesters)
    if not semesters:
        raise ValueError("at least one semester is required")
    total_credits = sum(s["credits"] for s in semesters)
    if total_credits <= 0:
        raise ValueError("total credits must be positive")
    for s in semesters:
        if not 0 <= s["sgpa"] <= 10:
            raise ValueError("sgpa must be between 0 and 10")
    return round(sum(s["sgpa"] * s["credits"] for s in semesters) / total_credits, 2)


def to_percentage(cgpa_value):
    """Common CGPA-to-percentage conversion used on Indian transcripts (x 9.5)."""
    if not 0 <= cgpa_value <= 10:
        raise ValueError("cgpa must be between 0 and 10")
    return round(cgpa_value * 9.5, 2)
