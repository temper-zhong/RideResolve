FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY rideresolve ./rideresolve
COPY data ./data
COPY api ./api
COPY container_entrypoint.py ./

RUN pip install --no-cache-dir .

ENV PORT=8080
EXPOSE 8080

CMD ["python", "container_entrypoint.py"]
