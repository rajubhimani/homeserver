# Dependencies only — definitions.py is bind-mounted from
# service_data/data/dagster/user-code/ at runtime (compose.yml), not copied
# in here (see docs/services/dagster.md's "Where your pipeline code actually
# lives"). Dagster has no generic pre-built "just runs" webserver/daemon the
# way Airflow or Temporal's server do — a code location IS your pipeline
# code by definition.
FROM python:3.13-slim

RUN pip install --no-cache-dir \
    dagster==1.13.18 \
    dagster-postgres==0.29.18 \
    dagster-docker==0.29.18

WORKDIR /opt/dagster/app

EXPOSE 4000

CMD ["dagster", "api", "grpc", "-h", "0.0.0.0", "-p", "4000", "-f", "definitions.py"]
