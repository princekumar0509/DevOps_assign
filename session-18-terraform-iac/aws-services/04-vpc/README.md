# VPC - Virtual Private Cloud (Networking)

> Session 18 - Terraform & IaC | Task 2: AWS Services Research

## What is VPC?

Amazon Virtual Private Cloud (VPC) is a logically isolated virtual network inside an AWS Region. The owner chooses its IP address ranges, divides it into subnets, controls routing, attaches gateways and applies firewall rules - much like a traditional data-centre network, but defined through APIs.

| Component | Scope | Purpose |
|---|---|---|
| VPC | Region (spans all AZs) | Isolated network with one or more CIDR blocks |
| Subnet | One Availability Zone | Slice of the VPC CIDR where resources are launched |
| Route table | VPC; associated with subnets | Decides where traffic leaving a subnet is sent |
| Internet gateway (IGW) | VPC | Connects the VPC to the internet |
| NAT gateway | AZ (zonal) or Region (regional mode) | Outbound-only internet access for private resources |
| Security group / Network ACL | Network interface / Subnet | Stateful allow-only firewall / stateless allow+deny firewall |
| VPC endpoints, peering, Transit Gateway, VPN | VPC | Private access to AWS services (gateway endpoints for S3/DynamoDB, PrivateLink interface endpoints) and connectivity to other networks |

Every Region contains a **default VPC** (`172.31.0.0/16`, a public `/20` subnet in each AZ and an attached IGW) so that instances can be launched immediately. Production workloads normally use custom VPCs defined as code.

## Why it matters for DevOps

Almost every AWS resource - EC2, RDS, EKS, Lambda in a VPC, load balancers - is placed into a VPC, so the network design determines what is reachable, how traffic flows and what it costs. Overlapping CIDR ranges are painful to fix later, missing routes are a frequent cause of failed deployments, and NAT data processing can become a significant line on the bill. Defining VPCs in Terraform gives every environment (dev, staging, prod) the same tested topology and makes network changes reviewable.

## CIDR

**Classless Inter-Domain Routing (CIDR)** notation writes an address range as `base-address/prefix-length`. The prefix length is the number of fixed network bits; the remaining bits identify hosts, so a block contains `2^(32 - prefix)` addresses.

- A VPC's IPv4 block must be between `/16` (65,536 addresses) and `/28` (16 addresses).
- Use private RFC 1918 ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) that do not overlap with peered VPCs or on-premises networks.
- Up to 5 IPv4 CIDR blocks per VPC by default (adjustable up to 50); secondary blocks can be added later, but the primary block cannot be changed.

### Worked example: splitting 10.0.0.0/16 into /24 subnets

```text
10.0.0.0/16 = 00001010.00000000 | 00000000.00000000
              16 network bits   | 16 host bits     -> 2^16 = 65,536 addresses
10.0.1.0/24 = 00001010.00000000.00000001 | 00000000
              24 network bits            | 8 host bits -> 2^8 = 256 addresses
```

Moving from `/16` to `/24` borrows 8 bits for subnetting, giving `2^8 = 256` possible `/24` subnets (`10.0.0.0/24` through `10.0.255.0/24`), each with 256 addresses (251 usable, see below). For comparison, a `/20` holds 4,096 addresses and a `/28` only 16. A two-AZ layout might use:

| Subnet | CIDR | Address range | AZ |
|---|---|---|---|
| public-a | `10.0.1.0/24` | 10.0.1.0 - 10.0.1.255 | ap-south-1a |
| public-b | `10.0.2.0/24` | 10.0.2.0 - 10.0.2.255 | ap-south-1b |
| private-a | `10.0.11.0/24` | 10.0.11.0 - 10.0.11.255 | ap-south-1a |
| private-b | `10.0.12.0/24` | 10.0.12.0 - 10.0.12.255 | ap-south-1b |

In Terraform, `cidrsubnet("10.0.0.0/16", 8, 11)` computes `10.0.11.0/24` (8 new bits, subnet number 11).

AWS reserves **5 addresses in every subnet**. For `10.0.1.0/24`:

| Address | Reserved for |
|---|---|
| `10.0.1.0` | Network address |
| `10.0.1.1` | VPC router |
| `10.0.1.2` | DNS (the Amazon DNS server is at the VPC base + 2, e.g. `10.0.0.2`; base + 2 is reserved in every subnet) |
| `10.0.1.3` | Reserved by AWS for future use |
| `10.0.1.255` | Network broadcast address (broadcast is not supported in a VPC, so it is reserved) |

Usable addresses are therefore `10.0.1.4` - `10.0.1.254`: **251** hosts.

## Subnets

A **subnet** is a range of IP addresses within the VPC that resides in exactly **one Availability Zone**; it cannot span AZs. High availability is achieved by creating matching subnets in at least two AZs.

- Each subnet is associated with exactly one route table and one network ACL; subnet CIDRs within a VPC must not overlap (default quota: 200 subnets per VPC).
- Subnet settings include auto-assign public IPv4 on launch and an optional IPv6 CIDR (`/44` to `/64`).
- Whether a subnet is "public" or "private" is determined by its **route table**, not by a subnet flag (see below).

## Route tables

A **route table** contains routes of the form *destination CIDR -> target*. The most specific matching route (longest prefix) wins.

- Every VPC has a **main route table** used by subnets without an explicit association; custom route tables are recommended so that the main table stays private.
- Every route table contains a non-removable **local route** for the VPC CIDR, which enables traffic between all subnets in the VPC.
- Targets include an internet gateway, NAT gateway, peering connection, transit gateway, gateway endpoint (via prefix list) or network interface.

| Destination | Public route table | Private route table (one per AZ with zonal NAT) |
|---|---|---|
| `10.0.0.0/16` | `local` | `local` |
| `0.0.0.0/0` | `igw-xxxx` (internet gateway) | `nat-xxxx` (NAT gateway in the same AZ) |
| `pl-xxxx` (S3 prefix list) | - | `vpce-xxxx` (optional S3 gateway endpoint) |

## Internet Gateway

An **internet gateway (IGW)** is a horizontally scaled, redundant and highly available VPC component that allows communication between the VPC and the internet. Only one IGW can be attached to a VPC, and it has no hourly charge (data transfer is billed).

It serves two purposes: it is a **route target** for internet-bound traffic, and it performs **1:1 NAT** between an instance's private IPv4 address and its public or Elastic IPv4 address. Internet reachability requires all four of: an attached IGW, a subnet route to it (`0.0.0.0/0 -> igw-xxxx`), a public IPv4/Elastic IP/IPv6 address on the resource, and security group plus network ACL rules that allow the traffic. For IPv6, an **egress-only internet gateway** provides outbound-only access.

## NAT Gateway

A **NAT gateway** lets resources in private subnets **initiate** outbound connections (for example, to download OS patches or call external APIs) while blocking unsolicited inbound connections.

| Variant | Placement | Notes |
|---|---|---|
| Public NAT gateway (zonal) | Created in a **public subnet** with an Elastic IP | Private subnets route `0.0.0.0/0` to it; traffic then leaves via the IGW. Deploy one per AZ so that an AZ failure does not break egress in other AZs |
| Regional NAT gateway | Created for the VPC with `availability-mode regional`; no public subnet required | Automatically expands to AZs where workloads exist; one NAT ID for all private route tables; does not support private connectivity |
| Private NAT gateway | Private subnet, no Elastic IP | Outbound connectivity to other VPCs or on-premises networks via a transit gateway or virtual private gateway |

- A zonal NAT gateway scales automatically from 5 Gbps up to 100 Gbps; the default quota is 5 NAT gateways per AZ.
- NAT gateways are billed per hour **and** per GB processed. Gateway endpoints for S3 and DynamoDB (no charge) and interface endpoints for other services keep AWS-bound traffic off the NAT gateway and reduce cost.

## Security Groups

Security groups are stateful firewalls attached to network interfaces (EC2 instances, RDS, load balancers, Lambda ENIs): response traffic is allowed automatically, only allow rules exist, all inbound traffic is denied by default, and rules can reference other security groups, which enables tier-to-tier rules without hard-coding IP addresses:

```text
Internet --443--> [alb-sg] --8080--> [app-sg] --5432--> [db-sg]
          (0.0.0.0/0)      (source: alb-sg)   (source: app-sg)
```

Default quotas: 60 inbound and 60 outbound rules per group, 5 groups per network interface (adjustable up to 16).

## Network ACLs

A **network ACL (NACL)** is an optional, **stateless** firewall applied at the **subnet** boundary.

- Rules are numbered (1 - 32766) and evaluated **in order from the lowest number**; the first match wins. A final `*` rule denies anything unmatched.
- Rules can **allow or deny** (useful for blocking specific IP ranges). Because NACLs are stateless, return traffic must be explicitly allowed - typically the ephemeral port range `1024-65535`.
- The default NACL allows all inbound and outbound traffic; a newly created custom NACL denies everything until rules are added.
- Each subnet is associated with exactly one NACL; one NACL can serve many subnets. Default quota: 20 rules per direction (adjustable up to 40).

Example NACL for a public web subnet:

| Direction | Rule # | Protocol / port | Source / destination | Action |
|---|---|---|---|---|
| Inbound | 90 | All | `203.0.113.0/24` (known bad range) | DENY |
| Inbound | 100 | TCP 443 | `0.0.0.0/0` | ALLOW |
| Inbound | 110 | TCP 1024-65535 | `0.0.0.0/0` (responses to outbound requests) | ALLOW |
| Inbound | * | All | `0.0.0.0/0` | DENY |
| Outbound | 100 | TCP 443 | `0.0.0.0/0` | ALLOW |
| Outbound | 110 | TCP 1024-65535 | `0.0.0.0/0` (responses to clients) | ALLOW |
| Outbound | * | All | `0.0.0.0/0` | DENY |

### Security group vs network ACL

| Feature | Security group | Network ACL |
|---|---|---|
| Level | Instance / network interface | Subnet |
| State | Stateful - return traffic automatically allowed | Stateless - return traffic must be explicitly allowed |
| Rule types | Allow only | Allow and deny |
| Rule order | All rules evaluated together | Numbered rules evaluated lowest first; first match wins |
| Default | Inbound denied, outbound allowed | Default NACL allows all; custom NACL denies all |
| References | Can reference other security groups | CIDR blocks only |
| Typical role | Primary, fine-grained access control | Coarse subnet guardrail, explicit IP blocking |

## Public vs private subnet

| Aspect | Public subnet | Private subnet |
|---|---|---|
| Defining feature | Route table has a route to an **internet gateway** | No route to an internet gateway |
| Outbound internet | Directly through the IGW (needs a public IP) | Through a NAT gateway, or none at all (isolated subnet) |
| Inbound from internet | Possible if SG/NACL allow it | Not possible directly |
| Typical resources | Load balancers, NAT gateways, bastion hosts | Application servers, databases, caches, EKS worker nodes |

A common best practice is to keep only internet-facing entry points (load balancers) in public subnets and everything else in private subnets.

## Architecture: two-AZ VPC

```text
                                    Internet
                                       |
                              +------------------+
                              | Internet Gateway |
                              +--------+---------+
                                       |
+--------------------------------------+---------------------------------------+
| VPC 10.0.0.0/16  (Region: ap-south-1)                                        |
|  +--------- AZ ap-south-1a ---------+  +--------- AZ ap-south-1b ---------+  |
|  | Public subnet 10.0.1.0/24        |  | Public subnet 10.0.2.0/24        |  |
|  |  +------------+  +------------+  |  |  +------------+  +------------+  |  |
|  |  | NAT GW (a) |  | ALB node   |  |  |  | NAT GW (b) |  | ALB node   |  |  |
|  |  |  + EIP     |  |            |  |  |  |  + EIP     |  |            |  |  |
|  |  +------^-----+  +------------+  |  |  +------^-----+  +------------+  |  |
|  |- - - - -|- - - - - - - - - - - - |  |- - - - -|- - - - - - - - - - - - |  |
|  | Private subnet 10.0.11.0/24      |  | Private subnet 10.0.12.0/24      |  |
|  |         |                        |  |         |                        |  |
|  |  +------+-----+  +------------+  |  |  +------+-----+  +------------+  |  |
|  |  | App EC2    |  | RDS        |  |  |  | App EC2    |  | RDS        |  |  |
|  |  | (no pub IP)|  | primary    |  |  |  | (no pub IP)|  | standby    |  |  |
|  |  +------------+  +------------+  |  |  +------------+  +------------+  |  |
|  +----------------------------------+  +----------------------------------+  |
|                                                                              |
| Public RT    : 10.0.0.0/16 -> local | 0.0.0.0/0 -> igw-xxxx                  |
| Private RT-a : 10.0.0.0/16 -> local | 0.0.0.0/0 -> NAT GW (a)                |
| Private RT-b : 10.0.0.0/16 -> local | 0.0.0.0/0 -> NAT GW (b)                |
+------------------------------------------------------------------------------+
```

Traffic flows in this design:

- **Inbound**: Internet -> IGW -> load balancer node in a public subnet -> app instance in a private subnet (allowed by `app-sg` from `alb-sg`).
- **Outbound from private subnets**: app instance -> private route table -> NAT gateway in the same AZ -> public route table -> IGW -> Internet. Replies return the same way; unsolicited inbound connections are dropped.
- **Database**: RDS primary and standby live in private subnets of different AZs and accept connections only from `app-sg`.

## AWS CLI examples

```bash
# VPC and two subnets in AZ a (IDs captured in shell variables)
VPC_ID=$(aws ec2 create-vpc --cidr-block 10.0.0.0/16 --query Vpc.VpcId --output text)
PUB_A=$(aws ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block 10.0.1.0/24 \
  --availability-zone ap-south-1a --query Subnet.SubnetId --output text)
PRIV_A=$(aws ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block 10.0.11.0/24 \
  --availability-zone ap-south-1a --query Subnet.SubnetId --output text)
aws ec2 modify-subnet-attribute --subnet-id "$PUB_A" --map-public-ip-on-launch

# Internet gateway and public route table
IGW_ID=$(aws ec2 create-internet-gateway --query InternetGateway.InternetGatewayId --output text)
aws ec2 attach-internet-gateway --internet-gateway-id "$IGW_ID" --vpc-id "$VPC_ID"
PUB_RT=$(aws ec2 create-route-table --vpc-id "$VPC_ID" --query RouteTable.RouteTableId --output text)
aws ec2 create-route --route-table-id "$PUB_RT" --destination-cidr-block 0.0.0.0/0 --gateway-id "$IGW_ID"
aws ec2 associate-route-table --route-table-id "$PUB_RT" --subnet-id "$PUB_A"

# Zonal NAT gateway in the public subnet and a private route table
EIP_ALLOC=$(aws ec2 allocate-address --domain vpc --query AllocationId --output text)
NAT_ID=$(aws ec2 create-nat-gateway --subnet-id "$PUB_A" --allocation-id "$EIP_ALLOC" \
  --query NatGateway.NatGatewayId --output text)
aws ec2 wait nat-gateway-available --nat-gateway-ids "$NAT_ID"
PRIV_RT=$(aws ec2 create-route-table --vpc-id "$VPC_ID" --query RouteTable.RouteTableId --output text)
aws ec2 create-route --route-table-id "$PRIV_RT" --destination-cidr-block 0.0.0.0/0 --nat-gateway-id "$NAT_ID"
aws ec2 associate-route-table --route-table-id "$PRIV_RT" --subnet-id "$PRIV_A"

# Alternative: regional NAT gateway; and a network ACL deny rule
aws ec2 create-nat-gateway --vpc-id "$VPC_ID" --availability-mode regional
aws ec2 create-network-acl-entry --network-acl-id acl-0123456789abcdef0 --ingress \
  --rule-number 90 --protocol -1 --cidr-block 203.0.113.0/24 --rule-action deny
```

## Terraform example

```hcl
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

provider "aws" { region = "ap-south-1" }

data "aws_availability_zones" "available" { state = "available" }

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
}

resource "aws_subnet" "public" {
  count                   = 2
  vpc_id                  = aws_vpc.main.id
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index + 1) # 10.0.1.0/24, 10.0.2.0/24
  map_public_ip_on_launch = true
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  availability_zone = data.aws_availability_zones.available.names[count.index]
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index + 11) # 10.0.11.0/24, 10.0.12.0/24
}

resource "aws_eip" "nat" {
  count  = 2
  domain = "vpc"
}

resource "aws_nat_gateway" "nat" {
  count         = 2
  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  depends_on    = [aws_internet_gateway.igw]
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }
}

resource "aws_route_table" "private" {
  count  = 2
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat[count.index].id
  }
}

resource "aws_route_table_association" "public" {
  count          = 2
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}
```

The `local` route is created automatically in every route table. A regional NAT gateway would replace the EIPs and per-AZ NAT gateways with a single `aws_nat_gateway` using `vpc_id` and `availability_mode = "regional"`.

## Key takeaways

- A VPC is a Regional, isolated network; subnets live in a single AZ, so high availability requires subnets in at least two AZs.
- CIDR prefix length sets the size of a range (`2^(32 - prefix)` addresses); a `/16` splits into 256 `/24` subnets, each with 251 usable addresses after AWS reserves 5.
- A subnet is public only because its route table points `0.0.0.0/0` at an internet gateway; private subnets reach the internet through a NAT gateway.
- Zonal NAT gateways belong in public subnets, one per AZ; regional NAT gateways remove that requirement. NAT data processing is a notable cost, reduced by VPC endpoints.
- Security groups are stateful, allow-only and attached to interfaces; network ACLs are stateless, ordered, allow/deny rules at the subnet boundary.
- Defining the VPC in Terraform with `cidrsubnet()` and `count`/`for_each` keeps every environment's network consistent.

## References

- [What is Amazon VPC?](https://docs.aws.amazon.com/vpc/latest/userguide/what-is-amazon-vpc.html)
- [VPC CIDR blocks](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-cidr-blocks.html)
- [Subnet CIDR blocks](https://docs.aws.amazon.com/vpc/latest/userguide/subnet-sizing.html)
- [Configure route tables](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Route_Tables.html)
- [Enable internet access using an internet gateway](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Internet_Gateway.html)
- [NAT gateways](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-nat-gateway.html)
- [Regional NAT gateways](https://docs.aws.amazon.com/vpc/latest/userguide/nat-gateways-regional.html)
- [Control traffic with security groups](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-security-groups.html)
- [Control subnet traffic with network ACLs](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-network-acls.html)
- [Amazon VPC quotas](https://docs.aws.amazon.com/vpc/latest/userguide/amazon-vpc-limits.html)

<!-- HANDS-ON -->
