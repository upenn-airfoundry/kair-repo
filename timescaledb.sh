#!/bin/bash
source .env
docker pull timescale/timescaledb-ha:pg17
docker run -d --name timescaledb -p 5432:5432 -e POSTGRES_PASSWORD=${DB_PASSWORD} timescale/timescaledb-ha:pg17
#psql -d "postgres://postgres:${DB_PASSWORD}@localhost/postgres" -f create_db.sql

