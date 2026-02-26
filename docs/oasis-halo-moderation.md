# OASIS Halo Content Moderation

This document describes the content moderation system for OASIS Halo, the AI-powered Help Desk and Product Guidance Assistant for Onliest.ai.

## Purpose & Scope

OASIS Halo supports:
- Onliest Design Studio guidance
- Product A & Product B fashion design assistance
- Platform troubleshooting
- Order & account-related help (non-sensitive)
- High-level pricing explanation (non-confidential)

OASIS Halo does **not** function as:
- A general-purpose chatbot
- A political/religious discussion tool
- A medical/legal/financial advisor
- A confidential data disclosure channel

## Architecture

Content moderation uses a two-phase approach:

1. **Phase 1 (Deterministic)**: Regex-based rules in `app/services/policy_gate.py` for fast blocking of safety-critical content
2. **Phase 2 (LLM)**: Optional LLM classifier in `app/services/policy_agent.py` for nuanced classification of ambiguous cases

Safety-critical categories are handled by deterministic rules only (no LLM) for reliability.

## Policy Categories

### Allowed Categories (Allowlist)

| Category | Description | Example Prompts |
|----------|-------------|-----------------|
| Product Usage Help | Help using Onliest/OASIS features | "How do I change Product B sleeve style?" |
| Design Guidance | Creative design advice | "Suggest a Banarasi Product A for wedding" |
| Order Status | General order help | "How can I track my order?" |
| Pricing Explanation | High-level pricing logic | "Why is handloom more expensive?" |
| Platform Troubleshooting | UI/UX help | "My 3D mannequin is not loading" |
| Account Settings | Non-sensitive profile help | "How do I update my email?" |
| Designer Collaboration | Design collaboration help | "How do I share my mannequin?" |

### Restricted Categories (Blocklist)

| Category | Reason Code | Response Behavior |
|----------|-------------|-------------------|
| Abuse/Harassment | `ABUSE_HARASSMENT_BLOCKED` | Refuse + Redirect |
| Hate/Violence | `HATE_VIOLENCE_BLOCKED` | Strong Refusal + Log |
| Sexual Content | `SEXUAL_CONTENT_BLOCKED` | Refuse |
| Self-Harm | `SELF_HARM_DETECTED` | Supportive refusal + crisis note |
| Illegal Instructions | `ILLEGAL_INSTRUCTIONS_BLOCKED` | Refuse |
| Prompt Injection | `PROMPT_INJECTION_BLOCKED` | Refuse + Continue normally |
| Political/Religious | `DISALLOWED_OFF_DOMAIN` | Redirect |
| Internal Secrets | `DISALLOWED_CONFIDENTIAL` | Refuse |

## Response Templates

### Safety-Critical Refusals

- **Hate/Violence**: "I cannot assist with content involving hate speech, violence, or threats..."
- **Self-Harm**: "I'm concerned about what you're going through. Please reach out to Onliest Support at support@onliest.ai or call our wellness line..."
- **Abuse**: "Please communicate respectfully. I'm here to help with Onliest products..."
- **Illegal/Sexual**: "I cannot provide assistance with that request. I can help with fashion design, product support, and order assistance."

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_CONTENT_MODERATION` | `true` | Enable/disable content moderation |
| `SELF_HARM_SUPPORT_EMAIL` | `support@onliest.ai` | Email for self-harm support outreach |
| `SELF_HARM_SUPPORT_PHONE` | `1-800-XXX-XXXX` | Phone for wellness line |
| `CONTENT_MODERATION_LOG_LEVEL` | `WARNING` | Log level for moderation events |

## Testing

### Unit Tests

Run the comprehensive moderation test suite:

```bash
PYTHONPATH=. pytest app/tests/test_oasis_halo_moderation.py -v
```

Run policy regression tests:

```bash
PYTHONPATH=. pytest app/tests/test_policy_regression.py -v
```

### Golden Test Cases

Golden conversation cases are stored in the `golden_conversation_case` table and used by the release control golden gate. To add cases, run the migration:

```bash
prisma migrate deploy
```

The migration `20260223120000_oasis_halo_golden_cases` seeds:
- Blocked cases: abuse, hate, self-harm, sexual, illegal, prompt injection
- Allowed cases: design, order, product, account

### Golden Gate

To run the golden gate (validates policy decisions against golden cases):

```bash
# Via API or release control service
POST /api/v1/chat/ops/release/golden-run
```

## Audit Logging

All policy decisions are logged to the `policy_audit` table with:
- `policy_intent` - Intent classification
- `policy_domain` - Domain classification (ONLIEST_FASHION, OASIS_PUBLIC, OFF_DOMAIN, CONFIDENTIAL, UNSAFE)
- `reason_code` - Block reason code
- `allow` - Whether the request was allowed
- `decision_source` - `rules_block`, `llm_classifier`, or `llm_fallback_rules`

## Pattern Matching

Safety-critical patterns are checked first in `classify_intent()`:

1. SELF_HARM
2. HATE_VIOLENCE
3. ABUSE_HARASSMENT
4. SEXUAL_CONTENT
5. ILLEGAL_INSTRUCTIONS
6. PROMPT_INJECTION
7. (then allowed/off-domain patterns)

This ensures safety-critical content is blocked before any allowed pattern matching.

## Files

- `app/services/policy_gate.py` - Deterministic policy logic, patterns, response templates
- `app/services/policy_agent.py` - LLM classifier integration, decision matrix
- `app/core/config.py` - Configuration options
- `app/tests/test_oasis_halo_moderation.py` - Comprehensive test suite
- `app/tests/test_policy_regression.py` - Regression tests
- `prisma/migrations/20260223120000_oasis_halo_golden_cases/migration.sql` - Golden case seed
