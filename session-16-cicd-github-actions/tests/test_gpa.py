import pytest

from app.gpa import cgpa, grade_point, sgpa, to_percentage


def test_grade_point_is_case_insensitive():
    assert grade_point("a+") == 9
    assert grade_point(" O ") == 10


def test_unknown_grade_is_rejected():
    with pytest.raises(ValueError):
        grade_point("Z")


def test_sgpa_is_credit_weighted():
    courses = [
        {"grade": "O", "credits": 4},   # 40
        {"grade": "A", "credits": 3},   # 24
        {"grade": "B+", "credits": 1},  # 7
    ]
    assert sgpa(courses) == round(71 / 8, 2)


def test_sgpa_needs_positive_credits():
    with pytest.raises(ValueError):
        sgpa([{"grade": "A", "credits": 0}])


def test_sgpa_needs_courses():
    with pytest.raises(ValueError):
        sgpa([])


def test_cgpa_weights_semesters_by_credits():
    semesters = [{"sgpa": 8.0, "credits": 20}, {"sgpa": 9.0, "credits": 30}]
    assert cgpa(semesters) == 8.6


def test_cgpa_rejects_out_of_range_sgpa():
    with pytest.raises(ValueError):
        cgpa([{"sgpa": 11, "credits": 20}])


def test_percentage_conversion():
    assert to_percentage(8.6) == 81.7
