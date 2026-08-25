################################################################################
# Módulo: networking
# Responsabilidade: VPC, subnets, NAT, VPC Endpoints, Security Group para Lambdas
################################################################################

locals {
  name_prefix = "wayfinder-${var.environment}"
}

################################################################################
# VPC
################################################################################

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name        = "${local.name_prefix}-vpc"
    Environment = var.environment
  }
}

################################################################################
# Subnets privadas (Lambdas)
################################################################################

resource "aws_subnet" "private" {
  count             = length(var.azs)
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 1)
  availability_zone = var.azs[count.index]

  tags = {
    Name        = "${local.name_prefix}-private-${count.index + 1}"
    Tier        = "private"
    Environment = var.environment
  }
}

################################################################################
# Subnets públicas (NAT Gateway)
################################################################################

resource "aws_subnet" "public" {
  count                   = length(var.azs)
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index + 101)
  availability_zone       = var.azs[count.index]
  map_public_ip_on_launch = false

  tags = {
    Name        = "${local.name_prefix}-public-${count.index + 1}"
    Tier        = "public"
    Environment = var.environment
  }
}

################################################################################
# Internet Gateway
################################################################################

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name        = "${local.name_prefix}-igw"
    Environment = var.environment
  }
}

################################################################################
# NAT Gateway  single AZ em dev para economizar custo
################################################################################

resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = { Name = "${local.name_prefix}-nat-eip" }
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = {
    Name        = "${local.name_prefix}-nat-gw"
    Environment = var.environment
  }

  depends_on = [aws_internet_gateway.main]
}

################################################################################
# Route Tables
################################################################################

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "${local.name_prefix}-rt-public" }
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }

  tags = { Name = "${local.name_prefix}-rt-private" }
}

resource "aws_route_table_association" "private" {
  count          = length(aws_subnet.private)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

################################################################################
# Security Group  Lambdas (egress HTTPS only, sem ingress)
################################################################################

resource "aws_security_group" "lambda" {
  name        = "${local.name_prefix}-lambda-sg"
  description = "Permite apenas egress HTTPS para Lambdas do Wayfinder Cloud"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS para AWS APIs via VPC Endpoints ou NAT"
  }

  tags = {
    Name        = "${local.name_prefix}-lambda-sg"
    Environment = var.environment
  }
}

################################################################################
# VPC Endpoints  evita tráfego pelo internet para APIs AWS
################################################################################

# Gateway Endpoints (gratuitos)
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
  tags              = { Name = "${local.name_prefix}-vpce-s3" }
}

resource "aws_vpc_endpoint" "dynamodb" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.dynamodb"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
  tags              = { Name = "${local.name_prefix}-vpce-dynamodb" }
}

# Interface Endpoints (com custo, mas eliminam dependência do NAT para APIs críticas)
locals {
  interface_endpoints = {
    "config"      = "com.amazonaws.${var.region}.config"
    "cloudtrail"  = "com.amazonaws.${var.region}.cloudtrail"
    "logs"        = "com.amazonaws.${var.region}.logs"
    "monitoring"  = "com.amazonaws.${var.region}.monitoring"
    "kms"         = "com.amazonaws.${var.region}.kms"
    "sns"         = "com.amazonaws.${var.region}.sns"
    "sts"         = "com.amazonaws.${var.region}.sts"
    "events"      = "com.amazonaws.${var.region}.events"
    "lambda"      = "com.amazonaws.${var.region}.lambda"
  }
}

resource "aws_vpc_endpoint" "interface" {
  for_each = local.interface_endpoints

  vpc_id              = aws_vpc.main.id
  service_name        = each.value
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.lambda.id]
  private_dns_enabled = true

  tags = { Name = "${local.name_prefix}-vpce-${each.key}" }
}
