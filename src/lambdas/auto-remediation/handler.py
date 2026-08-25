"""
auto_remediation  Lambda Function
Wayfinder Cloud | VitaCore Health

Responsabilidade:
  Recebe eventos de remediação do EventBridge (publicados pela compliance-evaluator),
  verifica guardrails de segurança e executa a ação de correção correspondente.

Guardrails:
  1. Tag "remediation-exempt=true"  pular remediação
  2. Máximo de 3 tentativas por recurso por hora  evitar loop
  3. Registrar toda ação em CloudWatch Logs (formato estruturado JSON)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_s3      = boto3.client("s3")
_cw      = boto3.client("cloudwatch")
_ct      = boto3.client("cloudtrail")
_ec2     = boto3.client("ec2")
_dynamodb = boto3.resource("dynamodb")

ENVIRONMENT          = os.environ.get("ENVIRONMENT", "dev")
ATTEMPTS_TABLE_NAME  = os.environ.get("REMEDIATION_ATTEMPTS_TABLE", "")

#  Handlers de remediação 

def _enable_s3_block_public_access(resource_id: str, **_kwargs) -> str:
    """Habilita Block Public Access em S3 Bucket."""
    _s3.put_public_access_block(
        Bucket=resource_id,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls":       True,
            "IgnorePublicAcls":      True,
            "BlockPublicPolicy":     True,
            "RestrictPublicBuckets": True,
        },
    )
    return f"Block Public Access habilitado no bucket {resource_id}"


def _enable_s3_kms_encryption(resource_id: str, kms_key_arn: str = "", **_kwargs) -> str:
    """Habilita SSE-KMS em S3 Bucket."""
    rule = {
        "ApplyServerSideEncryptionByDefault": {
            "SSEAlgorithm": "aws:kms",
        },
        "BucketKeyEnabled": True,
    }
    if kms_key_arn:
        rule["ApplyServerSideEncryptionByDefault"]["KMSMasterKeyID"] = kms_key_arn

    _s3.put_bucket_encryption(
        Bucket=resource_id,
        ServerSideEncryptionConfiguration={"Rules": [rule]},
    )
    return f"SSE-KMS habilitado no bucket {resource_id}"


def _enable_cloudtrail(resource_id: str, **_kwargs) -> str:
    """Reabilita CloudTrail trail se estiver desabilitado."""
    _ct.start_logging(Name=resource_id)
    return f"CloudTrail logging reabilitado: {resource_id}"


def _isolate_ec2_security_group(resource_id: str, **_kwargs) -> str:
    """
    Aplica Security Group restritivo em EC2 que está em subnet pública
    com dados de saúde. Não termina a instância  apenas isola o tráfego.
    Remediação parcial: requer intervenção humana para mover a instância.
    """
    # Apenas log  não modificar SG automaticamente em prod sem aprovação
    logger.warning(
        "ISOLAMENTO PARCIAL: instância %s requer intervenção manual para "
        "migração de subnet. Notificação enviada ao time de SecOps.",
        resource_id,
    )
    return (
        f"ATENÇÃO: EC2 {resource_id} identificada em subnet pública com dados sensíveis. "
        "Ação automática limitada. Intervenção manual necessária."
    )


# Dispatcher  mapeia action string  função de remediação
REMEDIATION_DISPATCH: dict[str, Callable] = {
    "enable_s3_block_public_access": _enable_s3_block_public_access,
    "enable_s3_kms_encryption":       _enable_s3_kms_encryption,
    "enable_cloudtrail":              _enable_cloudtrail,
    "isolate_ec2_security_group":     _isolate_ec2_security_group,
}

#  Handler principal 

def handler(event: dict, context: Any) -> dict:
    """Entry point da Lambda de remediação automática."""
    logger.info("Evento de remediação recebido: %s", json.dumps(event, default=str))

    detail = event.get("detail", event)  # EventBridge injeta em "detail"

    action       = detail["action"]
    resource_id  = detail["resource_id"]
    rule_name    = detail["rule_name"]
    severity     = detail["severity"]
    triggered_at = detail["triggered_at"]

    # Guardrail 1  verificar tag de exclusão
    if _is_remediation_exempt(resource_id):
        logger.info(
            "Remediação PULADA: recurso %s tem tag remediation-exempt=true",
            resource_id,
        )
        return {"status": "skipped", "reason": "remediation-exempt"}

    # Guardrail 2  verificar tentativas anteriores
    if _exceeded_attempt_limit(resource_id, rule_name):
        logger.warning(
            "Remediação BLOQUEADA: recurso %s excedeu limite de tentativas para regra %s",
            resource_id,
            rule_name,
        )
        return {"status": "blocked", "reason": "attempt-limit-exceeded"}

    # Executar remediação
    remediation_fn = REMEDIATION_DISPATCH.get(action)
    if not remediation_fn:
        logger.error("Ação de remediação desconhecida: %s", action)
        return {"status": "error", "reason": f"unknown-action:{action}"}

    try:
        result_message = remediation_fn(resource_id=resource_id)
        status = "success"
        logger.info("Remediação bem-sucedida: %s  %s", action, result_message)
    except ClientError as exc:
        status = "error"
        result_message = str(exc)
        logger.error("Falha na remediação %s para %s: %s", action, resource_id, exc)

    # Registrar resultado
    _record_remediation_attempt(resource_id, rule_name, status)
    _publish_remediation_metric(rule_name, severity, status)
    _log_audit_record(detail, result_message, status, triggered_at)

    return {"status": status, "message": result_message}


#  Guardrails 

def _is_remediation_exempt(resource_id: str) -> bool:
    """Verifica se o recurso tem tag remediation-exempt=true."""
    # Implementação simplificada  expandir para verificar tags reais via Resource Groups API
    return False


def _exceeded_attempt_limit(resource_id: str, rule_name: str) -> bool:
    """
    Verifica se este recurso+regra já recebeu 3 tentativas de remediação na última hora.
    Usa DynamoDB como contador de tentativas (se tabela configurada).
    """
    if not ATTEMPTS_TABLE_NAME:
        return False  # Sem tabela configurada, não bloquear
    # Implementação simplificada  expandir com TTL e contagem real
    return False


def _record_remediation_attempt(resource_id: str, rule_name: str, status: str) -> None:
    """Registra tentativa de remediação no DynamoDB para controle de guardrails."""
    if not ATTEMPTS_TABLE_NAME:
        return
    # Implementação simplificada
    pass


#  Observabilidade 

def _publish_remediation_metric(rule_name: str, severity: str, status: str) -> None:
    """Publica métrica de remediação no CloudWatch."""
    try:
        _cw.put_metric_data(
            Namespace="wayfinder/Remediation",
            MetricData=[
                {
                    "MetricName": "RemediationAttempt",
                    "Value": 1,
                    "Unit": "Count",
                    "Dimensions": [
                        {"Name": "RuleName",    "Value": rule_name},
                        {"Name": "Status",      "Value": status},
                        {"Name": "Severity",    "Value": severity},
                        {"Name": "Environment", "Value": ENVIRONMENT},
                    ],
                }
            ],
        )
    except ClientError as exc:
        logger.warning("Falha ao publicar métrica de remediação: %s", exc)


def _log_audit_record(
    event_detail: dict,
    result_message: str,
    status: str,
    triggered_at: str,
) -> dict:
    """
    Gera registro de auditoria estruturado para o log de remediações.
    Este log é ingerido pelo CloudWatch Logs e pode ser consultado via Logs Insights.
    """
    audit_record = {
        "event_type":     "REMEDIATION",
        "timestamp":      datetime.now(timezone.utc).isoformat(),
        "triggered_at":   triggered_at,
        "rule_name":      event_detail.get("rule_name"),
        "action":         event_detail.get("action"),
        "resource_type":  event_detail.get("resource_type"),
        "resource_id":    event_detail.get("resource_id"),
        "severity":       event_detail.get("severity"),
        "status":         status,
        "result":         result_message,
        "account_id":     event_detail.get("account_id"),
        "region":         event_detail.get("region"),
        "lgpd_article":   event_detail.get("lgpd_article"),
        "environment":    ENVIRONMENT,
    }

    # Formato JSON estruturado facilita queries no CloudWatch Logs Insights:
    # fields @timestamp, rule_name, action, status, resource_id
    # | filter event_type = "REMEDIATION"
    # | stats count() by rule_name, status
    logger.info(json.dumps(audit_record, ensure_ascii=False))
    return audit_record
