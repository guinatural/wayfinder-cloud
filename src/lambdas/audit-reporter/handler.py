"""
audit_reporter  Lambda Function
Wayfinder Cloud | VitaCore Health

Responsabilidade:
  Agendada semanalmente (segunda-feira 08:00 UTC).
  Executa queries Athena para consolidar métricas de compliance,
  gera relatório JSON estruturado e salva no S3.
  Publica resumo executivo no SNS INFO.

Variáveis de ambiente:
  AUDIT_BUCKET_NAME  Nome do bucket S3 para relatórios
  ATHENA_WORKGROUP   Workgroup Athena (default: wayfinder-audit)
  ATHENA_DATABASE    Database Glue/Athena (default: wayfinder_audit)
  INFO_TOPIC_ARN     ARN SNS para publicar sumário
  ENVIRONMENT        dev | staging | prod
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any

import boto3
from botocore.exceptions import ClientError

#  Configuração 

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

AUDIT_BUCKET_NAME = os.environ["AUDIT_BUCKET_NAME"]
ATHENA_WORKGROUP  = os.environ.get("ATHENA_WORKGROUP", "wayfinder-audit")
ATHENA_DATABASE   = os.environ.get("ATHENA_DATABASE", "wayfinder_audit")
INFO_TOPIC_ARN    = os.environ["INFO_TOPIC_ARN"]
ENVIRONMENT       = os.environ.get("ENVIRONMENT", "dev")

_athena = boto3.client("athena")
_s3     = boto3.client("s3")
_sns    = boto3.client("sns")

ATHENA_POLL_INTERVAL_SEC = 2
ATHENA_MAX_WAIT_SEC      = 240  # 4 minutos por query

#  Handler principal 

def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Entry point da Lambda audit-reporter.

    Fluxo:
    1. Executar queries Athena (4 queries principais)
    2. Consolidar resultados em relatório estruturado
    3. Salvar relatório em S3 (compliance-reports/{year}/{month}/{date}-weekly-report.json)
    4. Publicar sumário no SNS INFO

    Returns:
        dict com caminho do relatório e métricas-chave
    """
    now = datetime.now(timezone.utc)
    logger.info("Iniciando geração de relatório semanal  %s", now.isoformat())

    # Período de análise: últimos 7 dias
    end_date   = now
    start_date = now - timedelta(days=7)

    report = {
        "report_metadata": {
            "generated_at":   now.isoformat(),
            "period_start":   start_date.isoformat(),
            "period_end":     end_date.isoformat(),
            "environment":    ENVIRONMENT,
            "report_version": "1.0",
        },
        "executive_summary": {},
        "violations_by_severity": {},
        "top_noncompliant_resources": [],
        "mttr_average_hours":   None,
        "compliance_percentage": None,
        "errors": [],
    }

    # Query 1: Total de violações por severidade
    try:
        violations = _query_violations_by_severity(start_date, end_date)
        report["violations_by_severity"] = violations
    except Exception as exc:
        logger.error("Falha na query de violações por severidade: %s", exc)
        report["errors"].append(f"violations_by_severity: {exc}")

    # Query 2: Top 5 recursos mais não-conformes
    try:
        top_resources = _query_top_noncompliant_resources(start_date, end_date)
        report["top_noncompliant_resources"] = top_resources
    except Exception as exc:
        logger.error("Falha na query de top recursos: %s", exc)
        report["errors"].append(f"top_noncompliant_resources: {exc}")

    # Query 3: MTTR médio (Mean Time to Remediate)
    try:
        mttr = _query_mttr(start_date, end_date)
        report["mttr_average_hours"] = mttr
    except Exception as exc:
        logger.error("Falha na query de MTTR: %s", exc)
        report["errors"].append(f"mttr: {exc}")

    # Query 4: Percentual de conformidade geral
    try:
        compliance_pct = _query_compliance_percentage(start_date, end_date)
        report["compliance_percentage"] = compliance_pct
    except Exception as exc:
        logger.error("Falha na query de compliance percentage: %s", exc)
        report["errors"].append(f"compliance_percentage: {exc}")

    # Montar resumo executivo
    total_violations = sum(report["violations_by_severity"].values()) if report["violations_by_severity"] else 0
    critical_count   = report["violations_by_severity"].get("CRITICAL", 0)
    report["executive_summary"] = {
        "total_violations_7d":   total_violations,
        "critical_violations":   critical_count,
        "compliance_percentage": report["compliance_percentage"],
        "mttr_hours":            report["mttr_average_hours"],
        "top_resource":          report["top_noncompliant_resources"][0] if report["top_noncompliant_resources"] else None,
        "health_status":         _determine_health_status(critical_count, report["compliance_percentage"]),
    }

    # Salvar relatório no S3
    s3_key = _save_report_to_s3(report, now)
    logger.info("Relatório salvo em s3://%s/%s", AUDIT_BUCKET_NAME, s3_key)

    # Publicar sumário no SNS
    _publish_summary_sns(report["executive_summary"], s3_key)

    result = {
        "status":   "completed",
        "s3_key":   s3_key,
        "summary":  report["executive_summary"],
        "errors":   report["errors"],
    }

    logger.info("Relatório semanal concluído: %s", json.dumps(result, default=str))
    return result


#  Queries Athena 

def _run_athena_query(sql: str, query_name: str) -> list[dict[str, Any]]:
    """
    Executa query Athena e aguarda resultado com polling.

    Args:
        sql: Query SQL a executar
        query_name: Nome descritivo para logs

    Returns:
        Lista de rows como dicionários

    Raises:
        RuntimeError: se a query falhar ou exceder timeout
    """
    logger.info("Executando Athena query '%s'", query_name)

    response = _athena.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": ATHENA_DATABASE},
        WorkGroup=ATHENA_WORKGROUP,
    )
    execution_id = response["QueryExecutionId"]

    # Polling até conclusão
    elapsed = 0
    while elapsed < ATHENA_MAX_WAIT_SEC:
        status_resp = _athena.get_query_execution(QueryExecutionId=execution_id)
        state = status_resp["QueryExecution"]["Status"]["State"]

        if state == "SUCCEEDED":
            break
        elif state in ("FAILED", "CANCELLED"):
            reason = status_resp["QueryExecution"]["Status"].get("StateChangeReason", "")
            raise RuntimeError(f"Athena query '{query_name}' {state}: {reason}")

        time.sleep(ATHENA_POLL_INTERVAL_SEC)
        elapsed += ATHENA_POLL_INTERVAL_SEC
    else:
        raise RuntimeError(f"Athena query '{query_name}' excedeu timeout de {ATHENA_MAX_WAIT_SEC}s")

    # Obter resultados
    results = _athena.get_query_results(QueryExecutionId=execution_id)
    return _parse_athena_results(results)


def _parse_athena_results(results: dict[str, Any]) -> list[dict[str, Any]]:
    """Converte ResultSet do Athena em lista de dicionários."""
    rows = results["ResultSet"]["Rows"]
    if not rows:
        return []

    # Primeira linha é o header
    headers = [col["VarCharValue"] for col in rows[0]["Data"]]
    parsed = []

    for row in rows[1:]:
        values = [cell.get("VarCharValue", "") for cell in row["Data"]]
        parsed.append(dict(zip(headers, values)))

    return parsed


def _query_violations_by_severity(
    start: datetime, end: datetime
) -> dict[str, int]:
    """Total de violações por severidade nos últimos 7 dias."""
    sql = f"""
    SELECT
      json_extract_scalar(message, '$.severity') AS severity,
      COUNT(*) AS total
    FROM cloudtrail_logs
    WHERE
      eventsource = 'config.amazonaws.com'
      AND eventname = 'PutEvaluations'
      AND from_iso8601_timestamp(eventtime) BETWEEN
          TIMESTAMP '{start.strftime("%Y-%m-%d %H:%M:%S")}'
          AND TIMESTAMP '{end.strftime("%Y-%m-%d %H:%M:%S")}'
    GROUP BY 1
    ORDER BY 2 DESC
    """
    rows = _run_athena_query(sql, "violations_by_severity")
    return {row["severity"]: int(row["total"]) for row in rows if row.get("severity")}


def _query_top_noncompliant_resources(
    start: datetime, end: datetime
) -> list[dict[str, Any]]:
    """Top 5 recursos com mais violações no período."""
    sql = f"""
    SELECT
      json_extract_scalar(message, '$.resource_id')   AS resource_id,
      json_extract_scalar(message, '$.resource_type') AS resource_type,
      COUNT(*) AS violation_count
    FROM cloudtrail_logs
    WHERE
      eventsource = 'config.amazonaws.com'
      AND from_iso8601_timestamp(eventtime) BETWEEN
          TIMESTAMP '{start.strftime("%Y-%m-%d %H:%M:%S")}'
          AND TIMESTAMP '{end.strftime("%Y-%m-%d %H:%M:%S")}'
    GROUP BY 1, 2
    ORDER BY 3 DESC
    LIMIT 5
    """
    rows = _run_athena_query(sql, "top_noncompliant_resources")
    return [
        {
            "resource_id":      r.get("resource_id"),
            "resource_type":    r.get("resource_type"),
            "violation_count":  int(r.get("violation_count", 0)),
        }
        for r in rows
    ]


def _query_mttr(start: datetime, end: datetime) -> float | None:
    """MTTR médio em horas (tempo entre detecção e remediação bem-sucedida)."""
    sql = f"""
    SELECT
      AVG(
        date_diff('minute',
          from_iso8601_timestamp(json_extract_scalar(message, '$.triggered_at')),
          from_iso8601_timestamp(eventtime)
        )
      ) / 60.0 AS avg_mttr_hours
    FROM cloudtrail_logs
    WHERE
      json_extract_scalar(message, '$.event_type') = 'REMEDIATION'
      AND json_extract_scalar(message, '$.status')  = 'success'
      AND from_iso8601_timestamp(eventtime) BETWEEN
          TIMESTAMP '{start.strftime("%Y-%m-%d %H:%M:%S")}'
          AND TIMESTAMP '{end.strftime("%Y-%m-%d %H:%M:%S")}'
    """
    rows = _run_athena_query(sql, "mttr")
    if rows and rows[0].get("avg_mttr_hours"):
        try:
            return round(float(rows[0]["avg_mttr_hours"]), 2)
        except (ValueError, TypeError):
            return None
    return None


def _query_compliance_percentage(start: datetime, end: datetime) -> float | None:
    """Percentual de avaliações COMPLIANT no período."""
    sql = f"""
    SELECT
      ROUND(
        100.0 * SUM(CASE WHEN compliance_type = 'COMPLIANT' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0),
        2
      ) AS compliance_pct
    FROM (
      SELECT
        json_extract_scalar(message, '$.compliance_type') AS compliance_type
      FROM cloudtrail_logs
      WHERE
        eventsource = 'config.amazonaws.com'
        AND eventname = 'PutEvaluations'
        AND from_iso8601_timestamp(eventtime) BETWEEN
            TIMESTAMP '{start.strftime("%Y-%m-%d %H:%M:%S")}'
            AND TIMESTAMP '{end.strftime("%Y-%m-%d %H:%M:%S")}'
    )
    """
    rows = _run_athena_query(sql, "compliance_percentage")
    if rows and rows[0].get("compliance_pct"):
        try:
            return round(float(rows[0]["compliance_pct"]), 2)
        except (ValueError, TypeError):
            return None
    return None


#  Relatório S3 

def _save_report_to_s3(report: dict[str, Any], now: datetime) -> str:
    """
    Salva relatório JSON no S3 com path estruturado por data.

    Path: compliance-reports/{year}/{month}/{date}-weekly-report.json

    Returns:
        str: chave S3 do arquivo salvo
    """
    s3_key = (
        f"compliance-reports/{now.year}/{now.strftime('%m')}/"
        f"{now.strftime('%Y-%m-%d')}-weekly-report.json"
    )

    body = json.dumps(report, indent=2, ensure_ascii=False, default=str).encode("utf-8")

    _s3.put_object(
        Bucket=AUDIT_BUCKET_NAME,
        Key=s3_key,
        Body=body,
        ContentType="application/json",
        ServerSideEncryption="aws:kms",
        Metadata={
            "environment":    ENVIRONMENT,
            "report-version": "1.0",
            "generated-at":   now.isoformat(),
        },
    )

    return s3_key


def _publish_summary_sns(summary: dict[str, Any], s3_key: str) -> None:
    """Publica resumo executivo no SNS INFO."""
    compliance_pct = summary.get("compliance_percentage")
    pct_str = f"{compliance_pct}%" if compliance_pct is not None else "N/A"

    message = (
        f" Wayfinder Cloud  Relatório Semanal de Compliance [{ENVIRONMENT.upper()}]\n\n"
        f"Período: últimos 7 dias\n"
        f"Status de saúde: {summary.get('health_status', 'DESCONHECIDO')}\n"
        f"Conformidade geral: {pct_str}\n"
        f"Total de violações: {summary.get('total_violations_7d', 0)}\n"
        f"Violações CRITICAL: {summary.get('critical_violations', 0)}\n"
        f"MTTR médio: {summary.get('mttr_hours', 'N/A')} horas\n\n"
        f"Relatório completo salvo em:\n"
        f"s3://{AUDIT_BUCKET_NAME}/{s3_key}\n\n"
        f"Detalhes: {json.dumps(summary, indent=2, ensure_ascii=False, default=str)}"
    )

    try:
        _sns.publish(
            TopicArn=INFO_TOPIC_ARN,
            Subject=f"[Wayfinder Cloud] Relatório Semanal de Compliance  {ENVIRONMENT}",
            Message=message,
        )
        logger.info("Sumário publicado no SNS INFO")
    except ClientError as exc:
        logger.error("Falha ao publicar sumário no SNS: %s", exc)


#  Helpers 

def _determine_health_status(critical_count: int, compliance_pct: float | None) -> str:
    """
    Determina status de saúde geral do ambiente.

    Returns:
        str: HEALTHY | DEGRADED | CRITICAL
    """
    if critical_count > 0:
        return "CRITICAL"
    if compliance_pct is not None and compliance_pct < 80.0:
        return "DEGRADED"
    return "HEALTHY"
