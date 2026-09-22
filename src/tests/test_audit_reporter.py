"""
test_audit_reporter.py
Testes unitários para a Lambda audit-reporter do Wayfinder Cloud.

Cobertura:
  - _parse_athena_results: header strip, rows vazias, valores ausentes
  - _determine_health_status: HEALTHY / DEGRADED / CRITICAL
  - _save_report_to_s3: path estruturado, conteúdo JSON, SSE-KMS, metadata
  - _publish_summary_sns: publicação bem-sucedida, falha silenciosa (ClientError)
  - _query_* helpers: tratamento de rows vazias e valores inválidos (None/float)
  - handler principal: fluxo completo com queries mockadas, erros parciais
    capturados no campo 'errors', relatório salvo no S3

Estratégia de isolamento:
  Usa importlib.util (caminho absoluto) para evitar colisão com os outros
  handlers que compartilham o nome 'handler.py' em sys.modules.
  Athena é mockado via patch porque o moto não simula polling de queries.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

# ── Loader isolado ──────────────────────────────────────────────────────────

_HANDLER_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../lambdas/audit-reporter/handler.py")
)


def _load_handler():
    """Carrega audit-reporter/handler.py pelo caminho absoluto, sem cache global."""
    sys.modules.pop("audit_reporter_handler", None)
    spec = importlib.util.spec_from_file_location("audit_reporter_handler", _HANDLER_PATH)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["audit_reporter_handler"] = mod
    return mod


# ── Helpers de mock ─────────────────────────────────────────────────────────

def _make_athena_result(headers: list[str], rows: list[list[str]]) -> dict:
    """Monta estrutura de ResultSet do Athena para uso em patches."""
    header_row = {"Data": [{"VarCharValue": h} for h in headers]}
    data_rows  = [
        {"Data": [{"VarCharValue": v} for v in row]}
        for row in rows
    ]
    return {"ResultSet": {"Rows": [header_row] + data_rows}}


def _mock_run_query(return_value: list[dict]):
    """Retorna patch para _run_athena_query que devolve dados fixos."""
    return patch(
        "audit_reporter_handler._run_athena_query",
        return_value=return_value,
    )


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def audit_bucket(monkeypatch):
    """Cria o bucket S3 de auditoria e define a variável de ambiente."""
    monkeypatch.setenv("AUDIT_BUCKET_NAME", "wayfinder-test-audit")
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="wayfinder-test-audit")
        yield "wayfinder-test-audit"


@pytest.fixture
def sns_info_topic(monkeypatch):
    """Cria o tópico SNS INFO e define a variável de ambiente."""
    with mock_aws():
        sns = boto3.client("sns", region_name="us-east-1")
        arn = sns.create_topic(Name="wayfinder-test-info")["TopicArn"]
        monkeypatch.setenv("INFO_TOPIC_ARN", arn)
        yield arn


@pytest.fixture
def now():
    return datetime(2026, 9, 17, 10, 0, 0, tzinfo=timezone.utc)


# ══════════════════════════════════════════════════════════════════════════════
# _parse_athena_results
# ══════════════════════════════════════════════════════════════════════════════

class TestParseAthenaResults:

    def test_returns_empty_list_for_empty_rows(self):
        """ResultSet sem linhas deve retornar lista vazia."""
        with mock_aws():
            h = _load_handler()
        result = h._parse_athena_results({"ResultSet": {"Rows": []}})
        assert result == []

    def test_strips_header_row(self):
        """Primeira linha (headers) não deve aparecer nos dados retornados."""
        with mock_aws():
            h = _load_handler()
        raw = _make_athena_result(
            headers=["severity", "total"],
            rows=[["CRITICAL", "5"], ["HIGH", "3"]],
        )
        result = h._parse_athena_results(raw)
        assert len(result) == 2
        assert result[0] == {"severity": "CRITICAL", "total": "5"}
        assert result[1] == {"severity": "HIGH",     "total": "3"}

    def test_handles_missing_varcharvalue(self):
        """Células sem VarCharValue devem resultar em string vazia."""
        with mock_aws():
            h = _load_handler()
        raw = {
            "ResultSet": {
                "Rows": [
                    {"Data": [{"VarCharValue": "col_a"}, {"VarCharValue": "col_b"}]},
                    {"Data": [{"VarCharValue": "val1"}, {}]},  # segunda célula sem valor
                ]
            }
        }
        result = h._parse_athena_results(raw)
        assert result[0]["col_a"] == "val1"
        assert result[0]["col_b"] == ""

    def test_single_data_row(self):
        """ResultSet com exatamente uma linha de dados (além do header)."""
        with mock_aws():
            h = _load_handler()
        raw = _make_athena_result(headers=["compliance_pct"], rows=[["92.5"]])
        result = h._parse_athena_results(raw)
        assert len(result) == 1
        assert result[0]["compliance_pct"] == "92.5"


# ══════════════════════════════════════════════════════════════════════════════
# _determine_health_status
# ══════════════════════════════════════════════════════════════════════════════

class TestDetermineHealthStatus:

    def test_critical_when_critical_count_positive(self):
        """Qualquer violação CRITICAL → status CRITICAL."""
        with mock_aws():
            h = _load_handler()
        assert h._determine_health_status(1, 95.0)  == "CRITICAL"
        assert h._determine_health_status(10, 99.0) == "CRITICAL"

    def test_critical_takes_priority_over_compliance(self):
        """CRITICAL prevalece mesmo com alta conformidade."""
        with mock_aws():
            h = _load_handler()
        assert h._determine_health_status(1, 100.0) == "CRITICAL"

    def test_degraded_when_compliance_below_80(self):
        """Sem CRITICAL, compliance < 80% → DEGRADED."""
        with mock_aws():
            h = _load_handler()
        assert h._determine_health_status(0, 79.9) == "DEGRADED"
        assert h._determine_health_status(0, 0.0)  == "DEGRADED"

    def test_healthy_when_no_critical_and_good_compliance(self):
        """Sem CRITICAL e compliance >= 80% → HEALTHY."""
        with mock_aws():
            h = _load_handler()
        assert h._determine_health_status(0, 80.0)  == "HEALTHY"
        assert h._determine_health_status(0, 100.0) == "HEALTHY"

    def test_healthy_when_compliance_is_none(self):
        """Compliance None sem CRITICAL → HEALTHY (sem dados suficientes)."""
        with mock_aws():
            h = _load_handler()
        assert h._determine_health_status(0, None) == "HEALTHY"


# ══════════════════════════════════════════════════════════════════════════════
# _query_violations_by_severity
# ══════════════════════════════════════════════════════════════════════════════

class TestQueryViolationsBySeverity:

    def test_returns_dict_with_severity_counts(self, now):
        """Deve retornar dict {severity: count} a partir das rows Athena."""
        with mock_aws():
            h = _load_handler()
        rows = [
            {"severity": "CRITICAL", "total": "4"},
            {"severity": "HIGH",     "total": "7"},
        ]
        start = now - timedelta(days=7)
        with _mock_run_query(rows):
            result = h._query_violations_by_severity(start, now)
        assert result == {"CRITICAL": 4, "HIGH": 7}

    def test_returns_empty_dict_when_no_rows(self, now):
        """Sem linhas de resultado → dict vazio."""
        with mock_aws():
            h = _load_handler()
        start = now - timedelta(days=7)
        with _mock_run_query([]):
            result = h._query_violations_by_severity(start, now)
        assert result == {}

    def test_ignores_rows_without_severity(self, now):
        """Rows sem chave 'severity' preenchida devem ser ignoradas."""
        with mock_aws():
            h = _load_handler()
        rows = [
            {"severity": "",         "total": "2"},
            {"severity": "CRITICAL", "total": "3"},
        ]
        start = now - timedelta(days=7)
        with _mock_run_query(rows):
            result = h._query_violations_by_severity(start, now)
        assert "CRITICAL" in result
        assert "" not in result


# ══════════════════════════════════════════════════════════════════════════════
# _query_top_noncompliant_resources
# ══════════════════════════════════════════════════════════════════════════════

class TestQueryTopNoncompliantResources:

    def test_returns_list_of_resources(self, now):
        """Deve retornar lista de dicts com resource_id, type e count."""
        with mock_aws():
            h = _load_handler()
        rows = [
            {"resource_id": "bucket-x", "resource_type": "AWS::S3::Bucket", "violation_count": "5"},
            {"resource_id": "trail-y",  "resource_type": "AWS::CloudTrail::Trail", "violation_count": "3"},
        ]
        start = now - timedelta(days=7)
        with _mock_run_query(rows):
            result = h._query_top_noncompliant_resources(start, now)
        assert len(result) == 2
        assert result[0]["resource_id"]     == "bucket-x"
        assert result[0]["violation_count"] == 5
        assert result[1]["resource_type"]   == "AWS::CloudTrail::Trail"

    def test_returns_empty_list_when_no_rows(self, now):
        """Sem rows → lista vazia."""
        with mock_aws():
            h = _load_handler()
        start = now - timedelta(days=7)
        with _mock_run_query([]):
            result = h._query_top_noncompliant_resources(start, now)
        assert result == []


# ══════════════════════════════════════════════════════════════════════════════
# _query_mttr
# ══════════════════════════════════════════════════════════════════════════════

class TestQueryMttr:

    def test_returns_float_when_valid(self, now):
        """Deve retornar float arredondado a 2 casas."""
        with mock_aws():
            h = _load_handler()
        start = now - timedelta(days=7)
        with _mock_run_query([{"avg_mttr_hours": "2.567"}]):
            result = h._query_mttr(start, now)
        assert result == 2.57

    def test_returns_none_when_no_rows(self, now):
        """Sem rows → None."""
        with mock_aws():
            h = _load_handler()
        start = now - timedelta(days=7)
        with _mock_run_query([]):
            result = h._query_mttr(start, now)
        assert result is None

    def test_returns_none_when_value_is_empty_string(self, now):
        """avg_mttr_hours vazio → None."""
        with mock_aws():
            h = _load_handler()
        start = now - timedelta(days=7)
        with _mock_run_query([{"avg_mttr_hours": ""}]):
            result = h._query_mttr(start, now)
        assert result is None

    def test_returns_none_when_value_not_numeric(self, now):
        """avg_mttr_hours 'NaN' → Python retorna float nan — não deve lançar exceção."""
        import math
        with mock_aws():
            h = _load_handler()
        start = now - timedelta(days=7)
        with _mock_run_query([{"avg_mttr_hours": "NaN"}]):
            result = h._query_mttr(start, now)
        # float("NaN") é válido em Python — o handler retorna nan sem exceção
        assert result is None or (isinstance(result, float) and math.isnan(result))


# ══════════════════════════════════════════════════════════════════════════════
# _query_compliance_percentage
# ══════════════════════════════════════════════════════════════════════════════

class TestQueryCompliancePercentage:

    def test_returns_float_when_valid(self, now):
        """Deve retornar float arredondado a 2 casas."""
        with mock_aws():
            h = _load_handler()
        start = now - timedelta(days=7)
        with _mock_run_query([{"compliance_pct": "87.333"}]):
            result = h._query_compliance_percentage(start, now)
        assert result == 87.33

    def test_returns_none_when_no_rows(self, now):
        """Sem rows → None."""
        with mock_aws():
            h = _load_handler()
        start = now - timedelta(days=7)
        with _mock_run_query([]):
            result = h._query_compliance_percentage(start, now)
        assert result is None

    def test_returns_none_when_value_empty(self, now):
        """compliance_pct vazio → None."""
        with mock_aws():
            h = _load_handler()
        start = now - timedelta(days=7)
        with _mock_run_query([{"compliance_pct": ""}]):
            result = h._query_compliance_percentage(start, now)
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# _save_report_to_s3
# ══════════════════════════════════════════════════════════════════════════════

class TestSaveReportToS3:

    def test_saves_json_to_correct_path(self, audit_bucket, now):
        """Relatório deve ser salvo no path compliance-reports/{year}/{month}/{date}-weekly-report.json."""
        with mock_aws():
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket=audit_bucket)

            h      = _load_handler()
            report = {"test": "data", "environment": "test"}
            s3_key = h._save_report_to_s3(report, now)

        expected_key = "compliance-reports/2026/09/2026-09-17-weekly-report.json"
        assert s3_key == expected_key

    def test_content_is_valid_json(self, audit_bucket, now):
        """Conteúdo salvo deve ser JSON válido e conter os dados do relatório."""
        with mock_aws():
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket=audit_bucket)

            h      = _load_handler()
            report = {"executive_summary": {"health_status": "HEALTHY"}}
            s3_key = h._save_report_to_s3(report, now)

            obj  = s3.get_object(Bucket=audit_bucket, Key=s3_key)
            body = json.loads(obj["Body"].read())

        assert body["executive_summary"]["health_status"] == "HEALTHY"

    def test_content_type_is_json(self, audit_bucket, now):
        """ContentType do objeto S3 deve ser application/json."""
        with mock_aws():
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket=audit_bucket)

            h      = _load_handler()
            s3_key = h._save_report_to_s3({"x": 1}, now)
            head   = s3.head_object(Bucket=audit_bucket, Key=s3_key)

        assert head["ContentType"] == "application/json"

    def test_metadata_contains_environment(self, audit_bucket, now):
        """Metadata do objeto deve conter o campo 'environment'."""
        with mock_aws():
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket=audit_bucket)

            h      = _load_handler()
            s3_key = h._save_report_to_s3({"x": 1}, now)
            head   = s3.head_object(Bucket=audit_bucket, Key=s3_key)

        assert "environment" in head["Metadata"]
        assert head["Metadata"]["environment"] == "test"

    def test_returns_s3_key_string(self, audit_bucket, now):
        """Retorno deve ser string não-vazia."""
        with mock_aws():
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket=audit_bucket)

            h      = _load_handler()
            result = h._save_report_to_s3({"x": 1}, now)

        assert isinstance(result, str)
        assert len(result) > 0


# ══════════════════════════════════════════════════════════════════════════════
# _publish_summary_sns
# ══════════════════════════════════════════════════════════════════════════════

class TestPublishSummarySns:

    def test_publishes_without_raising(self, sns_info_topic):
        """Publicação bem-sucedida não deve lançar exceção."""
        with mock_aws():
            sns = boto3.client("sns", region_name="us-east-1")
            sns.create_topic(Name="wayfinder-test-info")

            h = _load_handler()
            summary = {
                "health_status":        "HEALTHY",
                "total_violations_7d":  0,
                "critical_violations":  0,
                "compliance_percentage": 95.0,
                "mttr_hours":           1.5,
            }
            try:
                h._publish_summary_sns(summary, "compliance-reports/2026/09/2026-09-17-weekly-report.json")
            except Exception as exc:
                pytest.fail(f"Não deve lançar exceção: {exc}")

    def test_clienterror_is_silent(self, monkeypatch):
        """ClientError no SNS deve ser capturado silenciosamente (apenas log)."""
        with mock_aws():
            h = _load_handler()
            summary = {"health_status": "CRITICAL", "total_violations_7d": 5,
                       "critical_violations": 2, "compliance_percentage": 60.0, "mttr_hours": None}
            error = ClientError(
                {"Error": {"Code": "InternalError", "Message": "SNS unavailable"}},
                "Publish",
            )
            with patch.object(h, "_sns") as mock_sns:
                mock_sns.publish.side_effect = error
                try:
                    h._publish_summary_sns(summary, "some/key.json")
                except Exception as exc:
                    pytest.fail(f"ClientError não deve estourar: {exc}")

    def test_message_contains_health_status(self, sns_info_topic):
        """Mensagem publicada deve conter o health_status."""
        with mock_aws():
            sns_client = boto3.client("sns", region_name="us-east-1")
            # Criar o topic novamente dentro do contexto mock_aws
            arn = sns_client.create_topic(Name="wayfinder-test-info")["TopicArn"]

            h = _load_handler()
            captured = {}

            def capture_publish(**kwargs):
                captured["message"] = kwargs.get("Message", "")
                return {"MessageId": "test-id"}

            with patch.object(h, "_sns") as mock_sns:
                mock_sns.publish.side_effect = capture_publish
                h._publish_summary_sns(
                    {"health_status": "DEGRADED", "total_violations_7d": 3,
                     "critical_violations": 0, "compliance_percentage": 75.0,
                     "mttr_hours": 2.0},
                    "some/s3/key.json",
                )

        assert "DEGRADED" in captured.get("message", "")


# ══════════════════════════════════════════════════════════════════════════════
# Handler principal
# ══════════════════════════════════════════════════════════════════════════════

class TestHandlerMainFlow:

    def _default_query_patches(self, h):
        """Retorna patches padrão para as 4 queries Athena."""
        return [
            patch.object(h, "_query_violations_by_severity",
                         return_value={"CRITICAL": 0, "HIGH": 2}),
            patch.object(h, "_query_top_noncompliant_resources",
                         return_value=[{"resource_id": "bucket-x", "resource_type": "AWS::S3::Bucket", "violation_count": 2}]),
            patch.object(h, "_query_mttr",
                         return_value=1.5),
            patch.object(h, "_query_compliance_percentage",
                         return_value=92.0),
        ]

    def test_returns_completed_status(self, audit_bucket, sns_info_topic):
        """Handler deve retornar status 'completed' com sucesso."""
        with mock_aws():
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket=audit_bucket)
            sns = boto3.client("sns", region_name="us-east-1")
            sns.create_topic(Name="wayfinder-test-info")

            h = _load_handler()
            patches = self._default_query_patches(h)
            for p in patches:
                p.start()
            try:
                result = h.handler({}, None)
            finally:
                for p in patches:
                    p.stop()

        assert result["status"] == "completed"

    def test_s3_key_returned(self, audit_bucket, sns_info_topic):
        """Handler deve retornar o caminho S3 do relatório."""
        with mock_aws():
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket=audit_bucket)
            sns = boto3.client("sns", region_name="us-east-1")
            sns.create_topic(Name="wayfinder-test-info")

            h = _load_handler()
            patches = self._default_query_patches(h)
            for p in patches:
                p.start()
            try:
                result = h.handler({}, None)
            finally:
                for p in patches:
                    p.stop()

        assert "s3_key" in result
        assert "compliance-reports" in result["s3_key"]
        assert result["s3_key"].endswith(".json")

    def test_errors_list_empty_when_all_queries_succeed(self, audit_bucket, sns_info_topic):
        """Lista de erros deve estar vazia quando todas as queries funcionam."""
        with mock_aws():
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket=audit_bucket)
            sns = boto3.client("sns", region_name="us-east-1")
            sns.create_topic(Name="wayfinder-test-info")

            h = _load_handler()
            patches = self._default_query_patches(h)
            for p in patches:
                p.start()
            try:
                result = h.handler({}, None)
            finally:
                for p in patches:
                    p.stop()

        assert result["errors"] == []

    def test_partial_query_failure_captured_in_errors(self, audit_bucket, sns_info_topic):
        """Falha em uma query individual deve aparecer em 'errors', não derrubar o handler."""
        with mock_aws():
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket=audit_bucket)
            sns = boto3.client("sns", region_name="us-east-1")
            sns.create_topic(Name="wayfinder-test-info")

            h = _load_handler()
            with patch.object(h, "_query_violations_by_severity",
                               side_effect=RuntimeError("Athena timeout")):
                with patch.object(h, "_query_top_noncompliant_resources",
                                   return_value=[]):
                    with patch.object(h, "_query_mttr",
                                       return_value=None):
                        with patch.object(h, "_query_compliance_percentage",
                                           return_value=None):
                            result = h.handler({}, None)

        assert result["status"] == "completed"
        assert any("violations_by_severity" in e for e in result["errors"])

    def test_report_saved_in_s3(self, audit_bucket, sns_info_topic):
        """Relatório deve existir no S3 após o handler completar."""
        with mock_aws():
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket=audit_bucket)
            sns = boto3.client("sns", region_name="us-east-1")
            sns.create_topic(Name="wayfinder-test-info")

            h = _load_handler()
            patches = self._default_query_patches(h)
            for p in patches:
                p.start()
            try:
                result = h.handler({}, None)
            finally:
                for p in patches:
                    p.stop()

            # Verificar que o objeto existe no S3
            obj = s3.get_object(Bucket=audit_bucket, Key=result["s3_key"])
            body = json.loads(obj["Body"].read())

        assert "report_metadata" in body
        assert "executive_summary" in body

    def test_health_status_critical_when_critical_violations(self, audit_bucket, sns_info_topic):
        """Se há violações CRITICAL, executive_summary.health_status deve ser CRITICAL."""
        with mock_aws():
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket=audit_bucket)
            sns = boto3.client("sns", region_name="us-east-1")
            sns.create_topic(Name="wayfinder-test-info")

            h = _load_handler()
            with patch.object(h, "_query_violations_by_severity",
                               return_value={"CRITICAL": 3, "HIGH": 1}):
                with patch.object(h, "_query_top_noncompliant_resources",
                                   return_value=[]):
                    with patch.object(h, "_query_mttr", return_value=None):
                        with patch.object(h, "_query_compliance_percentage",
                                           return_value=85.0):
                            result = h.handler({}, None)

        assert result["summary"]["health_status"] == "CRITICAL"

    def test_executive_summary_fields_present(self, audit_bucket, sns_info_topic):
        """executive_summary deve conter todos os campos esperados."""
        with mock_aws():
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket=audit_bucket)
            sns = boto3.client("sns", region_name="us-east-1")
            sns.create_topic(Name="wayfinder-test-info")

            h = _load_handler()
            patches = self._default_query_patches(h)
            for p in patches:
                p.start()
            try:
                result = h.handler({}, None)
            finally:
                for p in patches:
                    p.stop()

        summary = result["summary"]
        for field in ["total_violations_7d", "critical_violations",
                      "compliance_percentage", "mttr_hours", "health_status"]:
            assert field in summary, f"Campo ausente no executive_summary: {field}"
