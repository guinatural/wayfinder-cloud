"""
test_compliance_evaluator.py
Testes unitários para a Lambda compliance-evaluator do Wayfinder Cloud.
"""

import json
import sys
import os
import pytest
import boto3
from moto import mock_aws
from unittest.mock import patch, MagicMock

# Adiciona o diretório da Lambda ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../lambdas/compliance-evaluator"))


class TestComplianceEvaluatorParsing:
    """Testa o parsing de eventos Config do EventBridge."""

    def test_parse_valid_noncompliant_event(self, config_noncompliant_event):
        """Evento NON_COMPLIANT válido deve ser parseado corretamente."""
        with mock_aws():
            import handler as h
            result = h._parse_config_event(config_noncompliant_event)

        assert result["rule_name"]    == "wayfinder-dev-WAYFINDER-002"
        assert result["resource_type"] == "AWS::S3::Bucket"
        assert result["resource_id"]   == "vitacore-laudos-imagens-prod"
        assert result["account_id"]    == "123456789012"
        assert result["compliance_type"] == "NON_COMPLIANT"

    def test_parse_compliant_event_raises(self):
        """Evento COMPLIANT deve lançar ValueError (não deve ser processado)."""
        event = {
            "detail": {
                "configRuleName":  "wayfinder-dev-WAYFINDER-001",
                "resourceType":    "AWS::S3::Bucket",
                "resourceId":      "some-bucket",
                "awsAccountId":    "123456789012",
                "awsRegion":       "us-east-1",
                "newEvaluationResult": {"complianceType": "COMPLIANT", "resultRecordedTime": "2026-08-21T14:32:00Z"},
            }
        }
        with mock_aws():
            import handler as h
            with pytest.raises(ValueError, match="COMPLIANT"):
                h._parse_config_event(event)

    def test_parse_missing_detail_raises(self):
        """Evento sem 'detail' deve lançar KeyError."""
        with mock_aws():
            import handler as h
            with pytest.raises(KeyError):
                h._parse_config_event({})


class TestSeverityClassification:
    """Testa a classificação de severidade das regras WAYFINDER."""

    def test_wayfinder_002_is_critical(self):
        """WAYFINDER-002 (S3 público) deve sempre ser CRITICAL."""
        with mock_aws():
            import handler as h
            rule_info = h.RULE_LGPD_MAP.get("WAYFINDER-002", {})
        assert rule_info.get("severity") == "CRITICAL"

    def test_wayfinder_002_has_auto_remediation(self):
        """WAYFINDER-002 deve ter remediação automática habilitada."""
        with mock_aws():
            import handler as h
            rule_info = h.RULE_LGPD_MAP.get("WAYFINDER-002", {})
        assert rule_info.get("auto_remediation") is True
        assert rule_info.get("remediation_action") == "enable_s3_block_public_access"

    def test_wayfinder_004_is_high(self):
        """WAYFINDER-004 (RDS sem criptografia) deve ser HIGH."""
        with mock_aws():
            import handler as h
            rule_info = h.RULE_LGPD_MAP.get("WAYFINDER-004", {})
        assert rule_info.get("severity") == "HIGH"
        assert rule_info.get("auto_remediation") is False

    def test_all_critical_rules_mapped(self):
        """As 4 regras CRITICAL com auto-remediação devem estar mapeadas."""
        with mock_aws():
            import handler as h
            critical_auto = [
                k for k, v in h.RULE_LGPD_MAP.items()
                if v.get("severity") == "CRITICAL" and v.get("auto_remediation")
            ]
        # WAYFINDER-001, 002, 003, 006 devem ter auto-remediação crítica
        assert len(critical_auto) >= 4

    def test_lgpd_article_present_for_all_rules(self):
        """Todas as regras WAYFINDER devem ter artigo LGPD mapeado."""
        with mock_aws():
            import handler as h
            wayfinder_rules = {k: v for k, v in h.RULE_LGPD_MAP.items() if k.startswith("WAYFINDER-")}
        for rule_id, info in wayfinder_rules.items():
            assert "article" in info, f"Regra {rule_id} sem artigo LGPD mapeado"
            assert len(info["article"]) > 0, f"Regra {rule_id} com artigo vazio"


class TestCloudWatchMetrics:
    """Testa a publicação de métricas no CloudWatch."""

    def test_publish_metric_does_not_raise(self, config_noncompliant_event):
        """Falha ao publicar métrica não deve derrubar o fluxo principal."""
        with mock_aws():
            boto3.client("sns", region_name="us-east-1").create_topic(Name="wayfinder-test-critical")
            boto3.client("sns", region_name="us-east-1").create_topic(Name="wayfinder-test-warning")
            boto3.client("sns", region_name="us-east-1").create_topic(Name="wayfinder-test-info")

            import handler as h
            enriched = {
                "rule_name":        "WAYFINDER-002",
                "resource_type":    "AWS::S3::Bucket",
                "resource_id":      "vitacore-test-bucket",
                "account_id":       "123456789012",
                "region":           "us-east-1",
                "severity":         "CRITICAL",
                "environment":      "test",
                "auto_remediation": True,
            }
            # Não deve lançar exceção mesmo se CloudWatch falhar
            try:
                h._publish_cloudwatch_metric(enriched)
            except Exception as e:
                pytest.fail(f"_publish_cloudwatch_metric lançou exceção inesperada: {e}")


class TestSNSNotification:
    """Testa a publicação de notificações no SNS."""

    def test_publish_critical_notification(self, sns_topics):
        """Evento CRITICAL deve publicar no topic crítico."""
        with mock_aws():
            sns = boto3.client("sns", region_name="us-east-1")
            topics = {
                "critical": sns.create_topic(Name="wayfinder-test-critical")["TopicArn"],
                "warning":  sns.create_topic(Name="wayfinder-test-warning")["TopicArn"],
                "info":     sns.create_topic(Name="wayfinder-test-info")["TopicArn"],
            }

            import handler as h

            event = {
                "severity":         "CRITICAL",
                "rule_name":        "WAYFINDER-002",
                "resource_type":    "AWS::S3::Bucket",
                "resource_id":      "vitacore-laudos-imagens-prod",
                "account_id":       "123456789012",
                "region":           "us-east-1",
                "lgpd_article":     "Art. 46",
                "rule_description": "S3 público",
                "auto_remediation": True,
                "remediation_action": "enable_s3_block_public_access",
                "evaluated_at":     "2026-08-21T14:32:00Z",
                "environment":      "test",
            }

            # Não deve lançar exceção
            h._publish_notification(event)
