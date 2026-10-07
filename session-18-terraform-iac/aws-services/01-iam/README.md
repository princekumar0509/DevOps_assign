# IAM - Identity and Access Management (Governance)

> Session 18 - Terraform & IaC | Task 2: AWS Services Research

## What is IAM?

AWS Identity and Access Management (IAM) is the service that controls **authentication** (who is making a request) and **authorization** (what that principal is allowed to do) for every AWS API call - whether the call comes from the console, the AWS CLI, an SDK or Terraform.

| Property | Detail |
|---|---|
| Scope | Global service; users, groups, roles and policies are not tied to a Region |
| Cost | No additional charge |
| Default stance | Deny by default - a new user or role can do nothing until a policy allows it |
| Request model | Each request is signed (SigV4) and evaluated against all applicable policies |
| Audit | API activity is recorded by AWS CloudTrail |

Core vocabulary: a **principal** (root user, IAM user, role session, AWS service or federated identity) performs an **action** (`service:Operation`, e.g. `ec2:StartInstances`) on a **resource** identified by an ARN (e.g. `arn:aws:s3:::my-app-artifacts/*`), and a **policy** (JSON document) allows or denies that combination, optionally under conditions.

## Why it matters for DevOps

Every pipeline, Terraform run, container and EC2 instance needs credentials, and IAM decides how far a leaked credential or a buggy script can reach. Defining IAM as code makes permissions reviewable in pull requests, repeatable across environments and auditable through version history. Most cloud security incidents trace back to over-broad permissions or long-lived access keys, so IAM design is a core DevOps responsibility rather than an afterthought.

## Users

An **IAM user** is an identity with **long-term credentials**: an optional console password and up to two access keys (access key ID + secret access key) for programmatic access.

| | Root user | IAM user |
|---|---|---|
| Created | Automatically with the AWS account (email + password) | By an administrator |
| Permissions | Full, unrestricted access; identity policies cannot limit it (SCPs can restrict it in member accounts) | Only what attached policies allow |
| Intended use | A small set of root-only tasks (e.g. changing account settings, closing the account) | Legacy or exceptional cases only - their credentials never expire, so AWS recommends federation for people and roles for workloads |

## Groups

An **IAM group** is a collection of IAM users. Policies attached to the group apply to every member, which avoids managing permissions user-by-user.

- Groups cannot be nested (no groups inside groups).
- A group is not a principal - it cannot be named in the `Principal` element of a resource-based policy.
- A user can belong to multiple groups (default quota: 10 groups per user).

```text
Group "developers" --attached--> ReadOnlyAccess + custom "deploy-to-dev" policy
  |-- alice   (inherits both policies)
  `-- bob     (inherits both policies)
```

## Roles

An **IAM role** is an identity with permissions but **no long-term credentials**. A trusted principal *assumes* the role and receives **temporary security credentials** from AWS STS (access key, secret key, session token and expiry).

A role has two kinds of policy:

| Policy | Question it answers | Example |
|---|---|---|
| Trust policy (resource-based) | Who may assume the role? | `ec2.amazonaws.com`, another account, a GitHub OIDC provider |
| Permissions policies (identity-based) | What may the session do? | Read objects from one S3 bucket |

Example trust policy allowing EC2 to assume the role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Principal": { "Service": "ec2.amazonaws.com" }, "Action": "sts:AssumeRole" }
  ]
}
```

```text
Caller (EC2 instance, CI job, engineer)
  1. --- sts:AssumeRole (checked against the TRUST policy) -------------> AWS STS
  2. <-- temporary credentials (default 1 h; role max session 1-12 h) --- AWS STS
  3. --- signed API calls (checked against PERMISSIONS policies) -------> S3, EC2, ...
```

Common role types: **service roles** (EC2 instance profiles, Lambda execution roles, ECS task roles), **cross-account roles**, **federated roles** (SAML 2.0 or OIDC, e.g. GitHub Actions), and **service-linked roles** that AWS services create and manage themselves.

## Policies

### Policy types

| Type | Attached to | Grants access? | Purpose |
|---|---|---|---|
| Identity-based | Users, groups, roles | Yes | What the identity can do |
| Resource-based | Resources (S3 bucket policy, KMS key policy, SQS queue policy, role trust policy) | Yes | Who can access this resource, including other accounts; always has a `Principal` |
| Permissions boundary | Users, roles | No - sets a maximum | Caps what identity-based policies can grant |
| Service control policy (SCP) | AWS Organizations root, OUs, accounts | No - sets a maximum | Guardrail for all principals in member accounts |
| Resource control policy (RCP) | AWS Organizations root, OUs, accounts | No - sets a maximum | Guardrail for resources in member accounts |
| Session policy | Passed when assuming a role | No - sets a maximum | Further narrows a single session |

### Identity-based vs resource-based

- **Identity-based** policies are attached to the caller and do not contain a `Principal` element; the principal is implied.
- **Resource-based** policies are attached to the target resource, must name a `Principal`, and are the main way to grant **cross-account** access. For cross-account requests, both the caller's identity-based policy and the resource-based policy must allow the action.

### Managed vs inline

| | AWS managed | Customer managed | Inline |
|---|---|---|---|
| Created and maintained by | AWS | The account owner | The account owner, embedded in one identity |
| Reusable across identities | Yes | Yes | No (strict 1:1) |
| Versioning | Updated by AWS | Up to 5 versions with rollback | None |
| Typical use | Job-function starting points (e.g. `ReadOnlyAccess`) | Preferred for least-privilege, workload-specific access | Exceptional cases where the policy must be deleted with the identity |

### Policy JSON anatomy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadAppArtifacts",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": ["arn:aws:s3:::my-app-artifacts", "arn:aws:s3:::my-app-artifacts/*"],
      "Condition": { "Bool": { "aws:SecureTransport": "true" } }
    },
    {
      "Sid": "NeverDeleteArtifacts",
      "Effect": "Deny",
      "Action": "s3:DeleteObject",
      "Resource": "arn:aws:s3:::my-app-artifacts/*"
    }
  ]
}
```

| Element | Required? | Meaning |
|---|---|---|
| `Version` | Strongly recommended | Policy language version; always use `2012-10-17` (the older `2008-10-17` lacks features such as policy variables) |
| `Statement` | Yes | One statement object or an array of statements |
| `Sid` | No | Human-readable statement identifier |
| `Effect` | Yes | `Allow` or `Deny` |
| `Principal` | Resource-based policies only | Who the statement applies to (account, user, role, service, `*`) |
| `Action` / `NotAction` | Yes | Operations, wildcards allowed (e.g. `s3:Get*`) |
| `Resource` / `NotResource` | Yes in identity-based policies | ARNs the statement applies to (trust policies omit it) |
| `Condition` | No | `{ "Operator": { "key": "value" } }`, e.g. `StringEquals`, `IpAddress`, `Bool`, `DateLessThan` |

### Evaluation logic

```text
Request (principal, action, resource, context) is evaluated top to bottom:

 1. Explicit Deny in ANY applicable policy?                 yes --> DENY (final)
 2. In an Organization: do SCPs and RCPs allow it?          no  --> DENY (implicit)
 3. Allowed by an identity-based OR resource-based policy?  no  --> DENY (implicit)
 4. Permissions boundary / session policy (if any) allow?   no  --> DENY (implicit)
 5. All checks passed                                           --> ALLOW
```

The precedence rule to remember is **explicit deny > explicit allow > implicit deny**: everything starts as denied, an `Allow` is needed to grant access, and any matching `Deny` overrides every `Allow`. This sequence is simplified for a single account; the official flowchart also covers cross-account access and some resource-based policy edge cases.

## Permissions

Effective permissions are the **intersection of all guardrails** applied to the **union of all grants**, minus anything explicitly denied:

```text
allowed = (identity-based OR resource-based allows) AND boundary AND SCPs AND RCPs AND session policy AND no explicit Deny
```

- **Permissions boundaries** - a managed policy set on a user or role that defines the *maximum* permissions its identity-based policies can grant. A common pattern lets developers create roles for their applications only if they attach a mandated boundary (enforced with the `iam:PermissionsBoundary` condition key), which prevents privilege escalation.
- **Service control policies (SCPs)** - AWS Organizations policies attached to the root, an OU or an account. They limit what every principal in member accounts can do, including the member account root user, but never grant permissions themselves. They do not apply to the management account or to service-linked roles. Typical SCPs deny disabling CloudTrail, leaving the organization, or using unapproved Regions.
- **Resource control policies (RCPs)** - the resource-side counterpart to SCPs, used to cap access to resources such as S3 buckets and KMS keys across an organization.

## Least privilege

Least privilege means granting only the actions, on only the resources, under only the conditions a task requires - and nothing more.

| Over-privileged | Least privilege |
|---|---|
| `"Action": "*"`, `"Resource": "*"` | `"Action": ["s3:GetObject"]` on `arn:aws:s3:::my-app-artifacts/*` |
| One shared admin role for all pipelines | A separate role per pipeline and per environment |
| Permanent access "just in case" | Time-bound access through Identity Center permission sets or role sessions |

Practical approach: start from AWS managed policies while exploring, then generate a tighter customer managed policy from real CloudTrail activity with IAM Access Analyzer, scope `Resource` to specific ARNs, add `Condition` keys, and review last-accessed information to remove unused permissions.

## IAM best practices

| Practice | How it is applied |
|---|---|
| Protect the root user with MFA | AWS requires MFA for the root user of all account types; registering more than one MFA device adds resilience |
| No root access keys | Never create access keys for the root user; use root only for root-only tasks. Organizations can centrally remove root credentials from member accounts |
| Federation / IAM Identity Center for people | Workforce users sign in through IAM Identity Center or an external IdP and receive temporary credentials (`aws sso login`, or `aws login` for console credentials) |
| Roles for workloads | EC2 instance profiles, Lambda/ECS task roles, EKS Pod Identity or IRSA, and OIDC federation for CI/CD (e.g. GitHub Actions) instead of stored access keys |
| Short-lived credentials | Prefer STS-issued credentials that expire automatically over long-term keys |
| MFA for human access | Require MFA for privileged actions, for example with `aws:MultiFactorAuthPresent` |
| IAM Access Analyzer | Find resources shared outside the account or organization, flag unused roles, keys and permissions, validate policies and generate policies from activity |
| Rotate and remove keys | Where long-term keys are unavoidable, rotate them regularly (two-key rotation) and delete unused credentials; the credential report shows key age and last use |
| Tag-based access control (ABAC) | Grant access by matching tags, e.g. `aws:ResourceTag/Project` equals `${aws:PrincipalTag/Project}`, so policies scale without listing every ARN |
| Guardrails and monitoring | Apply SCPs/permissions boundaries and alert on root sign-in and IAM changes through CloudTrail and EventBridge |

ABAC example statement:

```json
{
  "Effect": "Allow",
  "Action": ["ec2:StartInstances", "ec2:StopInstances"],
  "Resource": "arn:aws:ec2:*:*:instance/*",
  "Condition": { "StringEquals": { "aws:ResourceTag/Project": "${aws:PrincipalTag/Project}" } }
}
```

## Common use cases

| Scenario | IAM mechanism |
|---|---|
| Engineers sign in to several accounts | IAM Identity Center permission sets mapped to IdP groups |
| EC2 application reads from S3 | Role + instance profile with a bucket-scoped policy |
| GitHub Actions deploys with Terraform | OIDC identity provider + role whose trust policy restricts the repository and branch |
| Central security account audits all accounts | Cross-account read-only role |
| Developers may create roles but not escalate | Permissions boundary enforced by condition |
| Organization-wide Region restriction | SCP denying actions outside approved Regions |

## AWS CLI examples

```bash
# Which identity are the current credentials for?
aws sts get-caller-identity

# Groups and users
aws iam create-group --group-name developers
aws iam attach-group-policy --group-name developers --policy-arn arn:aws:iam::aws:policy/ReadOnlyAccess
aws iam create-user --user-name alice
aws iam add-user-to-group --user-name alice --group-name developers

# Role for EC2 with a customer managed policy
aws iam create-role --role-name app-ec2-role --assume-role-policy-document file://ec2-trust-policy.json
aws iam create-policy --policy-name read-app-artifacts --policy-document file://read-app-artifacts.json
aws iam attach-role-policy --role-name app-ec2-role \
  --policy-arn arn:aws:iam::123456789012:policy/read-app-artifacts

# Temporary credentials, permissions boundaries and policy testing
aws sts assume-role --role-arn arn:aws:iam::123456789012:role/app-ec2-role --role-session-name demo
aws iam put-user-permissions-boundary --user-name alice \
  --permissions-boundary arn:aws:iam::123456789012:policy/dev-boundary
aws iam simulate-principal-policy --policy-source-arn arn:aws:iam::123456789012:role/app-ec2-role \
  --action-names s3:GetObject s3:DeleteObject --resource-arns "arn:aws:s3:::my-app-artifacts/*"

# Access Analyzer and credential hygiene
aws accessanalyzer create-analyzer --analyzer-name account-analyzer --type ACCOUNT
aws accessanalyzer validate-policy --policy-type IDENTITY_POLICY \
  --policy-document file://read-app-artifacts.json
aws iam update-access-key --user-name alice --access-key-id AKIAIOSFODNN7EXAMPLE --status Inactive
```

## Terraform example

```hcl
terraform {
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
  }
}

provider "aws" { region = "ap-south-1" }

# Trust policy: only the EC2 service may assume the role
data "aws_iam_policy_document" "ec2_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "app" {
  name               = "app-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_trust.json
}

resource "aws_iam_policy" "read_artifacts" {
  name = "read-app-artifacts"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:ListBucket"], Resource = "arn:aws:s3:::my-app-artifacts" },
      { Effect = "Allow", Action = ["s3:GetObject"], Resource = "arn:aws:s3:::my-app-artifacts/*" }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "app_read" {
  role       = aws_iam_role.app.name
  policy_arn = aws_iam_policy.read_artifacts.arn
}

resource "aws_iam_instance_profile" "app" {
  name = "app-ec2-profile"
  role = aws_iam_role.app.name
}
```

Policies can be written with `jsonencode()` or with the `aws_iam_policy_document` data source; both produce valid JSON and surface syntax errors at plan time instead of at apply time.

## Key takeaways

- IAM answers two questions for every request: who is calling (authentication) and whether the call is permitted (authorization).
- Users hold long-term credentials, groups organise users, and roles provide temporary credentials - roles are the default choice for workloads and federation for people.
- Policies are JSON documents built from `Version`, `Statement`, `Effect`, `Action`, `Resource` and optional `Condition`; resource-based policies add `Principal`.
- Evaluation always resolves as explicit deny > explicit allow > implicit deny.
- Permissions boundaries, SCPs and RCPs only limit permissions; they never grant them.
- Least privilege, MFA, no root access keys, short-lived credentials and IAM Access Analyzer are the baseline for a secure account.
- Managing IAM with Terraform makes access changes reviewable and repeatable.

## References

- [What is IAM?](https://docs.aws.amazon.com/IAM/latest/UserGuide/introduction.html)
- [IAM users](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_users.html)
- [IAM user groups](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_groups.html)
- [IAM roles](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles.html)
- [Policies and permissions in IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html)
- [IAM JSON policy element reference](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements.html)
- [Policy evaluation logic](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html)
- [Permissions boundaries for IAM entities](https://docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_boundaries.html)
- [Service control policies (SCPs)](https://docs.aws.amazon.com/organizations/latest/userguide/orgs_manage_policies_scps.html)
- [Security best practices in IAM](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [Using IAM Access Analyzer](https://docs.aws.amazon.com/IAM/latest/UserGuide/what-is-access-analyzer.html)
- [Attribute-based access control (ABAC)](https://docs.aws.amazon.com/IAM/latest/UserGuide/introduction_attribute-based-access-control.html)
- [What is IAM Identity Center?](https://docs.aws.amazon.com/singlesignon/latest/userguide/what-is.html)

<!-- HANDS-ON -->
