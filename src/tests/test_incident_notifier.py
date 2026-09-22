"""
test_incident_notifier.py
Testes unitários para a Lambda incident-notifier do Wayfinder Cloud.

Cobertura:
  - _extract_notifications: SNS Records, EventBridge detail, payload direto
  - _build_slack_payload: campos obrigatórios, cor por severidade, remediação
  - _send_slack_message: sucesso, HTTPError silenciado, URLError silenciado
  - _process_notification: Slack enviado/não enviado conforme webhook var
  - _log_audit_record: campos presentes, event_type correto
  - handler: SNS batch, EventBridge, erros parciais, contagem de processed/errors
"""

from __future__ import annotations

import importlib.util
import json
import sys
import os
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import urllib.error

import pytest
from moto import mock_aws

# ── Loader isolado ────────────────────────────────────────────────────────────

_HANDLER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../lambdas/incident-notifier/handler.py")
)


def _load_handler():
    sys.modules.pop("incident_notifier_handler", None)
    spec = importlib.util.spec_from_file_location("incident_notifier_handler", _HANDLER_PATH)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["incident_notifier_handler"] = mod
    return mod


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def compliance_payload():
    """Payload de notificação padrão WAYFINDER-002 CRITICAL."""
    return {
        "rule_name":          "WAYFINDER-002",
        "severity":           "CRITICAL",
        "resource_id":        "vitacore-laudos-imagens-prod",
        "resource_type":      "AWS::S3::Bucket",
        "lgpd_article":       "Art. 46",
        "rule_description":   "S3 bucket com dados de saúde e acesso público habilitado",
        "auto_remediation":   True,
        "remediation_action": "enable_s3_block_public_access",
        "evaluated_at":       "2026-09-17T10:00:00Z",
        "account_id":         "123456789012",
        "region":             "us-east-1",
    }


@pytest.fixture
def sns_event(compliance_payload):
    """Evento Lambda com wrapper SNS Records."""
    return {
        "Records": [
            {
                "EventSource": "aws:sns",
                "Sns": {"Message": json.dumps(compliance_payload)},
            }
        ]
    }


@pytest.fixture
def eventbridge_event(compliance_payload):
    """Evento Lambda com wrapper EventBridge detail."""
    return {"detail": compliance_payload}


# ══════════════════════════════════════════════════════════════════════════════
# _extract_notifications
# ══════════════════════════════════════════════════════════════════════════════

class TestExtractNotifications:

    def test_extracts_from_sns_records(self, sns_event, compliance_payload):
        """Deve extrair payload do campo Sns.Message e parsear JSON."""
        with mock_aws():
            h = _load_handler()
        result = h._extract_notifications(sns_event)
        assert len(result) == 1
        assert result[0]["rule_name"] == "WAYFINDER-002"

    def test_extracts_multiple_sns_records(self, compliance_payload):
        """Deve extrair múltiplos records de um batch SNS."""
        p2 = {**compliance_payload, "rule_name": "WAYFINDER-003"}
        event = {
            "Records": [
                {"EventSource": "aws:sns", "Sns": {"Message": json.dumps(compliance_payload)}},
                {"EventSource": "aws:sns", "Sns": {"Message": json.dumps(p2)}},
            ]
        }
        with mock_aws():
            h = _load_handler()
        result = h._extract_notifications(event)
        assert len(result) == 2
        assert result[1]["rule_name"] == "WAYFINDER-003"

    def test_extracts_from_eventbridge_detail(self, eventbridge_event):
        """Deve extrair payload do campo 'detail' do EventBridge."""
        with mock_aws():
            h = _load_handler()
        result = h._extract_notifications(eventbridge_event)
        assert len(result) == 1
        assert result[0]["severity"] == "CRITICAL"

    def test_extracts_direct_payload(self, compliance_payload):
        """Payload direto (sem wrapper) deve ser retornado como lista de um item."""
        with mock_aws():
            h = _load_handler()
        result = h._extract_notifications(compliance_payload)
        assert len(result) == 1
        assert result[0]["resource_id"] == "vitacore-laudos-imagens-prod"

    def test_skips_invalid_json_in_sns(self):
        """Mensagem SNS com JSON inválido deve ser ignorada silenciosamente."""
        event = {
            "Records": [
                {"EventSource": "aws:sns", "Sns": {"Message": "not-json"}},
            ]
        }
        with mock_aws():
            h = _load_handler()
        result = h._extract_notifications(event)
        assert result == []

    def test_returns_empty_list_for_empty_records(self):
        """Lista de Records vazia deve retornar lista vazia."""
        with mock_aws():
            h = _load_handler()
        result = h._extract_notifications({"Records": []})
        assert result == []


# ══════════════════════════════════════════════════════════════════════════════
# _build_slack_payload
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildSlackPayload:

    def _build(self, h, severity="CRITICAL", auto_remediation=True, remediation_action="enable_s3_block_public_access"):
        sev_cfg = h.SEVERITY_CONFIG.get(severity, h.SEVERITY_CONFIG["MEDIUM"])
        return h._build_slack_payload(
            severity=severity,
            sev_cfg=sev_cfg,
            rule_name="WAYFINDER-002",
            resource_id="vitacore-laudos-imagens-prod",
            resource_type="AWS::S3::Bucket",
            lgpd_article="Art. 46",
            description="S3 público",
            auto_remediation=auto_remediation,
            remediation_action=remediation_action,
            evaluated_at="2026-09-17T10:00:00Z",
            account_id="123456789012",
            region="us-east-1",
        )

    def test_returns_dict_with_attachments(self):
        with mock_aws():
            h = _load_handler()
        payload = self._build(h)
        assert "attachments" in payload
        assert len(payload["attachments"]) == 1

    def test_critical_uses_red_color(self):
        with mock_aws():
            h = _load_handler()
        payload = self._build(h, severity="CRITICAL")
        assert payload["attachments"][0]["color"] == "#FF0000"

    def test_high_uses_orange_color(self):
        with mock_aws():
            h = _load_handler()
        payload = self._build(h, severity="HIGH")
        assert payload["attachments"][0]["color"] == "#FF8C00"

    def test_low_uses_green_color(self):
        with mock_aws():
            h = _load_handler()
        payload = self._build(h, severity="LOW")
        assert payload["attachments"][0]["color"] == "#36A64F"

    def test_blocks_contains_rule_name_in_header(self):
        with mock_aws():
            h = _load_handler()
        payload = self._build(h)
        blocks = payload["attachments"][0]["blocks"]
        header = blocks[0]
        assert header["type"] == "header"
        assert "WAYFINDER-002" in header["text"]["text"]

    def test_auto_remediation_message_included(self):
        with mock_aws():
            h = _load_handler()
        payload = self._build(h, auto_remediation=True, remediation_action="enable_s3_block_public_access")
        blocks_text = json.dumps(payload["attachments"][0]["blocks"])
        assert "enable_s3_block_public_access" in blocks_text

    def test_manual_remediation_message_when_no_auto(self):
        with mock_aws():
            h = _load_handler()
        payload = self._build(h, auto_remediation=False, remediation_action=None)
        blocks_text = json.dumps(payload["attachments"][0]["blocks"])
        assert "manual" in blocks_text.lower() or "intervenção" in blocks_text.lower()

    def test_lgpd_article_in_payload(self):
        with mock_aws():
            h = _load_handler()
        payload = self._build(h)
        blocks_text = json.dumps(payload["attachments"][0]["blocks"])
        assert "Art. 46" in blocks_text

    def test_resource_id_in_payload(self):
        with mock_aws():
            h = _load_handler()
        payload = self._build(h)
        blocks_text = json.dumps(payload["attachments"][0]["blocks"])
        assert "vitacore-laudos-imagens-prod" in blocks_text

    def test_all_severity_configs_exist(self):
        """Todos os 5 níveis de severidade devem ter configuração."""
        with mock_aws():
            h = _load_handler()
        for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
            assert sev in h.SEVERITY_CONFIG
            cfg = h.SEVERITY_CONFIG[sev]
            assert "color" in cfg
            assert "label" in cfg


# ══════════════════════════════════════════════════════════════════════════════
# _send_slack_message
# ══════════════════════════════════════════════════════════════════════════════

class TestSendSlackMessage:

    def test_sends_post_to_webhook(self, monkeypatch):
        """Deve fazer POST para o webhook com Content-Type application/json."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test-webhook")
        with mock_aws():
            h = _load_handler()

        calls = []
        mock_response = MagicMock()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.read.return_value = b"ok"

        with patch("urllib.request.urlopen", return_value=mock_response) as mock_open:
            h._send_slack_message({"attachments": []})
            assert mock_open.called

    def test_http_error_raises(self, monkeypatch):
        """HTTPError deve ser relançado (para o handler capturar e contar como erro)."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
        with mock_aws():
            h = _load_handler()

        http_error = urllib.error.HTTPError(
            url="https://hooks.slack.com/test",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=None,
        )
        with patch("urllib.request.urlopen", side_effect=http_error):
            with pytest.raises(urllib.error.HTTPError):
                h._send_slack_message({"attachments": []})

    def test_url_error_raises(self, monkeypatch):
        """URLError deve ser relançado."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
        with mock_aws():
            h = _load_handler()

        url_error = urllib.error.URLError("Connection refused")
        with patch("urllib.request.urlopen", side_effect=url_error):
            with pytest.raises(urllib.error.URLError):
                h._send_slack_message({"attachments": []})


# ══════════════════════════════════════════════════════════════════════════════
# _process_notification
# ══════════════════════════════════════════════════════════════════════════════

class TestProcessNotification:

    def test_slack_not_called_when_no_webhook(self, compliance_payload, monkeypatch):
        """Sem SLACK_WEBHOOK_URL configurado, Slack não deve ser chamado."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
        with mock_aws():
            h = _load_handler()
            with patch.object(h, "_send_slack_message") as mock_slack:
                h._process_notification(compliance_payload)
        mock_slack.assert_not_called()

    def test_slack_called_when_webhook_set(self, compliance_payload, monkeypatch):
        """Com SLACK_WEBHOOK_URL configurado, Slack deve ser chamado."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/fake")
        with mock_aws():
            h = _load_handler()
            with patch.object(h, "_send_slack_message") as mock_slack:
                h._process_notification(compliance_payload)
        mock_slack.assert_called_once()

    def test_process_does_not_raise_on_missing_optional_fields(self, monkeypatch):
        """Payload com campos mínimos não deve lançar exceção."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
        minimal = {"severity": "HIGH", "rule_name": "WAYFINDER-005"}
        with mock_aws():
            h = _load_handler()
            try:
                h._process_notification(minimal)
            except Exception as exc:
                pytest.fail(f"Não deve lançar exceção: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# _log_audit_record
# ══════════════════════════════════════════════════════════════════════════════

class TestLogAuditRecord:

    def test_record_contains_event_type(self):
        with mock_aws():
            h = _load_handler()
        captured = []
        with patch.object(h.logger, "info", side_effect=lambda msg, *a: captured.append(msg)):
            h._log_audit_record("NOTIFICATION_SENT", {"rule_name": "WAYFINDER-002"})
        assert len(captured) >= 1
        record = json.loads(captured[-1])
        assert record["event_type"] == "NOTIFICATION_SENT"

    def test_record_contains_environment(self):
        with mock_aws():
            h = _load_handler()
        captured = []
        with patch.object(h.logger, "info", side_effect=lambda msg, *a: captured.append(msg)):
            h._log_audit_record("TEST", {"key": "value"})
        record = json.loads(captured[-1])
        assert "environment" in record
        assert record["environment"] == "test"

    def test_record_contains_service_name(self):
        with mock_aws():
            h = _load_handler()
        captured = []
        with patch.object(h.logger, "info", side_effect=lambda msg, *a: captured.append(msg)):
            h._log_audit_record("TEST", {})
        record = json.loads(captured[-1])
        assert record["service"] == "incident-notifier"

    def test_record_contains_logged_at(self):
        with mock_aws():
            h = _load_handler()
        captured = []
        with patch.object(h.logger, "info", side_effect=lambda msg, *a: captured.append(msg)):
            h._log_audit_record("TEST", {})
        record = json.loads(captured[-1])
        assert "logged_at" in record

    def test_extra_details_merged_in_record(self):
        with mock_aws():
            h = _load_handler()
        captured = []
        with patch.object(h.logger, "info", side_effect=lambda msg, *a: captured.append(msg)):
            h._log_audit_record("NOTIFICATION_SENT", {"rule_name": "WAYFINDER-002", "slack_sent": True})
        record = json.loads(captured[-1])
        assert record["rule_name"] == "WAYFINDER-002"
        assert record["slack_sent"] is True


# ══════════════════════════════════════════════════════════════════════════════
# Handler principal
# ══════════════════════════════════════════════════════════════════════════════

class TestHandlerMainFlow:

    def test_sns_event_returns_completed(self, sns_event, monkeypatch):
        """Handler com evento SNS deve retornar status completed."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
        with mock_aws():
            h = _load_handler()
            result = h.handler(sns_event, None)
        assert result["status"] == "completed"

    def test_eventbridge_event_returns_completed(self, eventbridge_event, monkeypatch):
        """Handler com evento EventBridge deve retornar status completed."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
        with mock_aws():
            h = _load_handler()
            result = h.handler(eventbridge_event, None)
        assert result["status"] == "completed"

    def test_processed_count_correct(self, sns_event, monkeypatch):
        """Contador processed deve refletir número de notificações bem-sucedidas."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
        with mock_aws():
            h = _load_handler()
            result = h.handler(sns_event, None)
        assert result["processed"] == 1
        assert result["errors"] == 0

    def test_error_count_incremented_on_failure(self, sns_event, monkeypatch):
        """Falha em _process_notification deve incrementar errors sem derrubar o handler."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
        with mock_aws():
            h = _load_handler()
            with patch.object(h, "_process_notification", side_effect=RuntimeError("boom")):
                result = h.handler(sns_event, None)
        assert result["status"] == "completed"
        assert result["errors"] == 1
        assert result["processed"] == 0

    def test_batch_sns_processes_all(self, compliance_payload, monkeypatch):
        """Batch com 3 records SNS deve processar todos os 3."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
        batch = {
            "Records": [
                {"EventSource": "aws:sns", "Sns": {"Message": json.dumps({**compliance_payload, "rule_name": f"WAYFINDER-00{i}"})} }
                for i in range(1, 4)
            ]
        }
        with mock_aws():
            h = _load_handler()
            result = h.handler(batch, None)
        assert result["processed"] == 3
        assert result["errors"] == 0

    def test_partial_failures_in_batch(self, compliance_payload, monkeypatch):
        """Batch parcialmente com falha deve contar processed e errors separadamente."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
        p2 = {**compliance_payload, "rule_name": "WAYFINDER-003"}
        batch = {
            "Records": [
                {"EventSource": "aws:sns", "Sns": {"Message": json.dumps(compliance_payload)}},
                {"EventSource": "aws:sns", "Sns": {"Message": json.dumps(p2)}},
            ]
        }
        call_count = [0]
        def selective_fail(payload):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("falha seletiva")
        with mock_aws():
            h = _load_handler()
            with patch.object(h, "_process_notification", side_effect=selective_fail):
                result = h.handler(batch, None)
        assert result["processed"] == 1
        assert result["errors"] == 1

    def test_result_contains_timestamp(self, eventbridge_event, monkeypatch):
        """Resultado deve sempre conter timestamp."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
        with mock_aws():
            h = _load_handler()
            result = h.handler(eventbridge_event, None)
        assert "timestamp" in result
        assert len(result["timestamp"]) > 0

    def test_direct_payload_processed(self, compliance_payload, monkeypatch):
        """Payload direto sem wrapper deve ser processado normalmente."""
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "")
        with mock_aws():
            h = _load_handler()
            result = h.handler(compliance_payload, None)
        assert result["status"] == "completed"
        assert result["processed"] == 1
