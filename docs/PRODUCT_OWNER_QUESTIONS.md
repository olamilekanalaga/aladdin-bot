# Product Owner Questions

These questions could not be answered from repository evidence. Documentation and reliability work do not need to stop while answers are gathered.

## Product objective

1. **What exact trading decision should the public Telegram alert optimise?**  
Why: 2x-from-first-spotted probability and remaining upside after entry are different objectives.  
Depends on: future rule evaluation and KPI definition.  
Repository options: current 1.4x confirmation, late-entry cap, or later ranked intelligence.

2. **Is Vlak Bot only an alert/monitoring product, or is automated execution a long-term goal?**  
Why: execution would introduce custody, risk, latency and compliance requirements absent today.  
Depends on: architecture and security boundary.

## Users and product scope

3. **Who is the supported user: private operator, invited trading community, or public service?**  
Why: changes access control, uptime, support and disclosure requirements.

4. **Should the GitHub repository remain public?**  
Why: secrets are excluded, but trading logic and operational safeguards are visible.  
Options: public engine, private repository, split public/private components.

## Trading and research objectives

5. **Are the current 1.4x minimum and 2.5x maximum frozen production rules?**  
Why: developers need to know whether tests should encode them as contractual invariants or temporary configuration.

6. **What minimum evidence is required before research can affect public alerts?**  
Why: prevents in-sample rules or leakage from becoming production decisions.  
Suggested options: chronological validation, live shadow sample, minimum sample size, explicit approval.

## Operational ownership

7. **Who responds to Vlak API outage, Telegram failure, database growth and missed daily summaries?**  
Why: alerts need an escalation owner and acceptable response time.

8. **What uptime and maximum acceptable alert delay are required?**  
Why: determines deployment, health monitoring and API cadence.

9. **Where is the approved private database backup stored and how long must history be retained?**  
Why: GitHub intentionally contains no runtime database.

## Developer responsibility

10. **Can the incoming developer access test Vlak/Telegram credentials and a sanitised production-shaped database?**  
Why: contract and migration tests cannot be realistic without safe fixtures.

11. **Which components may the developer change independently, and who approves trading-rule or Telegram changes?**  
Why: defines review boundaries and avoids accidental strategy changes.

## Production boundaries

12. **Should production remain on the current Windows PC or move to a managed server?**  
Why: process restart, persistence, backup, security and monitoring design depend on it.

13. **Should deprecated shadow Strong Watch code be removed or preserved for future research?**  
Why: it currently increases complexity while disabled.

## Priorities

14. **After startup/test reliability, which comes first: deployment uptime, outcome accuracy, or new signal research?**  
Why: all are valuable, but simultaneous work increases risk.  
Recommendation: uptime/data integrity before new formations.

## Unresolved data definitions

15. **What upstream event exactly makes `completed_24h` authoritative?**  
Why: incomplete calls must not be counted as failures.

16. **What is the approved correction process when Vlak returns a conflicting first-call market cap or ATH?**  
Why: maxima are preserved monotonically, so bad upstream data needs an explicit correction path.

