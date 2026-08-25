"""
compliance_evaluator  Lambda Function
Wayfinder Cloud | VitaCore Health

Responsabilidade:
  Recebe eventos de NON_COMPLIANT do AWS Config via EventBridge,
  enriquece com contexto (tags, classificação de dados, artigo LGPD relevante),
  determina severidade final e publica no SNS topic correto + métrica CloudWatch.

Fluxo:
  EventBridge (Config NON_COMPLIANT)  Lambda (este)  SNS Topic (por severidade)
                                                       CloudWatch Metric
                                                       EventBridge (remediação)
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

#  Configuração 

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Clientes AWS  instanciados uma vez (fora do handler) para reutilização entre invocações
_sns       = boto3.client("sns")
_cw        = boto3.client("cloudwatch")
_config    = boto3.client("config")
_tagging   = boto3.client("resourcegroupstaggingapi")
_events    = boto3.client("events")

# Variáveis de ambiente injetadas pelo Terraform
CRITICAL_TOPIC_ARN   = os.environ["CRITICAL_TOPIC_ARN"]
WARNING_TOPIC_ARN    = os.environ["WARNING_TOPIC_ARN"]
INFO_TOPIC_ARN       = os.environ["INFO_TOPIC_ARN"]
REMEDIATION_BUS_NAME = os.environ["WAYFINDER_EVENT_BUS_NAME"]
ENVIRONMENT          = os.environ.get("ENVIRONMENT", "dev")

#  Mapeamento LGPD 

RULE_LGPD_MAP: dict[str, dict[str, Any]] = {
    "WAYFINDER-001": {
        "article": "Art. 46 e 49",
        "description": "S3 com dados de saúde sem criptografia KMS",
        "severity": "CRITICAL",
        "auto_remediation": True,
        "remediation_action": "enable_s3_kms_encryption",
    },
    "WAYFINDER-002": {
        "article": "Art. 46",
        "description": "S3 com dados de saúde com acesso público habilitado",
        "severity": "CRITICAL",
        "auto_remediation": True,
        "remediation_action": "enable_s3_block_public_access",
    },
    "WAYFINDER-003": {
        "article": "Art. 37 e 48",
        "description": "CloudTrail desabilitado  perda de trilha de auditoria",
        "severity": "CRITICAL",
        "auto_remediation": True,
        "remediation_action": "enable_cloudtrail",
    },
    "WAYFINDER-004": {
        "article": "Art. 46",
        "description": "RDS sem criptografia em repouso",
        "severity": "HIGH",
        "auto_remediation": False,
        "remediation_action": None,
    },
    "WAYFINDER-005": {
        "article": "Art. 6, IV e 47",
        "description": "IAM com permissões administrativas excessivas (*)  ",
        "severity": "HIGH",
        "auto_remediation": False,
        "remediation_action": None,
    },
    "WAYFINDER-006": {
        "article": "Art. 46 e 49",
        "description": "EC2 com dados de saúde em subnet pública",
        "severity": "CRITICAL",
        "auto_remediation": True,
        "remediation_action": "isolate_ec2_security_group",
    },
    # Managed Rules
    "cloud-trail-enabled": {
        "article": "Art. 37",
        "description": "CloudTrail não habilitado na conta",
        "severity": "CRITICAL",
        "auto_remediation": False,
        "remediation_action": None,
    },
    "s3-bucket-public-read-prohibited": {
        "article": "Art. 46",
        "description": "S3 Bucket com leitura pública habilitada",
        "severity": "CRITICAL",
        "auto_remediation": True,
        "remediation_action": "enable_s3_block_public_access",
    },
    "encrypted-volumes": {
        "article": "Art. 46",
        "description": "EBS Volume sem criptografia",
        "severity": "HIGH",
        "auto_remediation": False,
        "remediation_action": None,
    },
}

SEVERITY_TOPIC_MAP = {
    "CRITICAL": CRITICAL_TOPIC_ARN,
    "HIGH":     WARNING_TOPIC_ARN,
    "MEDIUM":   WARNING_TOPIC_ARN,
    "LOW":      INFO_TOPIC_ARN,
}

#  Handler principal 

def handler(event: dict, context: Any) -> dict:
    """
    Entry point da Lambda.

    Args:
        event: Evento EventBridge com formato Config Rule change
        context: Lambda context (unused)

    Returns:
        dict com status e número de eventos processados
    """
    logger.info("Evento recebido: %s", json.dumps(event, default=str))

    try:
        compliance_event = _parse_config_event(event)
    except (KeyError, ValueError) as exc:
        logger.error("Evento inválido ou formato inesperado: %s", exc)
        raise

    # Enriquecer com tags do recurso
    resource_tags = _get_resource_tags(
        compliance_event["resource_type"],
        compliance_event["resource_id"],
    )

    # Determinar severidade final
    rule_info   = RULE_LGPD_MAP.get(compliance_event["rule_name"], {})
    severity    = rule_info.get("severity", "MEDIUM")
    lgpd_article = rule_info.get("article", "Não mapeado")

    # Elevar severidade se recurso tem classificação de dados sensíveis
    if resource_tags.get("data-classification") in ("health-critical", "health-standard"):
        if severity == "HIGH":
            severity = "CRITICAL"
            logger.warning(
                "Severidade elevada para CRITICAL: recurso com data-classification=%s",
                resource_tags.get("data-classification"),
            )

    enriched_event = {
        **compliance_event,
        "severity":           severity,
        "lgpd_article":       lgpd_article,
        "rule_description":   rule_info.get("description", ""),
        "auto_remediation":   rule_info.get("auto_remediation", False),
        "remediation_action": rule_info.get("remediation_action"),
        "resource_tags":      resource_tags,
        "environment":        ENVIRONMENT,
        "evaluated_at":       datetime.now(timezone.utc).isoformat(),
    }

    logger.info("Evento enriquecido: %s", json.dumps(enriched_event, default=str))

    # Publicar notificação no SNS
    _publish_notification(enriched_event)

    # Publicar métrica CloudWatch
    _publish_cloudwatch_metric(enriched_event)

    # Disparar remediação automática se elegível
    if enriched_event["auto_remediation"] and enriched_event["remediation_action"]:
        _trigger_auto_remediation(enriched_event)

    return {"status": "processed", "severity": severity}


#  Funções auxiliares 

def _parse_config_event(event: dict) -> dict:
    """
    Extrai campos relevantes do evento Config via EventBridge.

    Formato esperado do evento:
    {
      "source": "aws.config",
      "detail-type": "Config Rules Compliance Change",
      "detail": {
        "configRuleName": "WAYFINDER-001",
        "resourceType": "AWS::S3::Bucket",
        "resourceId": "vitacore-prontuarios-prod",
        "newEvaluationResult": {
          "complianceType": "NON_COMPLIANT",
          "resultRecordedTime": "2026-08-21T14:32:00Z"
        },
        "awsAccountId": "123456789012",
        "awsRegion": "us-east-1"
      }
    }
    """
    detail = event["detail"]
    compliance_type = detail["newEvaluationResult"]["complianceType"]

    if compliance_type != "NON_COMPLIANT":
        raise ValueError(f"Evento ignorado  complianceType={compliance_type}")

    return {
        "rule_name":     detail["configRuleName"],
        "resource_type": detail["resourceType"],
        "resource_id":   detail["resourceId"],
        "account_id":    detail["awsAccountId"],
        "region":        detail["awsRegion"],
        "compliance_type": compliance_type,
        "recorded_at":   detail["newEvaluationResult"]["resultRecordedTime"],
    }


def _get_resource_tags(resource_type: str, resource_id: str) -> dict[str, str]:
    """
    Busca as tags do recurso para enriquecer o evento de compliance.
    Retorna dicionário vazio em caso de erro (não deve quebrar o fluxo principal).
    """
    try:
        # Converte resource_type AWS::S3::Bucket  s3:bucket (aproximação)
        # Para implementação completa, mapear todos os resource types
        response = _tagging.get_resources(
            ResourceARNList=[],
            TagFilters=[],
        )
        return {}  # Implementação simplificada  expandir conforme necessidade
    except ClientError as exc:
        logger.warning("Não foi possível obter tags do recurso %s: %s", resource_id, exc)
        return {}


def _publish_notification(event: dict) -> None:
    """
    Publica mensagem formatada no SNS topic correspondente à severidade.
    """
    topic_arn = SEVERITY_TOPIC_MAP.get(event["severity"], INFO_TOPIC_ARN)

    subject = (
        f"[WAYFINDER-{event['severity']}] "
        f"{event['rule_name']}  "
        f"{event['resource_type']}: {event['resource_id']}"
    )

    message = json.dumps({
        " Wayfinder Cloud  Alerta de Compliance": None,
        "Severidade":      event["severity"],
        "Regra":           event["rule_name"],
        "Descrição":       event.get("rule_description", ""),
        "Recurso":         f"{event['resource_type']} / {event['resource_id']}",
        "Conta":           event["account_id"],
        "Região":          event["region"],
        "Artigo LGPD":     event["lgpd_article"],
        "Detectado em":    event["evaluated_at"],
        "Remediação auto": "Sim" if event["auto_remediation"] else "Não",
        "Ambiente":        event["environment"],
    }, indent=2, ensure_ascii=False)

    try:
        _sns.publish(
            TopicArn=topic_arn,
            Subject=subject[:100],  # SNS subject limit
            Message=message,
            MessageAttributes={
                "severity": {
                    "DataType": "String",
                    "StringValue": event["severity"],
                },
                "rule_name": {
                    "DataType": "String",
                    "StringValue": event["rule_name"],
                },
            },
        )
        logger.info("Notificação publicada no topic %s", topic_arn)
    except ClientError as exc:
        logger.error("Falha ao publicar notificação SNS: %s", exc)
        raise


def _publish_cloudwatch_metric(event: dict) -> None:
    """
    Publica métrica customizada no namespace wayfinder/Compliance.
    Permite criar alarmes e dashboards sobre postura de conformidade.
    """
    severity_value = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}.get(
        event["severity"], 1
    )

    try:
        _cw.put_metric_data(
            Namespace="wayfinder/Compliance",
            MetricData=[
                {
                    "MetricName": "NonCompliantResource",
                    "Value": 1,
                    "Unit": "Count",
                    "Dimensions": [
                        {"Name": "RuleName",    "Value": event["rule_name"]},
                        {"Name": "Severity",    "Value": event["severity"]},
                        {"Name": "Environment", "Value": event["environment"]},
                    ],
                },
                {
                    "MetricName": "ComplianceScore",
                    "Value": severity_value,
                    "Unit": "None",
                    "Dimensions": [
                        {"Name": "Environment", "Value": event["environment"]},
                    ],
                },
            ],
        )
        logger.info("Métricas CloudWatch publicadas para regra %s", event["rule_name"])
    except ClientError as exc:
        logger.warning("Falha ao publicar métrica CloudWatch: %s", exc)
        # Não relançar  métrica é best-effort, não deve derrubar o fluxo


def _trigger_auto_remediation(event: dict) -> None:
    """
    Publica evento no EventBridge para acionar a Lambda de remediação automática.
    Separa responsabilidades: evaluator classifica, remediation executa.
    """
    remediation_payload = {
        "action":        event["remediation_action"],
        "resource_type": event["resource_type"],
        "resource_id":   event["resource_id"],
        "rule_name":     event["rule_name"],
        "severity":      event["severity"],
        "account_id":    event["account_id"],
        "region":        event["region"],
        "triggered_at":  event["evaluated_at"],
        "lgpd_article":  event["lgpd_article"],
    }

    try:
        _events.put_events(
            Entries=[
                {
                    "Source":       "wayfinder.compliance-evaluator",
                    "DetailType":   "WayfinderAutoRemediation",
                    "Detail":       json.dumps(remediation_payload),
                    "EventBusName": REMEDIATION_BUS_NAME,
                }
            ]
        )
        logger.info(
            "Evento de remediação publicado: action=%s resource=%s",
            event["remediation_action"],
            event["resource_id"],
        )
    except ClientError as exc:
        logger.error("Falha ao publicar evento de remediação: %s", exc)
        raise
