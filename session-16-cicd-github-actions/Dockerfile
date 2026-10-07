# ---- build stage: produce the wheel
FROM python:3.12-slim AS build
WORKDIR /src
RUN pip install --no-cache-dir build==1.6.1
COPY pyproject.toml ./
COPY app ./app
RUN python -m build --wheel --outdir /dist .

# ---- runtime stage: only the wheel, gunicorn and a non-root user
FROM python:3.12-slim
ARG BUILD_SHA=local
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BUILD_SHA=${BUILD_SHA}
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir --no-deps /tmp/*.whl && rm /tmp/*.whl \
 && useradd --uid 10001 --no-create-home appuser
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:8000/health'); sys.exit(0)"
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "app.web:app"]
