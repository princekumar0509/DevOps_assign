"""HTTP API around app.gpa."""

import os

from flask import Flask, jsonify, request

from app import __version__
from app.gpa import GRADE_POINTS, cgpa, sgpa, to_percentage

app = Flask(__name__)

PAGE = """<!doctype html>
<html><head><title>CGPA Calculator</title></head>
<body style="font-family:sans-serif;max-width:640px;margin:40px auto">
<h1>CGPA Calculator</h1>
<p>Session 16 CI/CD demo &middot; version {version} &middot; build {build}</p>
<p>POST <code>/api/sgpa</code> with a list of courses, or <code>/api/cgpa</code> with semesters.</p>
</body></html>"""


def _build_id():
    # injected by the pipeline at image build time (git commit SHA)
    return os.environ.get("BUILD_SHA", "local")[:12]


@app.get("/")
def home():
    return PAGE.format(version=__version__, build=_build_id())


@app.get("/health")
def health():
    return jsonify(status="ok", version=__version__, build=_build_id())


@app.get("/api/grades")
def grades():
    return jsonify(GRADE_POINTS)


@app.post("/api/sgpa")
def api_sgpa():
    body = request.get_json(silent=True) or {}
    try:
        value = sgpa(body.get("courses", []))
    except (ValueError, TypeError, AttributeError) as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(sgpa=value)


@app.post("/api/cgpa")
def api_cgpa():
    body = request.get_json(silent=True) or {}
    try:
        value = cgpa(body.get("semesters", []))
        percent = to_percentage(value)
    except (ValueError, TypeError, KeyError) as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(cgpa=value, percentage=percent)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
