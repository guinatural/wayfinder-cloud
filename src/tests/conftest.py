"""
conftest.py  Fixtures compartilhadas para todos os testes do Wayfinder Cloud.
Usa moto para mockar chamadas AWS sem custo real.
"""

import json
import os
import pytest
import boto3
from moto import mock_aws


#  Variáveis de ambiente para os testes 

@pytest.fixture(autouse=True)
def aws_env_vars(monkeypatch):
    """Define variáveis de ambiente necessárias para todas as Lambdas."""
    monkeypatch.setenv("AWS_DEFAULT_REGION",      "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID",        "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY",    "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN",       "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN",        "testing")
    monkeypatch.setenv("ENVIRONMENT",             "test")
    monkeypatch.setenv("CRITICAL_TOPIC_ARN",      "arn:aws:sns:us-east-1:123456789012:wayfinder-test-critical")
    monkeypatch.setenv("WARNING_TOPIC_ARN",       "arn:aws:sns:us-east-1:123456789012:wayfinder-test-warning")
    monkeypatch.setenv("INFO_TOPIC_ARN",          "arn:aws:sns:us-east-1:123456789012:wayfinder-test-info")
    monkeypatch.setenv("WAYFINDER_EVENT_BUS_NAME","wayfinder-events")
    monkeypatch.setenv("AUDIT_BUCKET_NAME",       "wayfinder-test-audit")
    monkeypatch.setenv("ATHENA_WORKGROUP",        "wayfinder-audit")
    monkeypatch.setenv("ATHENA_DATABASE",         "wayfinder_audit")
    monkeypatch.setenv("REMEDIATION_ATTEMPTS_TABLE", "wayfinder-test-remediation-attempts")


@pytest.fixture
def mock_aws_services():
    """Inicia mocks do moto para serviços AWS comuns nos testes."""
    with mock_aws():
        yield


@pytest.fixture
def sns_topics(mock_aws_services):
    """Cria os SNS topics necessários para os testes."""
    sns = boto3.client("sns", region_name="us-east-1")
    critical = sns.create_topic(Name="wayfinder-test-critical")
    warning  = sns.create_topic(Name="wayfinder-test-warning")
    info     = sns.create_topic(Name="wayfinder-test-info")
    return {
        "critical": critical["TopicArn"],
        "warning":  warning["TopicArn"],
        "info":     info["TopicArn"],
    }


@pytest.fixture
def s3_audit_bucket(mock_aws_services):
    """Cria o bucket S3 de auditoria para os testes."""
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="wayfinder-test-audit")
    return "wayfinder-test-audit"


@pytest.fixture
def dynamodb_guardrail_table(mock_aws_services):
    """Cria a tabela DynamoDB de guardrail para os testes."""
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = dynamodb.create_table(
        TableName="wayfinder-test-remediation-attempts",
        AttributeDefinitions=[
            {"AttributeName": "resource_id", "AttributeType": "S"},
            {"AttributeName": "rule_name",   "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "resource_id", "KeyType": "HASH"},
            {"AttributeName": "rule_name",   "KeyType": "RANGE"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    return table


#  Eventos de teste 

@pytest.fixture
def config_noncompliant_event():
    """Evento EventBridge simulando Config NON_COMPLIANT para WAYFINDER-002 (S3 público)."""
    return {
        "version":     "0",
        "id":          "test-event-id",
        "source":      "aws.config",
        "account":     "123456789012",
        "region":      "us-east-1",
        "detail-type": "Config Rules Compliance Change",
        "detail": {
            "configRuleName":  "wayfinder-dev-WAYFINDER-002",
            "resourceType":    "AWS::S3::Bucket",
            "resourceId":      "vitacore-laudos-imagens-prod",
            "awsAccountId":    "123456789012",
            "awsRegion":       "us-east-1",
            "newEvaluationResult": {
                "complianceType":      "NON_COMPLIANT",
                "resultRecordedTime":  "2026-08-21T14:32:00Z",
            },
        },
    }


@pytest.fixture
def guardduty_finding_event():
    """Evento EventBridge simulando GuardDuty finding HIGH."""
    return {
        "source":      "aws.guardduty",
        "detail-type": "GuardDuty Finding",
        "detail": {
            "schemaVersion": "2.0",
            "accountId":     "123456789012",
            "region":        "us-east-1",
            "type":          "UnauthorizedAccess:S3/MaliciousIPCaller",
            "severity":      7.0,
            "title":         "S3 bucket accessed from malicious IP address",
            "description":   "S3 bucket vitacore-laudos-imagens-prod accessed from suspicious IP",
            "resource": {
                "resourceType": "S3Bucket",
                "s3BucketDetails": [{
                    "name": "vitacore-laudos-imagens-prod",
                    "type": "Destination",
                }],
            },
            "service": {
                "action": {
                    "actionType": "AWS_API_CALL",
                    "awsApiCallAction": {"api": "GetObject"},
                },
                "eventFirstSeen": "2026-08-21T14:30:00Z",
                "eventLastSeen":  "2026-08-21T14:32:00Z",
            },
        },
    }
