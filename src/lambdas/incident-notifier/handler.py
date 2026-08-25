"""
incident_notifier  Lambda Function
Wayfinder Cloud | VitaCore Health

Responsabilidade:
  Recebe eventos de compliance (forwarded pelo SNS ou EventBridge),
  formata mensagens ricas para Slack (Block Kit) e email,
  e publica no canal correto com contexto LGPD.

Variáveis de ambiente:
  ENVIRONMENT             dev | staging | prod
  SLACK_WEBHOOK_URL       URL do Incoming Webhook (opcional, vazio desabilita)
  CLOUDWATCH_DASHBOARD_URL  URL do dashboard para links nas notificações
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

#  Configuração 

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ENVIRONMENT             = os.environ.get("ENVIRONMENT", "dev")
SLACK_WEBHOOK_URL       = os.environ.get("SLACK_WEBHOOK_URL", "")
CLOUDWATCH_DASHBOARD_URL = os.environ.get(
    "CLOUDWATCH_DASHBOARD_URL",
    "https://console.aws.amazon.com/cloudwatch/home#dashboards",
)

# Mapeamento de severidade  emoji e cor Slack
SEVERITY_CONFIG: dict[str, dict[str, str]] = {
    "CRITICAL": {"emoji": "", "color": "#FF0000", "label": "CRITICAL"},
    "HIGH":     {"emoji": "", "color": "#FF8C00", "label": "HIGH"},
    "MEDIUM":   {"emoji": "", "color": "#FFA500", "label": "MEDIUM"},
    "LOW":      {"emoji": "", "color": "#36A64F", "label": "LOW"},
    "INFO":     {"emoji": "", "color": "#0099CC", "label": "INFO"},
}

#  Handler principal 

def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Entry point da Lambda incident-notifier.

    Aceita eventos de:
    - SNS (Records[].Sns.Message com JSON de compliance)
    - EventBridge (detail com payload de compliance direto)

    Args:
        event: Evento Lambda (SNS ou EventBridge)
        context: Lambda context

    Returns:
        dict com status de processamento
    """
    logger.info("Evento recebido: %s", json.dumps(event, default=str))

    notifications = _extract_notifications(event)
    processed = 0
    errors = 0

    for notification in notifications:
        try:
            _process_notification(notification)
            processed += 1
        except Exception as exc:
            logger.error("Falha ao processar notificação: %s | payload=%s", exc, notification)
            errors += 1

    result = {
        "status": "completed",
        "processed": processed,
        "errors": errors,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    _log_audit_record("NOTIFICATION_BATCH", result)
    return result


#  Extração de eventos 

def _extract_notifications(event: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Normaliza o evento de entrada para uma lista de payloads de notificação.
    Suporta SNS Records e EventBridge direto.
    """
    notifications: list[dict[str, Any]] = []

    # Formato SNS
    if "Records" in event:
        for record in event["Records"]:
            if record.get("EventSource") == "aws:sns" or record.get("eventSource") == "aws:sns":
                message_str = record["Sns"]["Message"]
                try:
                    notifications.append(json.loads(message_str))
                except json.JSONDecodeError:
                    logger.warning("Mensagem SNS não é JSON válido: %s", message_str[:200])
        return notifications

    # Formato EventBridge direto
    if "detail" in event:
        notifications.append(event["detail"])
        return notifications

    # Payload direto (testes manuais)
    notifications.append(event)
    return notifications


#  Processamento de notificação 

def _process_notification(payload: dict[str, Any]) -> None:
    """
    Processa um único payload de notificação:
    1. Formata mensagem para Slack (Block Kit) e email
    2. Envia para Slack se webhook configurado
    3. Loga registro de auditoria estruturado
    """
    severity = payload.get("severity", payload.get("Severidade", "MEDIUM"))
    rule_name = payload.get("rule_name", payload.get("Regra", "UNKNOWN"))
    resource_id = payload.get("resource_id", "unknown")
    resource_type = payload.get("resource_type", "unknown")
    lgpd_article = payload.get("lgpd_article", payload.get("Artigo LGPD", "Não mapeado"))
    description = payload.get("rule_description", payload.get("Descrição", ""))
    auto_remediation = payload.get("auto_remediation", False)
    remediation_action = payload.get("remediation_action")
    evaluated_at = payload.get("evaluated_at", datetime.now(timezone.utc).isoformat())
    account_id = payload.get("account_id", "")
    region = payload.get("region", "")

    sev_cfg = SEVERITY_CONFIG.get(severity, SEVERITY_CONFIG["MEDIUM"])

    # Enviar para Slack se configurado
    if SLACK_WEBHOOK_URL:
        slack_payload = _build_slack_payload(
            severity=severity,
            sev_cfg=sev_cfg,
            rule_name=rule_name,
            resource_id=resource_id,
            resource_type=resource_type,
            lgpd_article=lgpd_article,
            description=description,
            auto_remediation=auto_remediation,
            remediation_action=remediation_action,
            evaluated_at=evaluated_at,
            account_id=account_id,
            region=region,
        )
        _send_slack_message(slack_payload)

    _log_audit_record("NOTIFICATION_SENT", {
        "rule_name": rule_name,
        "severity": severity,
        "resource_id": resource_id,
        "lgpd_article": lgpd_article,
        "auto_remediation": auto_remediation,
        "slack_sent": bool(SLACK_WEBHOOK_URL),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


#  Formatação Slack Block Kit 

def _build_slack_payload(
    severity: str,
    sev_cfg: dict[str, str],
    rule_name: str,
    resource_id: str,
    resource_type: str,
    lgpd_article: str,
    description: str,
    auto_remediation: bool,
    remediation_action: str | None,
    evaluated_at: str,
    account_id: str,
    region: str,
) -> dict[str, Any]:
    """
    Constrói payload Slack usando Block Kit para formatação rica.
    Inclui: severidade com emoji, recurso afetado, artigo LGPD,
    ação de remediação tomada e link para dashboard.

    Returns:
        dict com payload Slack Block Kit pronto para POST
    """
    emoji = sev_cfg["emoji"]
    label = sev_cfg["label"]
    color = sev_cfg["color"]

    remediation_text = (
        f" Remediação automática aplicada: `{remediation_action}`"
        if auto_remediation and remediation_action
        else " Requer intervenção manual"
    )

    env_tag = f"[{ENVIRONMENT.upper()}]" if ENVIRONMENT != "prod" else ""

    return {
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{emoji} Wayfinder Cloud {env_tag}  {label}: {rule_name}",
                        },
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Recurso:*\n`{resource_type}`\n`{resource_id}`"},
                            {"type": "mrkdwn", "text": f"*Artigo LGPD:*\n{lgpd_article}"},
                        ],
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Descrição:*\n{description}"},
                            {"type": "mrkdwn", "text": f"*Conta / Região:*\n`{account_id}` / `{region}`"},
                        ],
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"*Remediação:*\n{remediation_text}"},
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"Detectado em: {evaluated_at} | <{CLOUDWATCH_DASHBOARD_URL}|Ver Dashboard>",
                            }
                        ],
                    },
                    {"type": "divider"},
                ],
            }
        ]
    }


def _send_slack_message(payload: dict[str, Any]) -> None:
    """
    Envia mensagem para Slack via Incoming Webhook usando urllib (sem dependência extra).

    Args:
        payload: Payload Block Kit serializado

    Raises:
        Exception: se a requisição falhar após retry
    """
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        SLACK_WEBHOOK_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            resp_body = response.read().decode("utf-8")
            if resp_body != "ok":
                logger.warning("Resposta inesperada do Slack webhook: %s", resp_body)
            else:
                logger.info("Mensagem Slack enviada com sucesso")
    except urllib.error.HTTPError as exc:
        logger.error("Falha HTTP ao enviar para Slack: status=%s reason=%s", exc.code, exc.reason)
        raise
    except urllib.error.URLError as exc:
        logger.error("Falha de rede ao enviar para Slack: %s", exc.reason)
        raise


#  Auditoria 

def _log_audit_record(event_type: str, details: dict[str, Any]) -> None:
    """
    Gera log estruturado JSON para auditoria no CloudWatch Logs.
    Formato compatível com CloudWatch Logs Insights.
    """
    record = {
        "event_type": event_type,
        "service": "incident-notifier",
        "environment": ENVIRONMENT,
        "logged_at": datetime.now(timezone.utc).isoformat(),
        **details,
    }
    logger.info(json.dumps(record, ensure_ascii=False, default=str))
