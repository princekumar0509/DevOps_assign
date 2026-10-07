# EC2 - Elastic Compute Cloud (Compute)

> Session 18 - Terraform & IaC | Task 2: AWS Services Research

## What is EC2?

Amazon Elastic Compute Cloud (EC2) provides resizable virtual servers, called **instances**, that run in a chosen AWS Region and Availability Zone (AZ). Modern instances run on the AWS Nitro System, and most are billed **per second with a 60-second minimum** while in the `running` state.

An instance is assembled from building blocks: an **AMI** (boot image), an **instance type** (CPU/memory/network profile), a **key pair** (SSH/RDP access), **security groups** (firewall), **EBS or instance store volumes** (block storage), a **subnet, network interface and IP addresses** (placement), an optional **IAM instance profile** (role credentials) and optional **user data** (a first-boot script run by cloud-init).

## Why it matters for DevOps

EC2 is the most direct way to run workloads on AWS and underpins many higher-level services (Auto Scaling groups, ECS/EKS worker nodes, CI runners, bastion hosts). DevOps engineers are expected to choose the right instance type and purchasing option for cost, bake repeatable images, bootstrap instances with user data, secure access without long-lived SSH keys and manage the whole fleet as code. Treating instances as disposable, Terraform-defined resources rather than hand-configured servers is what makes environments reproducible.

## AMI

An **Amazon Machine Image (AMI)** is a template containing one or more EBS snapshots (the root volume and optional data volumes), launch permissions and a block device mapping.

- **Sources** - AWS-provided images (Amazon Linux 2023, Ubuntu, Windows Server), AWS Marketplace, community AMIs, and custom "golden" AMIs built with EC2 Image Builder or Packer.
- **Regional** - an AMI ID exists in one Region; it must be copied to be used in another Region, and the copy gets a new ID.
- **Architecture** - `x86_64` or `arm64`; the AMI must match the instance type (Graviton types need `arm64` AMIs).
- **Discovery** - avoid hard-coding AMI IDs; resolve the latest image via public SSM parameters (e.g. `/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64`) or a filtered lookup.
- **Lifecycle** - AMIs can be deprecated, disabled and deregistered; deregistering does not delete the underlying snapshots.

## Instance types

### Families

| Category | Example families | Optimised for | Typical workloads |
|---|---|---|---|
| General purpose | `t3`, `t4g` (burstable), `m7i`, `m7g`, `m8g` | Balanced CPU/memory (about 1 vCPU : 4 GiB for M) | Web/app servers, small databases, dev/test |
| Compute optimized | `c7g`, `c7i`, `c8g` | High vCPU-to-memory ratio (about 1 : 2) | Batch, CI build agents, gaming, ad serving |
| Memory optimized | `r7g`, `r8g`, `x2idn`, `x8g`, `u7i` | Large RAM (about 1 : 8 for R, more for X/U) | In-memory caches, large relational databases, SAP HANA |
| Storage optimized | `i4i`, `i7ie`, `i8g`, `d3`, `d3en` | Fast local NVMe (I) or dense HDD (D) instance storage | NoSQL databases, data warehousing, distributed file systems |
| Accelerated computing | `p5`, `p6-b200`, `g6`, `g6e`, `inf2`, `trn2`, `f2` | GPUs, AWS Inferentia/Trainium chips, FPGAs | ML training and inference, graphics, video |

### Naming convention

```text
   m   7   g   .  large
   |   |   |      `--- size: nano, micro, small, medium, large, xlarge, 2xlarge ... metal
   |   |   `---------- options: g = AWS Graviton (Arm) processor
   |   `-------------- generation: 7th
   `------------------ series: m = general purpose
```

| Option letter | Meaning | Example |
|---|---|---|
| `a` / `g` / `i` | AMD / AWS Graviton / Intel processor | `m7a`, `m7g`, `m7i` |
| `d` | Local NVMe instance store volumes | `m7gd` |
| `n` | Network and EBS optimized | `c7gn` |
| `e` | Extra memory or extra storage | `i7ie` |
| `z` | High CPU frequency | `r7iz` |
| `flex` | Flex instance (baseline with burst capability) | `m7i-flex` |

Within a family each size step roughly doubles vCPU and memory; for example `m7g.large` has 2 vCPU and 8 GiB, while `m7g.xlarge` has 4 vCPU and 16 GiB.

### Burstable instances and CPU credits

T-family instances (`t3`, `t3a`, `t4g`, ...) provide a **baseline** CPU level and can **burst** above it using CPU credits.

- **One CPU credit** = one vCPU at 100% utilisation for one minute (or an equivalent combination, such as two vCPUs at 50% for one minute).
- Credits are **earned** continuously while usage is below the baseline and **spent** while above it. A `t3.micro`, for example, has 2 vCPUs with a 10% baseline per vCPU.
- **Standard mode** - when the credit balance reaches zero, CPU is throttled to the baseline.
- **Unlimited mode** - the instance can keep bursting; sustained usage above baseline incurs an extra charge for surplus credits. T3, T3a and T4g launch in unlimited mode by default; T2 launches in standard mode.
- Monitor `CPUCreditBalance` and `CPUSurplusCreditBalance` in CloudWatch. A T instance that is always busy is usually cheaper as an M or C instance.

### Purchasing options

| Option | Maximum discount vs On-Demand | Commitment | Best for |
|---|---|---|---|
| On-Demand | - | None, pay per second | Short-lived, unpredictable or new workloads |
| Savings Plans | Up to 66% (Compute SP) / up to 72% (EC2 Instance SP) | 1 or 3 years of USD/hour spend | Steady baseline usage; Compute SP also covers Fargate and Lambda |
| Reserved Instances | Up to 72% | 1 or 3 years for specific instance attributes | Steady workloads; zonal RIs also reserve capacity |
| Spot Instances | Up to 90% | None; AWS can reclaim with a 2-minute interruption notice | Fault-tolerant, stateless work: CI jobs, batch, big data |
| Dedicated Hosts/Instances, Capacity Reservations | - | Varies | Per-core licensing, compliance isolation, guaranteed capacity in an AZ |

AWS generally recommends Savings Plans over Reserved Instances for new commitments because they are more flexible.

## Key pairs

A **key pair** is a public key stored by AWS plus a private key held only by the user.

- On Linux, cloud-init writes the public key into `~/.ssh/authorized_keys` of the default user (`ec2-user` on Amazon Linux) at first boot. On Windows, the private key decrypts the initial Administrator password.
- Types: **RSA** and **ED25519** (ED25519 is not supported for Windows). Private key formats: `.pem` (OpenSSH) or `.ppk` (PuTTY).
- Key pairs are **regional**. AWS does not keep a copy of the private key; it can only be downloaded once at creation. An existing public key can be imported instead.
- The private key file must be readable only by its owner (`chmod 400`), otherwise SSH refuses it.
- Keyless alternatives preferred in production: **AWS Systems Manager Session Manager** (no inbound port 22, IAM-controlled and logged) and **EC2 Instance Connect** (pushes a short-lived public key for each session).

## Security Groups

A **security group (SG)** is a virtual firewall attached to an instance's elastic network interface (ENI).

| Characteristic | Behaviour |
|---|---|
| Stateful | Return traffic for an allowed connection is automatically allowed |
| Allow-only | Rules can only allow traffic; there are no deny rules |
| Defaults | No inbound traffic allowed; a new SG created via console/CLI allows all outbound traffic |
| Sources/destinations | CIDR blocks, prefix lists or other security groups (SG referencing) |
| Evaluation | All rules are evaluated together; changes apply immediately |
| Quotas (default) | 60 inbound and 60 outbound rules per SG; 5 SGs per ENI (adjustable up to 16) |

Example three-tier chain using SG references instead of IP addresses: `web-sg` allows TCP 443 from `0.0.0.0/0`, `app-sg` allows TCP 8080 only from `web-sg`, and `db-sg` allows TCP 5432 only from `app-sg`.

Note for Terraform users: the `aws_security_group` resource removes the default allow-all egress rule, so outbound rules must be declared explicitly.

## EBS

**Amazon Elastic Block Store (EBS)** provides network-attached block volumes. A volume lives in one AZ, can be attached to instances in that same AZ, and persists independently of the instance. Elastic Volumes allows size, type, IOPS and throughput to be changed without detaching.

| Type | Media | Size | Max IOPS | Max throughput | Notes |
|---|---|---|---|---|---|
| `gp3` | SSD | 1 GiB - 64 TiB | 80,000 | 2,000 MiB/s | Default choice; 3,000 IOPS and 125 MiB/s baseline included regardless of size |
| `gp2` | SSD | 1 GiB - 16 TiB | 16,000 | 250 MiB/s | Previous general purpose type; IOPS scale with size (3 IOPS/GiB) |
| `io2` Block Express | SSD | 4 GiB - 64 TiB | 256,000 | 4,000 MiB/s | 99.999% durability, sub-millisecond latency, Multi-Attach |
| `st1` | HDD | 125 GiB - 16 TiB | 500 | 500 MiB/s | Throughput-optimised streaming (big data, logs); not bootable |
| `sc1` | HDD | 125 GiB - 16 TiB | 250 | 250 MiB/s | Lowest-cost cold data; not bootable |

**Snapshots** are point-in-time, **incremental** backups of a volume stored durably by AWS (backed by S3 but not visible in user buckets). They are regional, can be copied across Regions and shared across accounts, and are used to create new volumes and AMIs. Automate them with Amazon Data Lifecycle Manager or AWS Backup; Recycle Bin protects against accidental deletion.

**Encryption** uses AWS KMS; enabling "EBS encryption by default" per Region makes every new volume and snapshot encrypted. By default the root volume is deleted at termination (`DeleteOnTermination = true`) while other attached volumes are preserved.

| | EBS volume | Instance store |
|---|---|---|
| Attachment | Network-attached | Physically attached disks on the host (NVMe/HDD) |
| Persistence | Survives stop/start and can outlive the instance | Data lost on stop, hibernate or terminate (survives reboot) |
| Availability | Any instance type, chosen size | Only on types that include it (e.g. `d` variants, I family), fixed size |
| Backups | Snapshots | None built in |
| Best for | Root volumes, databases, anything persistent | Caches, buffers, scratch space, replicated data |

## Public vs private IP (plus Elastic IP)

| Address type | Source | Behaviour on stop/start | Typical use |
|---|---|---|---|
| Private IPv4 | Subnet CIDR | Kept until the instance is terminated | Internal traffic within the VPC and connected networks |
| Public IPv4 (auto-assigned) | Amazon pool; assigned if the subnet or launch setting enables it | Released on stop/hibernate; a new one is assigned on start | Simple internet-facing instances |
| Elastic IP (EIP) | Static public IPv4 allocated to the account in a Region | Stays associated; can be remapped to another instance | Fixed endpoints, allow-listing, NAT gateways |
| IPv6 | VPC/subnet IPv6 range | Kept | Dual-stack workloads; globally unique |

- The instance OS only sees its private address; the internet gateway performs 1:1 NAT between the private and public IPv4 address.
- AWS charges hourly for every public IPv4 address, including Elastic IPs that are allocated but not in use, so unused EIPs should be released.
- Default quota: 5 Elastic IPs per Region (adjustable).

## Instance lifecycle

```text
                                       start (StartInstances)
                     +----------------------------------------------------------+
                     v                                                          |
RunInstances --> [pending] --> [running] --stop/hibernate--> [stopping] --> [stopped]
                                |  ^  |                                         |
                         reboot +--+  | terminate                     terminate |
                                      v                                         |
                               [shutting-down] <--------------------------------+
                                      |
                                      v
                                 [terminated]
```

| State | Meaning | Instance usage billed? |
|---|---|---|
| `pending` | Preparing to run (after launch or start) | No |
| `running` | Ready for use | Yes |
| `stopping` | Preparing to stop or hibernate | No, except when hibernating |
| `stopped` | Shut down; can be started again; type can be changed | No (EBS storage and EIPs still billed) |
| `shutting-down` | Preparing to be terminated | No |
| `terminated` | Permanently deleted; remains visible briefly | No |

| Action | RAM | Instance store | Public IPv4 | Private IPv4 / EIP | Root EBS volume |
|---|---|---|---|---|---|
| Reboot | Erased (OS restart) | Preserved | Kept | Kept | Preserved |
| Stop / start | Erased | Erased | New address on start | Kept | Preserved |
| Hibernate / start | Saved to root volume and restored | Erased | New address on start | Kept | Preserved |
| Terminate | Erased | Erased | Released | Private released; EIP disassociated | Deleted by default |

**Hibernation** must be enabled at launch, requires an encrypted EBS root volume large enough to hold the RAM contents, and is supported only on certain instance families and sizes. Termination protection, stop protection and the `InstanceInitiatedShutdownBehavior` attribute (stop or terminate when the OS shuts down; default stop) help prevent accidental data loss.

## Common use cases

- Web and application servers behind an Application Load Balancer in an Auto Scaling group.
- Self-hosted CI/CD runners and build agents (often on Spot Instances).
- Bastion or jump hosts (increasingly replaced by Session Manager).
- Worker nodes for Amazon ECS and Amazon EKS clusters.
- Self-managed databases or software that needs OS-level control or specific licensing.
- GPU instances for machine learning training and inference; HPC simulations.

## AWS CLI examples

```bash
# Compare instance types (vCPU and memory)
aws ec2 describe-instance-types --instance-types t3.micro m7g.large \
  --query "InstanceTypes[].[InstanceType,VCpuInfo.DefaultVCpus,MemoryInfo.SizeInMiB]" --output table

# Key pair (private key saved locally and locked down) and security group
aws ec2 create-key-pair --key-name demo-key --key-type ed25519 --key-format pem \
  --query KeyMaterial --output text > demo-key.pem
chmod 400 demo-key.pem
aws ec2 create-security-group --group-name web-sg --description "Web tier" --vpc-id vpc-0abc1234def567890
aws ec2 authorize-security-group-ingress --group-id sg-0123456789abcdef0 \
  --protocol tcp --port 443 --cidr 0.0.0.0/0

# Launch an instance with IMDSv2 enforced
aws ec2 run-instances \
  --image-id resolve:ssm:/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --instance-type t3.micro --key-name demo-key \
  --subnet-id subnet-0123456789abcdef0 --security-group-ids sg-0123456789abcdef0 \
  --metadata-options HttpTokens=required \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=web-01}]'

# Lifecycle operations
aws ec2 stop-instances --instance-ids i-0123456789abcdef0
aws ec2 stop-instances --instance-ids i-0123456789abcdef0 --hibernate
aws ec2 start-instances --instance-ids i-0123456789abcdef0
aws ec2 reboot-instances --instance-ids i-0123456789abcdef0
aws ec2 terminate-instances --instance-ids i-0123456789abcdef0

# EBS volume, snapshot and Elastic IP
aws ec2 create-volume --availability-zone ap-south-1a --volume-type gp3 --size 50 --encrypted
aws ec2 attach-volume --volume-id vol-0123456789abcdef0 --instance-id i-0123456789abcdef0 --device /dev/sdf
aws ec2 create-snapshot --volume-id vol-0123456789abcdef0 --description "pre-upgrade"
aws ec2 allocate-address --domain vpc
aws ec2 associate-address --instance-id i-0123456789abcdef0 --allocation-id eipalloc-0123456789abcdef0
```

## Terraform example

```hcl
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

provider "aws" { region = "ap-south-1" }

variable "vpc_id" { type = string }
variable "public_subnet_id" { type = string }

# Latest Amazon Linux 2023 AMI (provider v6 requires "owners" when most_recent = true)
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]
  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
}

resource "aws_security_group" "web" {
  name   = "web-sg"
  vpc_id = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "https" {
  security_group_id = aws_security_group.web.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.web.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1" # all protocols
}

resource "aws_key_pair" "deployer" {
  key_name   = "deployer-key"
  public_key = file("~/.ssh/id_ed25519.pub")
}

resource "aws_instance" "web" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = "t3.micro"
  subnet_id              = var.public_subnet_id
  vpc_security_group_ids = [aws_security_group.web.id]
  key_name               = aws_key_pair.deployer.key_name
  user_data              = "#!/bin/bash\ndnf install -y nginx && systemctl enable --now nginx"

  metadata_options { http_tokens = "required" } # enforce IMDSv2

  root_block_device {
    volume_type = "gp3"
    volume_size = 20
    encrypted   = true
  }

  tags = { Name = "web-01" }
}

resource "aws_eip" "web" {
  domain   = "vpc"
  instance = aws_instance.web.id
}
```

## Key takeaways

- An EC2 instance is the combination of an AMI, an instance type, networking (subnet, IPs, security groups), storage (EBS/instance store) and an IAM instance profile.
- Instance type names encode series, generation, options and size (`m7g.large`); matching the family to the workload is the main performance and cost lever.
- Burstable T instances run on CPU credits; Spot, Savings Plans and Reserved Instances reduce cost compared with On-Demand.
- Security groups are stateful, allow-only firewalls at the network interface; prefer Session Manager over open SSH ports.
- EBS is persistent, AZ-scoped block storage (`gp3` by default) protected with snapshots; instance store is fast but ephemeral.
- Public IPv4 addresses change on stop/start unless an Elastic IP is used, and all public IPv4 addresses are billed.
- Knowing what each lifecycle state preserves (RAM, instance store, IPs, volumes) prevents data loss and surprise bills.

## References

- [What is Amazon EC2?](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/concepts.html)
- [Amazon Machine Images (AMIs)](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/AMIs.html)
- [Amazon EC2 instance types](https://docs.aws.amazon.com/ec2/latest/instancetypes/instance-types.html)
- [Instance type naming conventions](https://docs.aws.amazon.com/ec2/latest/instancetypes/instance-type-names.html)
- [Burstable performance instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances.html)
- [Instance purchasing options](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instance-purchasing-options.html)
- [Amazon EC2 key pairs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html)
- [Security groups for EC2 instances](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-security-groups.html)
- [Amazon EBS volume types](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volume-types.html)
- [Amazon EBS snapshots](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-snapshots.html)
- [Elastic IP addresses](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/elastic-ip-addresses-eip.html)
- [Amazon EC2 instance state changes](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-lifecycle.html)

<!-- HANDS-ON -->
