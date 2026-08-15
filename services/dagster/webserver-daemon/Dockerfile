# Shared image for both dagster-webserver and dagster-daemon — same package
# set for both, per Dagster's own official docker-compose example
# (dagster-io/dagster/examples/deploy_docker/Dockerfile_dagster). Neither
# needs your actual pipeline code — that lives only in ../user-code/.
FROM python:3.13-slim

RUN pip install --no-cache-dir \
    dagster==1.13.18 \
    dagster-graphql==1.13.18 \
    dagster-webserver==1.13.18 \
    dagster-postgres==0.29.18 \
    dagster-docker==0.29.18

ENV DAGSTER_HOME=/opt/dagster/dagster_home/
RUN mkdir -p $DAGSTER_HOME

COPY dagster.yaml workspace.yaml $DAGSTER_HOME

WORKDIR $DAGSTER_HOME
