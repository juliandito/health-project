# Define base image as an argument
ARG PYTHON_BASE=python:3.12-alpine

#######################################################################################
# Stage 1: builder - build Python dependency wheels
#######################################################################################
FROM ${PYTHON_BASE} AS builder
WORKDIR /build
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

#######################################################################################
# Stage 2: runtime - install only runtime dependencies and app code, then run as non-root.
#######################################################################################
FROM ${PYTHON_BASE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Add group and user
RUN addgroup --system appgroup
RUN adduser --system --ingroup appgroup --home /home/appuser appuser

# Install dependencies from prebuilt wheels + remove wheels directory.
COPY --from=builder /wheels /wheels
COPY requirements.txt ./
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt
RUN rm -rf /wheels

# Copy + change ownership.
COPY --chown=appuser:appgroup main.py ./

USER appuser

EXPOSE 8000

# HEALTHCHECK without curl
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]