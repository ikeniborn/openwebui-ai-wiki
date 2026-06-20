FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
ENV OWAW_DATA_DIR=/data
VOLUME ["/data"]
ENTRYPOINT ["owaw"]
CMD ["watch"]
