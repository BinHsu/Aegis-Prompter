# First-Round Interview Cheatsheet

> **How to use:** Each question has a ready-to-speak English script.
> Memorize the core answer. The bullet points are your backup if you blank out.
> ⚠️ = watch-out / tricky framing reminder

---

## Q0. Self-Introduction (開場白)

**Script:**
> "I'm a Senior Software Architect with 15 years of experience building mission-critical systems across the full stack — from cross-platform C++ edge SDKs to large-scale AWS cloud infrastructure. My unique strength is the ability to bridge hardware constraints and cloud scale — most engineers live in one world or the other. I'm now relocating permanently to Germany for my children's education, and I'm fully committed to a long-term career here."

**Backup bullets:**
- 10 years at VIVOTEK: C++ SDK, OpenVPN device management, 1,000+ cameras
- 5 years at E2 Nova: full ownership of 5 AWS accounts, 3 regions, 4–5M daily requests
- AWS SAP certified (March 2026), ISO 27001/27701 audits 3 consecutive years

---

## Q1. Why Germany / Why relocate? (為什麼來德國？)

**Script:**
> "I'm relocating primarily for my children's education in the German school system. This is a multi-year family commitment — once the children are enrolled, the family stays. I specifically chose Berlin for its strong tech community and English-friendly environment while my German improves, but I'm open to all of Germany."

**If asked "Will you leave after 3 months?":**
> "No. The children's school enrollment is the anchor. Leaving early would disrupt their education — that's the strongest commitment signal I can give."

**Bonus (if asked about German connection):**
> "Throughout my career I've worked with German-engineered technology — Siemens industrial protocols, Bosch sensor integration, and VIVOTEK hardware certified to EN50155 deployed in European transit systems."

---

## Q2. Why should we hire you? (為什麼是你？)

**Script:**
> "I bring a unique hardware-to-cloud perspective. Unlike most cloud architects who only see the cloud layer, I understand low-level hardware constraints from a decade building C++ edge SDKs. This means I design cloud systems that are truly optimized for the underlying hardware — reducing latency and cost in ways a purely cloud-native engineer wouldn't think to look for."

**Backup bullets:**
- Not just theory: 479 CloudFormation templates, 155 Jenkins pipelines, 49 ASGs — inherited and evolved
- Shipped under pressure: ProxySQL eliminated 6,000+ daily timeouts without any app code changes
- ISO 27001 + DR drill ownership 3 years running

---

## Q3. Biggest professional achievement (最大成就)

**Script:**
> "At E2 Nova, I identified a database bottleneck causing over 6,000 connection timeouts per day. Rather than rewriting 20+ microservices, I designed an infrastructure-layer solution: a ProxySQL connection-pooling cluster provisioned entirely as Infrastructure as Code. It compressed 5,000 static DB connections down to 29 persistent ones, improved query P95 from 53% to 87% within 5ms SLA, and eliminated all timeouts — with zero application code changes. That stability directly supported the company's IPO preparation."

---

## Q4. Biggest strengths (強項)

**Script:**
> "My biggest strength is the ability to bridge hardware constraints and cloud scale — most engineers live in one world or the other. I have deep production experience at both ends: high-concurrency C++ at the edge and large-scale AWS infrastructure. This lets me architect end-to-end systems where others only see one layer, which significantly reduces the communication overhead between hardware and cloud teams."

**Secondary strength (if asked for more):**
> "I'm also unusually comfortable inheriting complex systems. At E2 Nova I became the single engineer who fully understood a 5-account, 3-region platform. That kind of full-context ownership is rare and very hard to replace."

---

## Q5. Biggest weakness (弱點)

**Script:**
> "My biggest weakness right now is German fluency. My last five years were in global English-speaking environments. Because my family is relocating permanently, I'm taking daily classes and targeting B1 within 18 months of starting a role."

⚠️ **Do not apologize. State it matter-of-factly and pivot to the commitment.**

---

## Q6. Tell me about a failure / mistake (失敗經驗 STAR)

**Script:**
> "A developer pushed a MySQL ENUM rename to production — what looked like a metadata change actually triggered a full table rewrite and locked the entire platform for 60 minutes. My mistake was hesitating 10 minutes between 'wait for it to finish' and 'kill the process.' I learned that hesitation on a live incident is itself a failure. After resolving it, I built a systemic fix: all schema migrations now run against an automated, production-sized anonymized clone before release. The clone is GDPR-compliant — real PII is masked before it ever leaves production. We also added a CI check that flags ALGORITHM=COPY risks in pull requests."

**Key insight to land:**
> "I don't just fix failures. I build systems that make them impossible to repeat."

---

## Q7. Tell me about a conflict / difficult coworker (衝突處理)

**Script:**
> "I first make sure we both step back to cool down — technical arguments get worse when they become personal. Then I shift the conversation to the specific technical constraints: what are the actual bottlenecks, what are the tradeoffs? Once we're aligned on the constraints, the solution usually becomes obvious. I always keep communication objective and document the outcome so there's no ambiguity later."

---

## Q8. Tell me about leadership / mentoring (帶人經驗)

**Script:**
> "At D2 Nova, I noticed that new engineers were taking six months to become productive. I identified the root cause: knowledge was siloed. I built a structured two-month technical onboarding curriculum — documented, peer-reviewed, openly shared. New engineers adopted it and ramp time dropped from six months to two. I also led the handoff of DeviceCenter to a three-person offshore team in India, which required me to translate institutional knowledge into written documentation under a deadline."

---

## Q9. What kind of environment do you work best in? (偏好工作環境)

**Script:**
> "I thrive in high-discipline, structured environments. When managing complex systems, rigorous documentation, strict CI/CD pipelines, and thorough peer review aren't overhead — they're what makes everything else possible. I'm also comfortable being the person who sets that standard if it doesn't exist yet."

---

## Q10. Where do you see yourself in 5 years? (五年後)

**Script:**
> "In five years I see myself as a Technical Principal, having built a fully automated, carrier-grade infrastructure that's become a competitive advantage for the company. My goal is to bridge hardware engineering and cloud services — and to have grown the team around me so that knowledge is shared, not siloed."

---

## Q11. What can we expect from you? (錄用後能期待什麼)

**Script:**
> "You can expect me to master your existing systems quickly — I have a track record of inheriting complex platforms and becoming the go-to person. From there I'll systematically improve automation, reduce manual operations, and improve observability. I won't introduce changes for the sake of it; every improvement will be tied to a production problem."

---

## Q12. Are you okay with on-call? (接受 On-Call 嗎)

**Script:**
> "Yes, I'm comfortable with on-call if it's structured professionally. From managing a 24/7 AWS platform, I know that sustainable on-call requires a clear Rufbereitschaft allowance, strict adherence to the 11-hour legal rest period, and a night shift premium — not just 1-to-1 time in lieu."

---

## Q13. Salary expectations (薪資期望)

> ⚠️ **Calibrate by role level — do not give a number first if you can avoid it.**

**Top-tier / Architect roles (Siemens, Bosch, Deutsche Bank):**
> "Based on 15 years of end-to-end architect experience, I'm targeting €85,000–€95,000. That said, I'm flexible depending on the full package and project scope."

**Standard DevOps / Platform / Senior SWE roles:**
> "I'm targeting around €75,000–€85,000 for a senior individual contributor role. The exact number is flexible — I prioritize technical challenge and team culture."

**Deflect if needed:**
> "I'm open to negotiating the full compensation package. My priority is finding a role with meaningful technical challenges where I can build a long-term career in Germany."

---

## Q14. Are you currently employed? / Current company (目前就業狀態)

**Script:**
> "I left E2 Nova in March 2026 to relocate to Germany on my Chancenkarte. I'm currently in Berlin, fully available, and actively interviewing."

⚠️ **Do not say "N/A" in forms — say "E2 Nova (departed March 2026)" or leave blank and explain verbally.**

---

## Q15. Work authorization (工作簽證)

**Script:**
> "I'm currently on a German Chancenkarte (Opportunity Card), which authorizes me to work independently without employer sponsorship. Once I receive an employment contract, I convert it to an Aufenthaltserlaubnis and eventually a Blaue Karte EU. No sponsorship required from the employer."

---

## Q16. What would your former colleagues and manager say about you? (前同事與主管眼中的你)

**Script:**
> "They'd say I'm the person who makes complex things understandable, and who refuses to stop at the quick fix. I document everything, I dig into root causes, and I push for solutions that make the problem impossible to repeat. My former manager would probably say I'm reliable — not necessarily the fastest firefighter in the room, but the person who makes sure the fire never happens again. My colleagues would likely add that I have high standards for documentation and process, because I believe knowledge trapped in one person's head is a liability. If you want someone to patch things quickly and move on, I'm not your best choice. If you want someone to build a system where patching becomes unnecessary — that's where I operate."

⚠️ **The last two sentences are the key.** They reframe the "not a firefighter" as a deliberate choice, not a gap. Own it.

---

## Quick Reference — Key Numbers

| Metric | Value |
|--------|-------|
| Experience | 15 years total (10 VIVOTEK + 5 E2 Nova) |
| Daily traffic (E2 Nova prod) | 4–5 million HTTP requests |
| CloudFormation templates | 479 |
| Jenkins pipelines | 155 (38,900 lines) |
| ASGs managed | 49 |
| DB connections (before ProxySQL) | 5,000 static |
| DB connections (after ProxySQL) | 29 persistent |
| Daily timeouts eliminated | 6,000+ |
| DB P95 improvement | 53% → 87% within 5ms |
| Cameras managed (DeviceCenter) | 1,000+ (arch supports 3,000) |
| Onboarding ramp improvement | 6 months → 2 months (−66%) |
| ISO 27001/27701 DR drills | 3 consecutive years, zero major NCs |
| AWS certifications | SAP (March 2026) + SAA + ISC2 CC |
| German level | A1, targeting B1 within 18 months |
