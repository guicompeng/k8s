#!/usr/bin/env python3


from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


DEFAULT_QUERY_URL = "http://10.187.36.245:30082/api/v1/query_range"


@dataclass(frozen=True)
class MetricQuery:
    alias: str
    query: str


DEFAULT_METRICS: List[MetricQuery] = [
    # ======================
    # WORDPRESS / APACHE
    # ======================
    MetricQuery("wordpress_apache_up", "max(apache_up)"),
    MetricQuery("wordpress_http_rps", "sum(rate(apache_accesses_total[2m]))"),
    MetricQuery(
        "wordpress_http_avg_response_seconds",
        "sum(rate(apache_duration_ms_total[2m])) / clamp_min(sum(rate(apache_accesses_total[2m])), 0.001) / 1000",
    ),
    MetricQuery(
        "wordpress_http_avg_response_over_2s",
        "(sum(rate(apache_duration_ms_total[2m])) / clamp_min(sum(rate(apache_accesses_total[2m])), 0.001) / 1000) > bool 2",
    ),

    MetricQuery("wordpress_http_5xx_rate", 'sum(rate(apache_accesses_total{code=~"5.."}[2m]))'),
    MetricQuery("wordpress_http_4xx_rate", 'sum(rate(apache_accesses_total{code=~"4.."}[2m]))'),
    MetricQuery(
        "wordpress_http_5xx_ratio",
        'sum(rate(apache_accesses_total{code=~"5.."}[2m])) / clamp_min(sum(rate(apache_accesses_total[2m])), 0.001)',
    ),

    MetricQuery("wordpress_apache_cpuload", "avg(apache_cpuload)"),
    MetricQuery("wordpress_apache_workers_busy", 'sum(apache_workers{state="busy"})'),
    MetricQuery("wordpress_apache_workers_idle", 'sum(apache_workers{state="idle"})'),
    MetricQuery("wordpress_apache_workers_reply", 'sum(apache_scoreboard{state="reply"})'),

    MetricQuery(
        "wordpress_apache_workers_utilization",
        'sum(apache_workers{state="busy"}) / clamp_min(sum(apache_workers),1)'
    ),

    MetricQuery("wordpress_process_cpu_rate", "sum(rate(process_cpu_seconds_total[5m]))"),
    MetricQuery("wordpress_process_resident_memory_bytes", "avg(process_resident_memory_bytes)"),
    MetricQuery("wordpress_process_open_fds", "avg(process_open_fds)"),

    MetricQuery(
        "wordpress_container_cpu_rate",
        "sum(rate(container_cpu_usage_seconds_total{namespace='wordpress',container!=''}[2m]))"
    ),
    MetricQuery(
        "wordpress_container_memory_working_set_bytes",
        "sum(container_memory_working_set_bytes{namespace='wordpress',container!=''})"
    ),

    # ======================
    # MARIADB
    # ======================
    MetricQuery("mariadb_uptime_seconds", "max(mysql_global_status_uptime)"),
    MetricQuery("mariadb_threads_connected", "max(mysql_global_status_threads_connected)"),
    MetricQuery("mariadb_threads_running", "max(mysql_global_status_threads_running)"),

    # 🔥 NOVA: uso de conexão
    MetricQuery(
        "mariadb_connection_usage_ratio",
        'max(mysql_global_status_threads_connected) / max(mysql_global_variables_max_connections)'
    ),

    MetricQuery("mariadb_questions_rate", "sum(rate(mysql_global_status_questions[2m]))"),
    MetricQuery("mariadb_slow_queries_rate", "sum(rate(mysql_global_status_slow_queries[5m]))"),
    MetricQuery("mariadb_aborted_connects_rate", "sum(rate(mysql_global_status_aborted_connects[5m]))"),
    MetricQuery("mariadb_innodb_row_lock_time_rate", "sum(rate(mysql_global_status_innodb_row_lock_time[5m]))"),
    MetricQuery("mariadb_bytes_received_rate", "sum(rate(mysql_global_status_bytes_received[5m]))"),
    MetricQuery("mariadb_bytes_sent_rate", "sum(rate(mysql_global_status_bytes_sent[5m]))"),

    # 🔥 NOVA: buffer pool hit ratio
    MetricQuery(
        "mariadb_innodb_buffer_pool_hit_ratio",
        '(1 - (rate(mysql_global_status_innodb_buffer_pool_reads[5m]) / clamp_min(rate(mysql_global_status_innodb_buffer_pool_read_requests[5m]),1)))'
    ),

    # ======================
    # KUBERNETES
    # ======================
    MetricQuery(
        "k8s_wordpress_container_restarts_rate",
        'sum(rate(kube_pod_container_status_restarts_total{namespace="wordpress"}[5m]))',
    ),
    MetricQuery(
        "k8s_wordpress_unready_containers",
        'sum(kube_pod_container_status_ready{namespace="wordpress"} == 0)',
    ),
    MetricQuery(
        "k8s_wordpress_non_running_pods",
        'sum(kube_pod_status_phase{namespace="wordpress",phase=~"Pending|Failed|Unknown"})',
    ),

    # 🔥 NOVOS estados
    MetricQuery(
        "k8s_pods_waiting",
        'sum(kube_pod_container_status_waiting{namespace="wordpress"})',
    ),
    MetricQuery(
        "k8s_oom_kills",
        'sum(increase(container_oom_events_total{namespace="wordpress"}[5m]))'
    ),

    MetricQuery(
        "k8s_wordpress_cpu_throttled_seconds_rate",
        'sum(rate(container_cpu_cfs_throttled_seconds_total{namespace="wordpress",container!=""}[5m]))',
    ),

    # 🔥 NOVA: ratio throttling
    MetricQuery(
        "k8s_cpu_throttling_ratio",
        'sum(rate(container_cpu_cfs_throttled_periods_total{namespace="wordpress",container!=""}[5m])) / clamp_min(sum(rate(container_cpu_cfs_periods_total{namespace="wordpress",container!=""}[5m])), 1)',
    ),

    MetricQuery(
        "k8s_wordpress_container_cpu_usage_cores",
        'sum(rate(container_cpu_usage_seconds_total{namespace="wordpress",container!=""}[5m]))',
    ),
    MetricQuery(
        "k8s_wordpress_container_memory_working_set_bytes",
        'sum(container_memory_working_set_bytes{namespace="wordpress",container!=""})',
    ),

    # deployment health
    MetricQuery(
        "wordpress_deployment_available_ratio",
        'sum(kube_deployment_status_replicas_available{namespace="wordpress"}) / clamp_min(sum(kube_deployment_spec_replicas{namespace="wordpress"}), 1)'
    ),

    # erros de rede
    MetricQuery(
        "wordpress_network_receive_errors_rate",
        'sum(rate(container_network_receive_errors_total{namespace="wordpress"}[2m]))'
    ),
    MetricQuery(
        "wordpress_network_transmit_errors_rate",
        'sum(rate(container_network_transmit_errors_total{namespace="wordpress"}[2m]))'
    ),
]


# ======================
# HELPERS (do segundo código)
# ======================

def parse_step_to_seconds(step: str) -> int:
    if step.endswith("s"):
        return int(step[:-1])
    elif step.endswith("m"):
        return int(step[:-1]) * 60
    else:
        raise ValueError(f"Unsupported step format: {step}")


def normalize_ts(ts: float, step_seconds: int) -> float:
    return round(ts / step_seconds) * step_seconds


# ======================
# CORE (base + melhorias)
# ======================

def normalize_query_range_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.path.endswith("/api/v1/query_range"):
        return value
    return value.rstrip("/") + "/api/v1/query_range"


def parse_time_argument(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()


def utc_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def fetch_query_range(url: str, query: str, start: float, end: float, step: str, timeout: int):
    params = urlencode(
        {"query": query, "start": f"{start:.3f}", "end": f"{end:.3f}", "step": step}
    )

    request = Request(f"{url}?{params}", headers={"Accept": "application/json"})

    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} for query: {query}") from exc
    except URLError as exc:
        raise RuntimeError(f"Connection error: {exc.reason}") from exc

    if payload.get("status") != "success":
        raise RuntimeError(f"Prometheus error: {payload.get('error')}")

    result = payload.get("data", {}).get("result", [])
    return result[0] if result else {"values": []}


def collect_series(url, metrics, start, end, step, timeout):
    step_seconds = parse_step_to_seconds(step)

    rows = defaultdict(dict)
    column_names = ["timestamp"]

    for metric in metrics:
        column_names.append(metric.alias)

        series = fetch_query_range(url, metric.query, start, end, step, timeout)

        for timestamp, value in series.get("values", []):
            norm_ts = normalize_ts(float(timestamp), step_seconds)
            ts_key = utc_timestamp(norm_ts)

            try:
                val = float(value)
            except:
                val = 0.0

            rows[ts_key][metric.alias] = val

    # 🔥 fill missing
    for ts in rows:
        for col in column_names:
            if col != "timestamp":
                rows[ts].setdefault(col, 0.0)

    return column_names, rows


def write_csv(columns, rows, output_handle):
    writer = csv.DictWriter(output_handle, fieldnames=columns)
    writer.writeheader()

    for timestamp in sorted(rows.keys()):
        record = {col: rows[timestamp].get(col, 0.0) for col in columns}
        record["timestamp"] = timestamp
        writer.writerow(record)


def build_argument_parser():
    parser = argparse.ArgumentParser(description="Scrape Prometheus metrics and export CSV.")
    parser.add_argument("--url", default=DEFAULT_QUERY_URL)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--minutes", type=int, default=300)
    parser.add_argument("--step", default="10s")
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--output", default="metrics.csv")
    return parser


def main():
    parser = build_argument_parser()
    args = parser.parse_args()

    end = parse_time_argument(args.end) if args.end else datetime.now(timezone.utc).timestamp()
    start = parse_time_argument(args.start) if args.start else end - timedelta(minutes=args.minutes).total_seconds()

    if start > end:
        parser.error("start must be <= end")

    query_url = normalize_query_range_url(args.url)

    columns, rows = collect_series(
        query_url,
        DEFAULT_METRICS,
        start,
        end,
        args.step,
        args.timeout,
    )

    if args.output == "-":
        write_csv(columns, rows, sys.stdout)
    else:
        with open(args.output, "w", newline="", encoding="utf-8") as handle:
            write_csv(columns, rows, handle)


if __name__ == "__main__":
    raise SystemExit(main())