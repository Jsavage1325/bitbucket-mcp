## Architecture
- A design pattern must be chosen before coding where applicable (state the pattern in the PR/ADR).
- ADR required for non-trivial changes.
  - Any meaningful architectural decision must have an ADR (1–2 pages).
  - Include: context, decision, alternatives, consequences.
- Explicit non-functional requirements (baseline):
  - Latency, availability, cost constraints, scaling expectations, RTO/RPO, data retention.
- Dependency boundaries:
  - Keep domain logic isolated from infrastructure/framework code.
  - No AWS SDK calls in core domain modules; wrap behind interfaces/adapters.
- Event-driven rules (if applicable):
  - Idempotency keys required.
  - Deduplication strategy documented.
  - Ordering expectations documented.
  - Retry policy and DLQ policy documented.
  - Exactly-once vs at-least-once assumptions documented.

## Coding
- TDD required:
  - Extract requirements into unit tests.
  - Follow red -> green -> refactor.
- Readable code without comments; add comments only where the code is not exceptionally clear.
- Code should be DRY and extensible.
- Ruff formatted (Python).
- Use `uv` for Python package management.
- Logging and monitoring throughout the system, with CloudWatch enabled.
  - Sentry can be added for larger or more critical applications.
- Preferred libraries:
  - SQLModel when an ORM is required.
  - Pydantic for validation - for lambdas remain lightweight and use data classes.
  - Tenacity for retry logic.
  - pytest - all tests should be tagged, unit, integration or smoke.
  - Prefer httpx over requests
- Error handling standards:
  - No naked `except:`.
  - Errors must either be handled or re-raised with context.
  - Define a consistent error taxonomy (domain vs infra vs validation).
- Configuration rules:
  - No environment reads (`os.getenv`) inside core logic; config assembled at entrypoints.
  - Fail fast on missing config.
- Linting/formatting scope (Python):
  - `ruff` line length: 100.
  - `ruff` import sorting: enabled (`I`).
  - `ruff` ruleset:
    - select: `E`, `F`, `I`, `B`, `UP`, `N`, `S`, `C90`, `SIM`, `PL`, `RUF`.
    - ignore: `S101` (allow `assert` in tests only).
- Testing pyramid:
  - Unit tests required.
  - Integration tests for AWS interactions (LocalStack or real AWS sandbox).
  - Smoke tests post-deploy.
  - Unit tests should NEVER touch live services.
- Test conventions:
  - Naming: `test_<behavior>`.
  - Use AAA or Given/When/Then.
  - Avoid mocking implementation details; mock boundaries only.
- Use python with modern python type hints

## CI/CD
- Bitbucket is the CI/CD tool.
- Packaging of Lambdas and Docker image builds must be triggered by Terraform, NOT the Bitbucket pipeline.
- Preferred build/package/deploy flow (all compute types):
  - **Build**: Terraform `null_resource` triggers `build.sh` on every plan/apply via a timestamp trigger.
  - **Package**:
    - Lambda: `uv` installs deps into `build/package/<service-name>/`, script copies source; `data.archive_file.<service-name>` zips it.
    - Container (Batch/ECS): `build.sh` builds the image, tags it `{stack-name}-{env}-{hash}`, pushes to ECR; `aws_ecr_image` references the digest.
  - **Deploy**: Terraform resource (`aws_lambda_function` / `aws_batch_job_definition` / `aws_ecs_task_definition`) references the zip hash or image digest and depends on the build `null_resource`.
  - **CI/CD**: Bitbucket pipelines run Terraform plan/apply only; all builds happen during those Terraform runs, not in pipeline scripts.
- Stages/environments:
  - `qa` branch: `qa-plan`, `qa-apply`.
  - `main` branch: `live-plan`, `live-apply`.
  - Prior to `qa-plan`, run unit tests, `ruff`, and `terraform fmt`.
- Quality gates (must pass):
  - Unit tests.
  - `ruff`.
  - `pip-audit` (vulnerability scan).
  - Type check (if adopted).
  - `terraform fmt` and `terraform validate`.
- Plan/apply safety:
  - Manual approval gates for `*-apply` (especially live).
  - Require a clean plan (no drift surprises) before apply.
  - Store plan artifacts and link them to PRs/builds.
- Versioning/release:
  - Artifacts must be versioned (semver + git sha recommended).
  - Live deployments must reference a tag.
- Rollback strategy required:
  - Lambda: previous version/alias.
  - ECS/ECR: previous image digest.
  - Terraform: define mitigations; state rollback is hard.

## Infra / Terraform
- Artifact naming: `{stack-name}-{env}-{hash}`.
  - Add timestamp/build number only if collisions are possible.
  - Hash must be content-based; avoid time-based hashes.
- We have some variables we have saved in bitbucket as project-wide variables. These should be used in the bitbucket pipeline
    - QA: AWS_ACCESS_KEY_ID_QA
      live: AWS_ACCESS_KEY_ID
    - QA: AWS_SECRET_ACCESS_KEY_QA
      live: AWS_SECRET_ACCESS_KEY
    - QA: DATA_STATE_BUCKET_QA
      live: DATA_STATE_BUCKET_LIVE
    - QA: DATA_ENV_QA
      live: DATA_ENV_LIVE
- Terraform secrets:
  - Pull from AWS Secrets Manager.
  - Secret names come from tfvars.
  - tfvars are the source of truth for app variables.
  - There should be live.tfvars and qa.tfvars which contain infra truths
    - vpc_id = "vpc-007d0afc723dbf977"
      private_subnet_ids = [
        "subnet-07639910743c7e5f6",
        "subnet-070ce1c50cc106ee0",
        "subnet-01f44334156e92379"
      ]
- Builds:
  - Lambda and Docker builds triggered by Terraform.
  - Builds must not be bash scripts, and must be POSIX compliant (#!/bin/sh)
  - Always-trigger via timestamp allowed only when reproducibility isn't possible.
- State & locking:
  - Use S3 backend + DynamoDB lock with encryption and strict access policy.
- Module standards:
  - Inputs/outputs documented.
  - No mega-modules.
  - Modules versioned (tagged) or pinned commits.
- Secrets handling:
  - Never output secrets in Terraform outputs.
  - Avoid secrets in state where possible; call out unavoidable cases.
- CloudWatch log retention must be set (no "never expire" by default).
- IAM:
  - Least privilege required; wildcard permissions must be justified in code review/ADR.
- Environments and drift:
  - Define drift detection approach (scheduled plan-only run, etc.).
- Group terraform modules logically. Ask the user for confirmation of structure.
- Add tags in locals of main.tf file. Example tags & locals:
  locals {
    project_name = "PROJECT NAME"                                 -- this should be changed by user, please prompt
    stack_name   = replace(lower(local.project_name), " ", "-")
    environment  = lower(terraform.workspace)
    random_id    = random_id.stack.hex
    region       = "eu-west-1"

    tags = {
      Name        = "${local.stack_name}"                         -- this should be changed by user, please prompt
      Project     = local.project_name
      Service     = "Data"                                        -- constant - this is the team that manages the resource
      Environment = upper(terraform.workspace)
      ManagedBy   = "Terraform"
      RepoUrl     = upstream-origin-url                           -- populate using the upstream origin URL
    }
  }


## Observability
- Structured logging (JSON).
- Required log fields:
  - `service`, `env`, `version`, `request_id`/`correlation_id`, `tenant` (if relevant).
- Metrics minimums:
  - Invocation count.
  - Duration (p50/p95/p99).
  - Error count and error rate.
  - Throttles.
  - DLQ depth (if event-driven).
- Use tenacity to handle retry logic
- Tracing:
  - Use X-Ray.
  - Propagate correlation IDs across async boundaries.
- Alarms per service:
  - Error rate spike.
  - Latency regression.
  - DLQ depth > threshold.
  - No events processed for X minutes (dead consumer).
- Notification routing must be defined (Slack/email/on-call).
- Log retention: explicit retention period per env (qa shorter, live longer).

## Security & Compliance
- Secure defaults:
  - Encryption at rest + in transit required.
  - Public access must be explicitly justified.
- Dependency management:
  - Vulnerability scanning (pip-audit / dependabot / Snyk).
  - Pin dependencies with hashes where supported.
- Secrets hygiene:
  - No secrets in repo, CI vars, or logs.
  - Redaction rules for logs.
- Threat modeling required for new externally-facing endpoints or sensitive data flows.

## Repo & Developer Experience
- Project structure conventions:
  - `src/`, `tests/`, `terraform/`, `scripts/`, `docs/`, `src/lib` (for modules).
  - One obvious entrypoint per lambda/service.
- Makefile is required with golden-path utilities:
  - `make run` - run local application (if applicable)
  - `make test` - run local unit tests
  - `make integration-test` - run integration tests (if applicable)
  - `make smoke` - run smoke tests (if applicable)
  - `make lint` - run ruff locally
  - `make terraform-lint` - run terraform fmt
  - `make terraform-validate` - run terraform validate
  - `make local` - run full local stack (if feasible)
- Local dev:
  - Document how to run locally (docker-compose/SAM/localstack).
  - Provide `.env.example` (no secrets).
- Documentation:
  - `RUNBOOK.md` per service: alarms, dashboards, common failure modes,
    rollback, redeploy steps.
- Process / quality:
  - Definition of Done:
    - Tests added/updated.
    - Logging/metrics added.
    - Alarms configured (live).
    - Runbook updated.
    - Terraform plan reviewed.
    - Smoke tests passing in QA.
  - Code review rules:
    - Require 1–2 approvals depending on risk.
    - Reviewer checklist: security, IAM, logging, tests, backward compatibility.
  - Backward compatibility:
    - Migration strategy for data/schema changes.
    - Event/API versioning rules (don’t break consumers).

## Code Review Agents

DeltaGuard runs two review agents on every PR commit automatically:

- **`agents/generic-review.md`** — general code quality, bugs, configuration, and standards.
- **`agents/security-review.md`** — security-focused pass: injection, IAM, secrets, crypto, supply chain.

Both agents run on every commit. The security agent is expected to return an empty comments array when no issues are found — a clean result is a valid and expected outcome. Neither agent blocks merges; they post informational comments only.

The active agent is selected via the `REVIEW_MODE` environment variable. To run both agents per commit, invoke the worker twice with different `REVIEW_MODE` values, or extend the runner to loop over all agents.

## General Instructions
- Before reading requirements, raise any unclear items or requirements that need clarification.
- Create a deployment script for QA: `terraform/terraform_qa.sh`.
  - Pull creds from AWS.
  - `terraform init` + plan/apply for QA.
- Where applicable (especially event-driven systems), add post-deploy smoke tests for core functionality.
