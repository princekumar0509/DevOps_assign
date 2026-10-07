# DynamoDB & RDS - Database Services

> Session 18 - Terraform & IaC | Task 2: AWS Services Research

AWS offers purpose-built databases rather than one engine for everything. This document covers the two most widely used: **Amazon DynamoDB**, a serverless NoSQL key-value and document database, and **Amazon RDS**, a managed relational database service.

## Why it matters for DevOps

Databases are the most stateful - and therefore riskiest - part of any infrastructure. DevOps engineers decide where data lives, how it is backed up, how it survives an Availability Zone failure, how credentials are handled and how capacity scales. Declaring tables, DB instances, subnet groups, backup retention and encryption in Terraform makes those decisions explicit and reviewable, and features such as deletion protection and final snapshots guard against an accidental `terraform destroy`.

## DynamoDB

### NoSQL

Amazon DynamoDB is a fully managed, **serverless NoSQL** database: there are no servers, patches or storage volumes to manage, data is automatically replicated across three AZs in a Region, and key-based reads and writes return in single-digit milliseconds at virtually any scale. Applications use the DynamoDB API (`PutItem`, `GetItem`, `Query`, `Scan`, ...) or PartiQL, a SQL-compatible query language. Unlike a relational database, only the primary key is fixed, there are no joins, and data is modelled around the application's **access patterns** (often denormalised) so that each request is a cheap key lookup.

### Tables

A **table** is a collection of items, created with a name, a primary key schema and a capacity mode. There is no practical limit on table size, encryption at rest is always on (AWS owned key by default, or an AWS managed / customer managed KMS key), and the default quota is 2,500 tables per Region.

### Items

An **item** is a single record identified uniquely by its primary key - comparable to a row. The maximum item size is **400 KB**, including attribute names. Items are written with `PutItem`/`UpdateItem`, read with `GetItem`/`Query`, and can be grouped in batch operations or ACID transactions (up to 100 items).

### Attributes

An **attribute** is a name-value pair within an item - comparable to a column, except that different items can have different attributes. Only key attributes are declared when the table is created.

| Category | Types |
|---|---|
| Scalar | String (`S`), Number (`N`), Binary (`B`), Boolean (`BOOL`), Null (`NULL`) |
| Document | Map (`M`), List (`L`) - nesting up to 32 levels |
| Set | String set (`SS`), Number set (`NS`), Binary set (`BS`) |

### Partition key

The **partition key** (also called the hash key) is mandatory. DynamoDB hashes its value to decide which physical partition stores the item. With a partition key alone (a *simple* primary key), each value identifies exactly one item. Good partition keys have high cardinality and evenly distributed traffic (e.g. `StudentId`, `UserId`); low-cardinality keys such as `Status` create "hot" partitions that throttle.

### Sort key

The optional **sort key** (range key) combines with the partition key to form a *composite* primary key. Items sharing a partition key are stored together, ordered by sort key, so a single `Query` can return a whole group and filter it with `=`, `<`, `>`, `BETWEEN` or `begins_with`.

### Example table design: student enrolments

Table `StudentEnrolments` - partition key `StudentId`, sort key `CourseId`:

| StudentId (PK) | CourseId (SK) | CourseName | Semester | Grade | EnrolledAt |
|---|---|---|---|---|---|
| S1001 | AWS301 | AWS Architecture | 2026-FALL | | 2026-08-04T11:20:00Z |
| S1001 | DEVOPS101 | DevOps Foundations | 2026-FALL | A | 2026-08-01T10:15:00Z |
| S1001 | TF201 | Terraform and IaC | 2026-FALL | | 2026-08-03T09:00:00Z |
| S1002 | DEVOPS101 | DevOps Foundations | 2026-FALL | B+ | 2026-08-02T14:30:00Z |
| S1003 | TF201 | Terraform and IaC | 2027-SPRING | | 2026-12-15T08:45:00Z |

Empty `Grade` cells mean the attribute is simply absent from that item. The design serves these access patterns:

| Access pattern | Operation |
|---|---|
| All courses for student S1001 | `Query` where `StudentId = "S1001"` (returned in `CourseId` order) |
| One specific enrolment | `GetItem` with `StudentId = "S1001"` and `CourseId = "TF201"` |
| S1001's Terraform courses | `Query` where `StudentId = "S1001"` and `begins_with(CourseId, "TF")` |
| All students in DEVOPS101 | `Query` on GSI `CourseIndex` (PK `CourseId`, SK `StudentId`) |
| S1001's enrolments by date | `Query` on LSI `EnrolledAtIndex` (PK `StudentId`, SK `EnrolledAt`) |

Reads are eventually consistent by default; strongly consistent reads can be requested on the table and on LSIs (not on GSIs).

### Capacity modes

| | On-demand (default, recommended for most workloads) | Provisioned |
|---|---|---|
| Billing | Per request (read and write request units) | Per hour for the RCU/WCU provisioned, whether used or not |
| Scaling | Automatic, no capacity planning | Fixed values, optionally adjusted by auto scaling |
| Cost control | Optional maximum throughput per table or GSI | Predictable; reserved capacity discounts available |
| Best for | New, spiky or unpredictable traffic | Steady, forecastable traffic |

One **RCU** = one strongly consistent read per second (or two eventually consistent reads) of up to 4 KB; one **WCU** = one write per second of up to 1 KB; transactional requests consume twice as much. For example, reading a 6 KB item costs 2 RCU strongly consistent or 1 RCU eventually consistent, and writing a 2.5 KB item costs 3 WCU. A table can switch from provisioned to on-demand up to four times per rolling 24 hours, and from on-demand to provisioned at any time.

### Secondary indexes (GSI and LSI)

| | Global secondary index (GSI) | Local secondary index (LSI) |
|---|---|---|
| Key | Any partition key and optional sort key | Same partition key as the table, different sort key |
| Created | At any time | Only when the table is created |
| Quota per table | 20 (default) | 5 |
| Read consistency | Eventually consistent only | Eventual or strong |
| Capacity | Separate from the table | Shared with the table |
| Size limit | None | 10 GB per partition key value |

Each index *projects* `KEYS_ONLY`, `INCLUDE` (selected attributes) or `ALL` attributes.

### DynamoDB use cases

- Serverless backends (API Gateway + Lambda) and microservice data stores with known access patterns.
- Session stores, shopping carts, user profiles and feature flags.
- Gaming leaderboards, IoT and event data (with TTL to expire old items automatically).
- Event-driven pipelines using DynamoDB Streams; multi-Region active-active apps with global tables.
- Terraform state locking in older setups - the S3 backend's DynamoDB locking is now deprecated in favour of `use_lockfile`.

## RDS

### Relational database

A relational database stores data in **tables with a fixed schema** (typed columns, rows, primary and foreign keys), is queried with **SQL** including joins and aggregations, and guarantees **ACID** transactions. Amazon RDS runs these engines as a managed service: AWS provisions the hardware, patches the OS and engine, takes backups and handles failover, while the customer manages schema design, queries, indexes, parameters and database users.

### Supported engines

| Engine | Notes |
|---|---|
| MySQL, PostgreSQL, MariaDB | Open-source engines; no licence cost |
| Oracle | BYOL, or License Included for Standard Edition 2 |
| Microsoft SQL Server | Express, Web, Standard and Enterprise editions, License Included |
| IBM Db2 | Standard and Advanced editions; IBM licence via BYOL or AWS Marketplace |
| Amazon Aurora (MySQL- and PostgreSQL-compatible) | AWS-built engine managed through RDS; storage replicated six ways across three AZs, up to 15 low-lag replicas, Aurora Serverless v2 |

### DB instances

A **DB instance** is an isolated database environment running one engine, reached through a DNS **endpoint** and port. Its compute is defined by the **DB instance class**, named like EC2 types with a `db.` prefix:

| Class family | Examples | Typical use |
|---|---|---|
| Burstable | `db.t4g.micro`, `db.t4g.medium` | Dev/test, small workloads |
| General purpose | `db.m7g.large`, `db.m8g.xlarge` | Most production OLTP workloads |
| Memory optimized | `db.r7g.large`, `db.r8g.2xlarge`, `db.x2iedn` | Large working sets, heavy caching |

Storage is EBS-based: `gp3`, `io2` Block Express, `io1`, `gp2` (and legacy magnetic), up to 64 TiB for most engines, with optional **storage autoscaling**. Engine settings live in **parameter groups**, and optional features (for Oracle and SQL Server) in **option groups**.

### Security

| Layer | Control |
|---|---|
| Network | DB instance placed in private subnets via a **DB subnet group** spanning at least two AZs; `PubliclyAccessible = false` |
| Firewall | **Security group** allowing only the engine port (e.g. 5432) from the application's security group |
| Encryption at rest | **AWS KMS** encryption of storage, snapshots, automated backups and replicas; chosen at creation - an unencrypted instance is encrypted by restoring from an encrypted snapshot copy |
| Encryption in transit | **TLS** connections; enforce with `rds.force_ssl` (PostgreSQL) or `require_secure_transport` (MySQL/MariaDB) |
| Authentication | Database users, **IAM database authentication** (MariaDB, MySQL, PostgreSQL; tokens valid 15 minutes) or Kerberos for supported engines |
| Credentials | Master password managed and rotated in **AWS Secrets Manager** (`manage_master_user_password`) |
| Safety and audit | Deletion protection, CloudTrail for API calls, engine logs exported to CloudWatch Logs |

### Backups

| Type | How it works | Retention |
|---|---|---|
| Automated backups | Daily storage snapshot during the backup window plus transaction logs uploaded about every 5 minutes | 0-35 days (0 disables them) |
| Point-in-time recovery (PITR) | Restore to any second within the retention period, typically up to the last 5 minutes | Within the automated backup window |
| Manual snapshots | Taken on demand (or by AWS Backup); can be copied across Regions and shared with other accounts | Until explicitly deleted |

A restore always creates a **new DB instance** with a new endpoint. A final snapshot should be taken on deletion, and automated backups are removed with the instance unless explicitly retained. Multi-AZ instance deployments take backups from the standby to avoid I/O suspension on the primary.

### Multi-AZ deployments

```text
Multi-AZ DB instance: [Primary AZ-a] ==sync==>      [Standby AZ-b]                 (not readable)
Multi-AZ DB cluster : [Writer  AZ-a] ==semi-sync==> [Reader AZ-b] + [Reader AZ-c]  (readable)
Read replica        : [Primary]      --async-->     [Replica, same/other Region]   (own endpoint)
```

| | Multi-AZ DB instance deployment | Multi-AZ DB cluster deployment |
|---|---|---|
| Topology | Primary + one standby in another AZ | One writer + two readable reader instances in three AZs |
| Replication | Synchronous | Semisynchronous (at least one reader must acknowledge each commit) |
| Standby usable for reads | No | Yes, through the reader endpoint |
| Failover | Automatic; typically 60-120 seconds; the endpoint's DNS record moves to the standby | Automatic to the reader with the most recent changes; lower write latency and faster failover |
| Engines | MariaDB, MySQL, Oracle, PostgreSQL, SQL Server, Db2 | MySQL and PostgreSQL |

Failover is triggered by host, storage or network failure on the primary, an AZ disruption, some OS patching and instance modifications, or a manual "reboot with failover". Applications should reconnect using the endpoint and keep DNS caching short (60 seconds or less).

### Read replicas

- Read-only copies kept up to date by **asynchronous** engine-native replication, so they can lag behind the primary (`ReplicaLag` metric).
- Used to **scale reads** (reporting, analytics, read-heavy APIs); each replica has its own endpoint, so the application must route read traffic to it.
- Up to **15** replicas per source instance; the source must have automated backups enabled.
- Can be **cross-Region** for disaster recovery and lower latency for distant users, and can be **promoted** to a standalone instance (replication then stops).
- Not a substitute for Multi-AZ: a replica is not an automatic failover target. A replica can itself be Multi-AZ.

### RDS use cases

- OLTP backends for web and mobile applications (orders, payments, user accounts).
- Packaged software that requires a specific engine (WordPress on MySQL, ERP/CRM on Oracle or SQL Server).
- Lift-and-shift migrations of on-premises databases (often with AWS DMS).
- Reporting and BI queries offloaded to read replicas; multi-tenant SaaS on PostgreSQL.

## DynamoDB vs RDS

| Aspect | DynamoDB | RDS |
|---|---|---|
| Data model | Key-value and document (NoSQL) | Relational tables (SQL) |
| Schema | Flexible; only the primary key is fixed | Fixed schema with types and constraints |
| Querying | Key-based `GetItem`/`Query`, `Scan`, PartiQL; no joins | Full SQL with joins, aggregations and ad-hoc queries |
| Scaling | Horizontal and automatic, virtually unlimited | Vertical (instance class) plus read replicas; storage autoscaling |
| Operations | Serverless - no instances to size or patch | Managed instances: choose class, storage, maintenance and backup windows |
| Availability | Multi-AZ by default; global tables for multi-Region | Multi-AZ optional; cross-Region read replicas |
| Transactions | ACID transactions of up to 100 items | Full ACID transactions |
| Pricing | Per request (on-demand) or provisioned capacity, plus storage | Per instance-hour, storage, provisioned IOPS and backup storage beyond the free allotment |
| Best fit | Known access patterns at large scale, serverless apps | Complex queries, relational integrity, existing SQL applications |

## AWS CLI examples

```bash
# DynamoDB: on-demand table with a composite key and a GSI
aws dynamodb create-table --table-name StudentEnrolments \
  --attribute-definitions AttributeName=StudentId,AttributeType=S AttributeName=CourseId,AttributeType=S \
  --key-schema AttributeName=StudentId,KeyType=HASH AttributeName=CourseId,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --global-secondary-indexes '[{"IndexName":"CourseIndex","KeySchema":[{"AttributeName":"CourseId","KeyType":"HASH"},{"AttributeName":"StudentId","KeyType":"RANGE"}],"Projection":{"ProjectionType":"ALL"}}]'
aws dynamodb wait table-exists --table-name StudentEnrolments
aws dynamodb put-item --table-name StudentEnrolments \
  --item '{"StudentId":{"S":"S1001"},"CourseId":{"S":"TF201"},"CourseName":{"S":"Terraform and IaC"}}'
aws dynamodb query --table-name StudentEnrolments --key-condition-expression "StudentId = :s" \
  --expression-attribute-values '{":s":{"S":"S1001"}}'
aws dynamodb query --table-name StudentEnrolments --index-name CourseIndex \
  --key-condition-expression "CourseId = :c" --expression-attribute-values '{":c":{"S":"DEVOPS101"}}'

# RDS: encrypted Multi-AZ PostgreSQL in private subnets, password in Secrets Manager
aws rds create-db-subnet-group --db-subnet-group-name app-db-subnets \
  --db-subnet-group-description "Private subnets for RDS" \
  --subnet-ids subnet-0aaa1111bbbb22223 subnet-0ccc3333dddd44445
aws rds create-db-instance --db-instance-identifier app-db --engine postgres --engine-version 17 \
  --db-instance-class db.t4g.micro --allocated-storage 20 --storage-type gp3 \
  --master-username dbadmin --manage-master-user-password \
  --db-subnet-group-name app-db-subnets --vpc-security-group-ids sg-0123456789abcdef0 \
  --no-publicly-accessible --storage-encrypted --multi-az \
  --backup-retention-period 7 --deletion-protection

# Backups, PITR, read replica and failover test
aws rds create-db-snapshot --db-instance-identifier app-db --db-snapshot-identifier app-db-pre-release
aws rds restore-db-instance-to-point-in-time --source-db-instance-identifier app-db \
  --target-db-instance-identifier app-db-restored --use-latest-restorable-time
aws rds create-db-instance-read-replica --db-instance-identifier app-db-replica-1 \
  --source-db-instance-identifier app-db
aws rds reboot-db-instance --db-instance-identifier app-db --force-failover
```

## Terraform example

```hcl
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

provider "aws" { region = "ap-south-1" }

variable "private_subnet_ids" { type = list(string) }
variable "db_security_group_id" { type = string }

resource "aws_dynamodb_table" "enrolments" {
  name                        = "StudentEnrolments"
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "StudentId"
  range_key                   = "CourseId"
  deletion_protection_enabled = true

  attribute {
    name = "StudentId"
    type = "S"
  }
  attribute {
    name = "CourseId"
    type = "S"
  }

  global_secondary_index {
    name            = "CourseIndex"
    projection_type = "ALL"
    key_schema { # key_schema replaces the deprecated GSI hash_key/range_key arguments
      attribute_name = "CourseId"
      key_type       = "HASH"
    }
    key_schema {
      attribute_name = "StudentId"
      key_type       = "RANGE"
    }
  }

  point_in_time_recovery { enabled = true }
}

resource "aws_db_subnet_group" "app" {
  name       = "app-db-subnets"
  subnet_ids = var.private_subnet_ids
}

resource "aws_db_instance" "app" {
  identifier                          = "app-db"
  engine                              = "postgres"
  engine_version                      = "17"
  instance_class                      = "db.t4g.micro" # db.m*/db.r* classes for production
  allocated_storage                   = 20
  max_allocated_storage               = 100 # enables storage autoscaling
  storage_type                        = "gp3"
  storage_encrypted                   = true
  username                            = "dbadmin"
  manage_master_user_password         = true # stored and rotated in Secrets Manager
  iam_database_authentication_enabled = true
  db_subnet_group_name                = aws_db_subnet_group.app.name
  vpc_security_group_ids              = [var.db_security_group_id]
  publicly_accessible                 = false
  multi_az                            = true
  backup_retention_period             = 7
  deletion_protection                 = true
  final_snapshot_identifier           = "app-db-final"
}
```

## Key takeaways

- DynamoDB is serverless NoSQL: tables hold items (up to 400 KB) made of attributes, addressed by a partition key and an optional sort key.
- DynamoDB tables are designed from access patterns; GSIs and LSIs add alternative query paths, and on-demand mode removes capacity planning.
- RDS manages MySQL, PostgreSQL, MariaDB, Oracle, SQL Server and Db2 (plus Aurora); the customer still owns schema, queries and tuning.
- RDS security combines private subnets, security groups, KMS encryption, TLS, IAM database authentication and Secrets Manager.
- Automated backups (up to 35 days) enable point-in-time recovery; manual snapshots persist until deleted; every restore creates a new instance.
- Multi-AZ provides high availability through a synchronous standby (or a three-AZ cluster), while asynchronous read replicas scale reads and support cross-Region DR.
- Choose DynamoDB for massive scale with known access patterns, RDS for relational data and complex SQL.

## References

- [What is Amazon DynamoDB?](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Introduction.html)
- [Core components of DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/HowItWorks.CoreComponents.html)
- [DynamoDB throughput capacity](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/capacity-mode.html)
- [Improving data access with secondary indexes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/SecondaryIndexes.html)
- [Quotas in Amazon DynamoDB](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/ServiceQuotas.html)
- [What is Amazon RDS?](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Welcome.html)
- [DB instance classes](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.DBInstanceClass.html)
- [IAM database authentication](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.html)
- [Introduction to backups](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithAutomatedBackups.html)
- [Multi-AZ DB instance deployments](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZSingleStandby.html)
- [Multi-AZ DB cluster deployments](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/multi-az-db-clusters-concepts.html)
- [Working with DB instance read replicas](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ReadRepl.html)

<!-- HANDS-ON -->
