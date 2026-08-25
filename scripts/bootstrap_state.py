#!/usr/bin/env python3
"""
bootstrap_state.py  Wayfinder Cloud
Cria o bucket S3 e a tabela DynamoDB para o Terraform remote state.

Este script deve ser executado UMA VEZ por ambiente antes do primeiro
'terraform init'. Os recursos criados aqui NÃO são gerenciados pelo
Terraform (para evitar o paradoxo do bootstrap).

Uso:
    python scripts/bootstrap_state.py --env dev --region us-east-1
    python scripts/bootstrap_state.py --env prod --region us-east-1

Pré-requisitos:
    - AWS CLI configurado com profile wayfinder-{env}
    - Python 3.8+
    - boto3 instalado: pip install boto3
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

import boto3
from botocore.exceptions import ClientError


#  Constantes 

PROJECT = "wayfinder-cloud"

STATE_BUCKET_PREFIX  = f"{PROJECT}-tfstate"
LOCK_TABLE_PREFIX    = f"{PROJECT}-tfstate-lock"


#  Helpers 

def log(msg: str, level: str = "INFO") -> None:
    symbols = {"INFO": "", "WARN": " ", "ERROR": "", "STEP": ""}
    print(f"  {symbols.get(level, ' ')} {msg}")


def confirm(prompt: str) -> bool:
    answer = input(f"\n{prompt} [y/N] ").strip().lower()
    return answer in ("y", "yes")


#  S3 State Bucket 

def create_state_bucket(s3: Any, bucket_name: str, region: str) -> None:
    """Cria o bucket S3 para o Terraform state com todas as proteções necessárias."""

    log(f"Criando bucket S3: {bucket_name}", "STEP")

    # Verificar se já existe
    try:
        s3.head_bucket(Bucket=bucket_name)
        log(f"Bucket {bucket_name} já existe  pulando criação")
        return
    except ClientError as e:
        if e.response["Error"]["Code"] not in ("404", "NoSuchBucket"):
            raise

    # Criar bucket
    kwargs: dict[str, Any] = {"Bucket": bucket_name}
    if region != "us-east-1":
        kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}

    s3.create_bucket(**kwargs)
    log(f"Bucket {bucket_name} criado")
    time.sleep(2)  # Propagação

    # Versionamento (obrigatório para state lock e recuperação)
    s3.put_bucket_versioning(
        Bucket=bucket_name,
        VersioningConfiguration={"Status": "Enabled"},
    )
    log("Versionamento habilitado")

    # Bloquear acesso público
    s3.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls":       True,
            "IgnorePublicAcls":      True,
            "BlockPublicPolicy":     True,
            "RestrictPublicBuckets": True,
        },
    )
    log("Block Public Access habilitado")

    # Criptografia SSE-S3 (state file não é dado de saúde  SSE-S3 é suficiente)
    s3.put_bucket_encryption(
        Bucket=bucket_name,
        ServerSideEncryptionConfiguration={
            "Rules": [{
                "ApplyServerSideEncryptionByDefault": {
                    "SSEAlgorithm": "AES256"
                },
                "BucketKeyEnabled": True,
            }]
        },
    )
    log("Criptografia SSE-AES256 habilitada")

    # Policy: forçar HTTPS e bloquear delete de objetos com versão
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid":    "DenyNonTLS",
                "Effect": "Deny",
                "Principal": "*",
                "Action":   "s3:*",
                "Resource": [f"arn:aws:s3:::{bucket_name}", f"arn:aws:s3:::{bucket_name}/*"],
                "Condition": {"Bool": {"aws:SecureTransport": "false"}},
            },
            {
                "Sid":    "DenyPermanentDelete",
                "Effect": "Deny",
                "Principal": "*",
                "Action":   "s3:DeleteObjectVersion",
                "Resource": f"arn:aws:s3:::{bucket_name}/*",
            },
        ],
    }
    s3.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(policy))
    log("Bucket policy de segurança aplicada (HTTPS obrigatório, delete versão bloqueado)")

    # Tags
    s3.put_bucket_tagging(
        Bucket=bucket_name,
        Tagging={
            "TagSet": [
                {"Key": "Project",            "Value": PROJECT},
                {"Key": "Purpose",            "Value": "terraform-state"},
                {"Key": "ManagedBy",          "Value": "bootstrap-script"},
                {"Key": "DataClassification", "Value": "operational"},
            ]
        },
    )
    log("Tags aplicadas")
    log(f"Bucket {bucket_name} configurado com sucesso")


#  DynamoDB Lock Table 

def create_lock_table(dynamodb: Any, table_name: str, region: str) -> None:
    """Cria a tabela DynamoDB para o Terraform state lock."""

    log(f"Criando tabela DynamoDB: {table_name}", "STEP")

    # Verificar se já existe
    try:
        dynamodb.describe_table(TableName=table_name)
        log(f"Tabela {table_name} já existe  pulando criação")
        return
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise

    # Criar tabela
    dynamodb.create_table(
        TableName=table_name,
        AttributeDefinitions=[
            {"AttributeName": "LockID", "AttributeType": "S"}
        ],
        KeySchema=[
            {"AttributeName": "LockID", "KeyType": "HASH"}
        ],
        BillingMode="PAY_PER_REQUEST",  # Sem provisionamento  lock é esporádico
        SSESpecification={
            "Enabled":     True,
            "SSEType":     "AES256",
        },
        Tags=[
            {"Key": "Project",   "Value": PROJECT},
            {"Key": "Purpose",   "Value": "terraform-state-lock"},
            {"Key": "ManagedBy", "Value": "bootstrap-script"},
        ],
    )
    log(f"Tabela {table_name} criada  aguardando ficar ACTIVE...")

    # Aguardar estar pronta
    waiter = dynamodb.get_waiter("table_exists")
    waiter.wait(TableName=table_name)
    log(f"Tabela {table_name} ACTIVE e pronta para uso")


#  Main 

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bootstrap do Terraform remote state para o Wayfinder Cloud"
    )
    parser.add_argument(
        "--env", required=True, choices=["dev", "staging", "prod"],
        help="Ambiente alvo (dev | staging | prod)"
    )
    parser.add_argument(
        "--region", default="us-east-1",
        help="Região AWS (padrão: us-east-1)"
    )
    parser.add_argument(
        "--profile", default=None,
        help="AWS CLI profile (padrão: wayfinder-{env})"
    )
    args = parser.parse_args()

    env     = args.env
    region  = args.region
    profile = args.profile or f"wayfinder-{env}"

    bucket_name = f"{STATE_BUCKET_PREFIX}-{env}"
    table_name  = LOCK_TABLE_PREFIX

    print(f"""

        Wayfinder Cloud  Bootstrap Terraform State          

  Ambiente : {env:<50}
  Região   : {region:<50}
  Profile  : {profile:<50}
  Bucket   : {bucket_name:<50}
  DynamoDB : {table_name:<50}

""")

    if env == "prod" and not confirm(
        "  Você está criando o state backend de PRODUÇÃO. Confirmar?"
    ):
        print("Operação cancelada.")
        sys.exit(0)

    # Inicializar clientes AWS
    session  = boto3.Session(profile_name=profile, region_name=region)
    s3       = session.client("s3")
    dynamodb = session.client("dynamodb")

    # Criar recursos
    create_state_bucket(s3, bucket_name, region)
    create_lock_table(dynamodb, table_name, region)

    print(f"""
 Bootstrap concluído com sucesso!

Próximos passos:
  1. Copie o tfvars de exemplo:
     cp infra/environments/{env}/terraform.tfvars.example \\
        infra/environments/{env}/terraform.tfvars

  2. Preencha o terraform.tfvars com seus valores

  3. Inicialize o Terraform:
     cd infra/environments/{env}
     terraform init
     terraform plan
     terraform apply

Backend configurado em:
  s3://{bucket_name}/{env}/terraform.tfstate
  DynamoDB: {table_name} (lock)
""")


if __name__ == "__main__":
    main()
