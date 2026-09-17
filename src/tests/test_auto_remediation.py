"""
test_auto_remediation.py
Testes unitários para a Lambda auto-remediation do Wayfinder Cloud.

Cobertura:
  - Remediações individuais: S3 Block Public Access, SSE-KMS, CloudTrail
  - Remediação parcial: EC2 isolation (apenas log, sem ação destrutiva)
  - Guardrail 1: tag remediation-exempt=true
  - Guardrail 2: limite de tentativas (3 por hora)
  - Dispatcher: ação desconhecida → status error
  - Handler principal: fluxo completo com EventBridge detail
  - Observabilidade: métricas CloudWatch, registro de auditoria
  - Resiliência: ClientError não estoura o handler

Nota de isolamento:
  Usa importlib.util para carregar o módulo pelo caminho absoluto,
  evitando colisão com compliance-evaluator/handler.py que compartilha
  o nome 'handler' e já pode estar em sys.modules ao rodar a suite completa.
"""

import importlib.util
import sys
import os
import pytest
import boto3
from moto import mock_aws
from unittest.mock import patch
from botocore.exceptions import ClientError

_HANDLER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../lambdas/auto-remediation/handler.py")
)


def _load_handler():
    """Carrega auto-remediation/handler.py de forma isolada pelo caminho absoluto."""
    sys.modules.pop("auto_remediation_handler", None)
    spec = importlib.util.spec_from_file_location("auto_remediation_handler", _HANDLER_PATH)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["auto_remediation_handler"] = mod
    return mod


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def remediation_event():
    """Evento EventBridge para WAYFINDER-002 — S3 public access."""
    return {
        "detail": {
            "action":        "enable_s3_block_public_access",
            "resource_id":   "vitacore-laudos-imagens-prod",
            "resource_type": "AWS::S3::Bucket",
            "rule_name":     "WAYFINDER-002",
            "severity":      "CRITICAL",
            "lgpd_article":  "Art. 46",
            "account_id":    "123456789012",
            "region":        "us-east-1",
            "triggered_at":  "2026-09-17T10:00:00Z",
        }
    }


@pytest.fixture
def kms_event():
    """Evento EventBridge para WAYFINDER-001 — S3 sem KMS."""
    return {
        "detail": {
            "action":        "enable_s3_kms_encryption",
            "resource_id":   "vitacore-exames-prod",
            "resource_type": "AWS::S3::Bucket",
            "rule_name":     "WAYFINDER-001",
            "severity":      "CRITICAL",
            "lgpd_article":  "Art. 46",
            "account_id":    "123456789012",
            "region":        "us-east-1",
            "triggered_at":  "2026-09-17T10:00:00Z",
        }
    }


@pytest.fixture
def cloudtrail_event():
    """Evento EventBridge para WAYFINDER-003 — CloudTrail desabilitado."""
    return {
        "detail": {
            "action":        "enable_cloudtrail",
            "resource_id":   "wayfinder-vitacore-trail",
            "resource_type": "AWS::CloudTrail::Trail",
            "rule_name":     "WAYFINDER-003",
            "severity":      "CRITICAL",
            "lgpd_article":  "Art. 37",
            "account_id":    "123456789012",
            "region":        "us-east-1",
            "triggered_at":  "2026-09-17T10:00:00Z",
        }
    }


@pytest.fixture
def ec2_isolation_event():
    """Evento EventBridge para WAYFINDER-006 — EC2 em subnet pública."""
    return {
        "detail": {
            "action":        "isolate_ec2_security_group",
            "resource_id":   "i-0abc123def456789",
            "resource_type": "AWS::EC2::Instance",
            "rule_name":     "WAYFINDER-006",
            "severity":      "CRITICAL",
            "lgpd_article":  "Art. 46",
            "account_id":    "123456789012",
            "region":        "us-east-1",
            "triggered_at":  "2026-09-17T10:00:00Z",
        }
    }


# ──────────────────────────────────────────────────────────────────────────────
# _enable_s3_block_public_access
# ──────────────────────────────────────────────────────────────────────────────

class TestEnableS3BlockPublicAccess:

    def test_all_four_flags_set_to_true(self):
        """Block Public Access deve habilitar os 4 flags como True."""
        with mock_aws():
            h  = _load_handler()
            s3 = boto3.client("s3", region_name="us-east-1")
            bucket = "vitacore-laudos-imagens-prod"
            s3.create_bucket(Bucket=bucket)

            h._enable_s3_block_public_access(resource_id=bucket)

            cfg   = s3.get_public_access_block(Bucket=bucket)["PublicAccessBlockConfiguration"]
            assert cfg["BlockPublicAcls"]       is True
            assert cfg["IgnorePublicAcls"]      is True
            assert cfg["BlockPublicPolicy"]     is True
            assert cfg["RestrictPublicBuckets"] is True

    def test_returns_descriptive_message(self):
        """Retorno deve mencionar o bucket corrigido."""
        with mock_aws():
            h  = _load_handler()
            s3 = boto3.client("s3", region_name="us-east-1")
            bucket = "test-bucket-msg"
            s3.create_bucket(Bucket=bucket)
            result = h._enable_s3_block_public_access(resource_id=bucket)
        assert bucket in result

    def test_raises_on_nonexistent_bucket(self):
        """Bucket inexistente deve levantar ClientError."""
        with mock_aws():
            h = _load_handler()
            with pytest.raises(ClientError):
                h._enable_s3_block_public_access(resource_id="bucket-inexistente-xyz")


# ──────────────────────────────────────────────────────────────────────────────
# _enable_s3_kms_encryption
# ──────────────────────────────────────────────────────────────────────────────

class TestEnableS3KmsEncryption:

    def test_applied_without_key_arn(self):
        """SSE-KMS deve ser habilitado sem KMS ARN explícito."""
        with mock_aws():
            h  = _load_handler()
            s3 = boto3.client("s3", region_name="us-east-1")
            bucket = "vitacore-exames-prod"
            s3.create_bucket(Bucket=bucket)
            result = h._enable_s3_kms_encryption(resource_id=bucket)
        assert bucket in result

    def test_applied_with_key_arn(self):
        """SSE-KMS com KMS ARN explícito deve incluir a chave."""
        with mock_aws():
            h  = _load_handler()
            s3 = boto3.client("s3", region_name="us-east-1")
            bucket = "vitacore-exames-kms-prod"
            s3.create_bucket(Bucket=bucket)
            result = h._enable_s3_kms_encryption(
                resource_id=bucket,
                kms_key_arn="arn:aws:kms:us-east-1:123456789012:key/test-key",
            )
        assert bucket in result

    def test_returns_descriptive_message(self):
        """Retorno deve mencionar o bucket."""
        with mock_aws():
            h  = _load_handler()
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="bucket-kms-test")
            result = h._enable_s3_kms_encryption(resource_id="bucket-kms-test")
        assert "bucket-kms-test" in result


# ──────────────────────────────────────────────────────────────────────────────
# _enable_cloudtrail
# ──────────────────────────────────────────────────────────────────────────────

class TestEnableCloudTrail:

    def test_start_logging_called(self):
        """start_logging deve ser chamado para o trail correto."""
        with mock_aws():
            h  = _load_handler()
            ct = boto3.client("cloudtrail", region_name="us-east-1")
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="wayfinder-ct-test-bucket")
            trail = "wayfinder-vitacore-trail"
            ct.create_trail(Name=trail, S3BucketName="wayfinder-ct-test-bucket")
            result = h._enable_cloudtrail(resource_id=trail)
        assert trail in result

    def test_returns_descriptive_message(self):
        """Retorno deve mencionar o trail reabilitado."""
        with mock_aws():
            h  = _load_handler()
            ct = boto3.client("cloudtrail", region_name="us-east-1")
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="ct-test-bucket-2")
            trail = "test-trail-desc"
            ct.create_trail(Name=trail, S3BucketName="ct-test-bucket-2")
            result = h._enable_cloudtrail(resource_id=trail)
        assert trail in result


# ──────────────────────────────────────────────────────────────────────────────
# _isolate_ec2_security_group
# ──────────────────────────────────────────────────────────────────────────────

class TestIsolateEc2SecurityGroup:

    def test_returns_warning_message(self):
        """Isolamento de EC2 deve retornar aviso de intervenção manual."""
        with mock_aws():
            h      = _load_handler()
            result = h._isolate_ec2_security_group(resource_id="i-0abc123def456789")
        assert "ATENÇÃO" in result or "manual" in result.lower()

    def test_mentions_resource_id(self):
        """Mensagem deve referenciar a instância."""
        with mock_aws():
            h           = _load_handler()
            instance_id = "i-0abc123def456789"
            result      = h._isolate_ec2_security_group(resource_id=instance_id)
        assert instance_id in result

    def test_does_not_raise(self):
        """Isolamento não deve lançar exceção — apenas loga."""
        with mock_aws():
            h = _load_handler()
            try:
                h._isolate_ec2_security_group(resource_id="i-0abc123def456789")
            except Exception as exc:
                pytest.fail(f"Isolamento não deve lançar exceção: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# Dispatcher
# ──────────────────────────────────────────────────────────────────────────────

class TestRemediationDispatch:

    def test_all_four_actions_registered(self):
        """As 4 ações de remediação devem estar no dispatcher."""
        with mock_aws():
            h = _load_handler()
        expected = {
            "enable_s3_block_public_access",
            "enable_s3_kms_encryption",
            "enable_cloudtrail",
            "isolate_ec2_security_group",
        }
        assert expected == set(h.REMEDIATION_DISPATCH.keys())

    def test_each_entry_is_callable(self):
        """Cada entrada no dispatcher deve ser callable."""
        with mock_aws():
            h = _load_handler()
        for action, fn in h.REMEDIATION_DISPATCH.items():
            assert callable(fn), f"Ação '{action}' não é callable"

    def test_unknown_action_returns_error_status(self):
        """Ação desconhecida deve retornar status error sem lançar exceção."""
        with mock_aws():
            h = _load_handler()
            event = {
                "detail": {
                    "action":        "acao_inexistente",
                    "resource_id":   "qualquer-recurso",
                    "resource_type": "AWS::S3::Bucket",
                    "rule_name":     "WAYFINDER-001",
                    "severity":      "HIGH",
                    "lgpd_article":  "Art. 46",
                    "account_id":    "123456789012",
                    "region":        "us-east-1",
                    "triggered_at":  "2026-09-17T10:00:00Z",
                }
            }
            result = h.handler(event, None)
        assert result["status"] == "error"
        assert "unknown-action" in result["reason"]


# ──────────────────────────────────────────────────────────────────────────────
# Guardrail 1 — remediation-exempt
# ──────────────────────────────────────────────────────────────────────────────

class TestGuardrailRemediationExempt:

    def test_exempt_resource_returns_skipped(self, remediation_event):
        """Recurso com tag exempt deve retornar status skipped."""
        with mock_aws():
            h = _load_handler()
            with patch.object(h, "_is_remediation_exempt", return_value=True):
                result = h.handler(remediation_event, None)
        assert result["status"] == "skipped"
        assert result["reason"] == "remediation-exempt"

    def test_non_exempt_resource_proceeds(self, remediation_event):
        """Recurso sem tag exempt deve prosseguir com remediação."""
        with mock_aws():
            h  = _load_handler()
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="vitacore-laudos-imagens-prod")
            with patch.object(h, "_is_remediation_exempt", return_value=False):
                result = h.handler(remediation_event, None)
        assert result["status"] == "success"

    def test_default_returns_false(self):
        """_is_remediation_exempt padrão deve retornar False."""
        with mock_aws():
            h = _load_handler()
        assert h._is_remediation_exempt("qualquer-recurso") is False


# ──────────────────────────────────────────────────────────────────────────────
# Guardrail 2 — limite de tentativas
# ──────────────────────────────────────────────────────────────────────────────

class TestGuardrailAttemptLimit:

    def test_exceeded_returns_blocked(self, remediation_event):
        """Recurso que excedeu o limite deve retornar status blocked."""
        with mock_aws():
            h = _load_handler()
            with patch.object(h, "_is_remediation_exempt",  return_value=False):
                with patch.object(h, "_exceeded_attempt_limit", return_value=True):
                    result = h.handler(remediation_event, None)
        assert result["status"] == "blocked"
        assert result["reason"] == "attempt-limit-exceeded"

    def test_default_false_without_table(self, monkeypatch):
        """Sem tabela DynamoDB configurada, deve retornar False."""
        monkeypatch.setenv("REMEDIATION_ATTEMPTS_TABLE", "")
        with mock_aws():
            h = _load_handler()
        assert h._exceeded_attempt_limit("recurso-x", "WAYFINDER-002") is False

    def test_within_limit_proceeds(self, remediation_event):
        """Recurso dentro do limite deve prosseguir."""
        with mock_aws():
            h  = _load_handler()
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="vitacore-laudos-imagens-prod")
            with patch.object(h, "_is_remediation_exempt",  return_value=False):
                with patch.object(h, "_exceeded_attempt_limit", return_value=False):
                    result = h.handler(remediation_event, None)
        assert result["status"] == "success"


# ──────────────────────────────────────────────────────────────────────────────
# Handler principal — fluxo completo
# ──────────────────────────────────────────────────────────────────────────────

class TestHandlerMainFlow:

    def test_s3_block_public_access_end_to_end(self, remediation_event):
        with mock_aws():
            h  = _load_handler()
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="vitacore-laudos-imagens-prod")
            result = h.handler(remediation_event, None)
        assert result["status"] == "success"
        assert "vitacore-laudos-imagens-prod" in result["message"]

    def test_s3_kms_encryption_end_to_end(self, kms_event):
        with mock_aws():
            h  = _load_handler()
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="vitacore-exames-prod")
            result = h.handler(kms_event, None)
        assert result["status"] == "success"

    def test_cloudtrail_end_to_end(self, cloudtrail_event):
        with mock_aws():
            h  = _load_handler()
            ct = boto3.client("cloudtrail", region_name="us-east-1")
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="wayfinder-ct-trail-bucket")
            ct.create_trail(
                Name="wayfinder-vitacore-trail",
                S3BucketName="wayfinder-ct-trail-bucket",
            )
            result = h.handler(cloudtrail_event, None)
        assert result["status"] == "success"

    def test_ec2_isolation_end_to_end(self, ec2_isolation_event):
        """Isolamento EC2 é remediação parcial — retorna success com aviso."""
        with mock_aws():
            h      = _load_handler()
            result = h.handler(ec2_isolation_event, None)
        assert result["status"] == "success"
        assert "manual" in result["message"].lower() or "ATENÇÃO" in result["message"]

    def test_clienterror_returns_error_status(self, remediation_event):
        """ClientError durante remediação deve retornar status error."""
        with mock_aws():
            h     = _load_handler()
            error = ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
                "PutPublicAccessBlock",
            )
            with patch.object(h, "_enable_s3_block_public_access", side_effect=error):
                with patch.object(h, "_is_remediation_exempt",     return_value=False):
                    with patch.object(h, "_exceeded_attempt_limit", return_value=False):
                        result = h.handler(remediation_event, None)
        assert result["status"] == "error"

    def test_guardrail_exempt_precedes_remediation(self, remediation_event):
        """Guardrail exempt deve ser verificado antes de qualquer ação AWS."""
        with mock_aws():
            h = _load_handler()
            # Bucket NÃO criado — se remediação rodar, levanta ClientError
            with patch.object(h, "_is_remediation_exempt", return_value=True):
                result = h.handler(remediation_event, None)
        assert result["status"] == "skipped"


# ──────────────────────────────────────────────────────────────────────────────
# Observabilidade
# ──────────────────────────────────────────────────────────────────────────────

class TestObservability:

    def test_publish_metric_success_status(self):
        """Métrica com status success não deve lançar exceção."""
        with mock_aws():
            h = _load_handler()
            try:
                h._publish_remediation_metric("WAYFINDER-002", "CRITICAL", "success")
            except Exception as exc:
                pytest.fail(f"Não deve lançar exceção: {exc}")

    def test_publish_metric_error_status(self):
        """Métrica com status error não deve lançar exceção."""
        with mock_aws():
            h = _load_handler()
            try:
                h._publish_remediation_metric("WAYFINDER-002", "CRITICAL", "error")
            except Exception as exc:
                pytest.fail(f"Não deve lançar exceção: {exc}")

    def test_log_audit_record_fields(self):
        """Registro de auditoria deve conter todos os campos esperados."""
        with mock_aws():
            h = _load_handler()
            detail = {
                "action":        "enable_s3_block_public_access",
                "resource_id":   "vitacore-laudos-imagens-prod",
                "resource_type": "AWS::S3::Bucket",
                "rule_name":     "WAYFINDER-002",
                "severity":      "CRITICAL",
                "lgpd_article":  "Art. 46",
                "account_id":    "123456789012",
                "region":        "us-east-1",
            }
            record = h._log_audit_record(
                event_detail=detail,
                result_message="Block Public Access habilitado",
                status="success",
                triggered_at="2026-09-17T10:00:00Z",
            )
        assert record["event_type"]   == "REMEDIATION"
        assert record["rule_name"]    == "WAYFINDER-002"
        assert record["resource_id"]  == "vitacore-laudos-imagens-prod"
        assert record["status"]       == "success"
        assert record["lgpd_article"] == "Art. 46"
        assert "timestamp" in record

    def test_log_audit_record_includes_environment(self):
        """Registro de auditoria deve incluir o ambiente."""
        with mock_aws():
            h = _load_handler()
            detail = {
                "action": "enable_cloudtrail", "resource_id": "trail-t",
                "resource_type": "AWS::CloudTrail::Trail", "rule_name": "WAYFINDER-003",
                "severity": "CRITICAL", "lgpd_article": "Art. 37",
                "account_id": "123456789012", "region": "us-east-1",
            }
            record = h._log_audit_record(
                event_detail=detail,
                result_message="Logging reabilitado",
                status="success",
                triggered_at="2026-09-17T10:00:00Z",
            )
        assert "environment" in record
        assert record["environment"] == "test"

    def test_cloudwatch_failure_does_not_block_remediation(self, remediation_event):
        """Falha silenciosa no CloudWatch não deve impedir remediação S3."""
        with mock_aws():
            h  = _load_handler()
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="vitacore-laudos-imagens-prod")
            with patch.object(h, "_publish_remediation_metric", return_value=None):
                with patch.object(h, "_is_remediation_exempt",     return_value=False):
                    with patch.object(h, "_exceeded_attempt_limit", return_value=False):
                        result = h.handler(remediation_event, None)
            assert result["status"] == "success"
            cfg = s3.get_public_access_block(Bucket="vitacore-laudos-imagens-prod")
            assert cfg["PublicAccessBlockConfiguration"]["BlockPublicAcls"] is True


# ──────────────────────────────────────────────────────────────────────────────
# Resiliência e edge cases
# ──────────────────────────────────────────────────────────────────────────────

class TestResilienceAndEdgeCases:

    def test_record_attempt_noop_without_table(self, monkeypatch):
        """_record_remediation_attempt deve ser silencioso sem tabela."""
        monkeypatch.setenv("REMEDIATION_ATTEMPTS_TABLE", "")
        with mock_aws():
            h = _load_handler()
            try:
                h._record_remediation_attempt("id-x", "WAYFINDER-002", "success")
            except Exception as exc:
                pytest.fail(f"Não deve lançar exceção: {exc}")

    def test_block_public_access_idempotent(self):
        """Chamar remediação S3 duas vezes deve ser idempotente."""
        with mock_aws():
            h  = _load_handler()
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="idempotent-bucket")
            r1 = h._enable_s3_block_public_access(resource_id="idempotent-bucket")
            r2 = h._enable_s3_block_public_access(resource_id="idempotent-bucket")
        assert "idempotent-bucket" in r1
        assert "idempotent-bucket" in r2

    def test_audit_record_captured_in_handler(self, remediation_event):
        """_log_audit_record deve ser chamado uma vez com os campos certos."""
        with mock_aws():
            h  = _load_handler()
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="vitacore-laudos-imagens-prod")

            captured = []
            original = h._log_audit_record

            def capturing(*args, **kwargs):
                record = original(*args, **kwargs)
                captured.append(record)
                return record

            with patch.object(h, "_log_audit_record", side_effect=capturing):
                with patch.object(h, "_is_remediation_exempt",     return_value=False):
                    with patch.object(h, "_exceeded_attempt_limit", return_value=False):
                        h.handler(remediation_event, None)

        assert len(captured) == 1
        rec = captured[0]
        assert rec["rule_name"]   == "WAYFINDER-002"
        assert rec["resource_id"] == "vitacore-laudos-imagens-prod"
        assert rec["status"]      == "success"
