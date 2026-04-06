# Bin Hsu — Career Transition Profile (Updated 2026-03-20 v2)

> Source: v1 profile + IaC repo analysis + PDF design docs + web research + interview Q&A
> Previous version: `~/Documents/bin_hsu_profile.md`
> This file is the **session continuity anchor** — resume/cover letter work references this file.

---

## Personal Info
- **Name:** Bin Hsu
- **Email:** pcpunkhades@gmail.com
- **Mobile:** +886 970 772375 (Taiwan, until ~2026-03-25)
- **Landing date:** 2026-03-25 (Berlin)
- **Anmeldung:** 2026-03-27 (scheduled)
- **Visa:** Chancenkarte issued **2026-03-18** (Visa D, 1 year); last day at E2 Nova 2026-03-23; extend via employment → Aufenthaltserlaubnis → Blaue Karte EU → Niederlassungserlaubnis

### ⚠️ Why Germany / Why Berlin — prepared answer for HR/recruiter
> **The real reason (use this):** Relocating primarily for **children's education** — committed to having children complete at least one year of German Kindergarten before entering the German primary school system. This is a **multi-year family commitment**, not a trial. Once in the German school system, the family stays.
>
> **Why Berlin specifically:** Strong IT industry concentration and the largest English-speaking expat tech community in Germany — lowers the initial language barrier while German improves. However, **target is all of Germany**, not just Berlin. Open to Munich, Hamburg, Stuttgart, Frankfurt.
>
> **Recruiter concern addressed:** "Will you leave after 3 months?" → No. The children's school enrollment anchors the family. Leaving early would disrupt the children's education — the strongest possible commitment signal.
>
> **If asked about German connection:** "I've been working with German-engineered technology stacks throughout my career — Siemens industrial protocols, Bosch sensor integration, and VIVOTEK surveillance hardware that's certified to EN50155 (German railway standard) and deployed in European transit systems."

---

## Education
| Degree | Field | School |
|--------|-------|--------|
| M.S.E.E. | Electrical Engineering | National Taipei University of Technology (台北科技大學) |
| B.S. | Mathematics & Information Education | National Taipei University of Education |

---

## Certifications
| Cert | Status | Date |
|------|--------|------|
| **AWS Certified Solutions Architect – Professional (SAP)** | ✅ Certified | **2026-03-13** |
| AWS Certified Solutions Architect – Associate (SAA) | ✅ Certified | prior |
| ISC2 Certified in Cybersecurity (CC) | ✅ Certified | prior |
| Google Cybersecurity Professional Certificate | ✅ Completed | prior |

> ⚠️ **Resume/LinkedIn action:** Update SAP from "Pursuing" → "Certified (March 2026)"

---

## Languages
| Language | Level | Notes |
|----------|-------|-------|
| Mandarin | Native | — |
| English | Professional Working | IELTS Reading 8.5 (C2), Overall 6.5–7.0 |
| German | **A1 – Actively Learning** | Daily study; targeting B1 within 18 months of employment (resume wording) |

---

## Work Experience — Full Detail

### VIVOTEK (2011–2021) | Senior Software Engineer | 10 years
**Company context (for German market):** IP surveillance hardware manufacturer · Delta Electronics wholly-owned subsidiary (TWSE: 2308) · deployed in **120+ countries** (verified via vivotek.com, 2026-03) · 300+ global distribution partners · 6 consecutive years Taiwan Top 40 Global Brand

#### System 1: GAEA — Crash-Safe Distributed Storage SDK
- A storage engine (MP3 + SQLite3) deployed across cameras, web, and VMS for recording and playback
- **Tech:** C/C++ + Boost
- **Core guarantee:** Directory integrity survives power cuts and mid-write HDD removal; user can mount the directory on any CMS/VMS even after abrupt shutdown
- **Resume framing:** "Designed and shipped crash-safe on-device storage SDK (C/C++ + Boost) deployed across cameras, NVR, and VMS — guaranteed data integrity under power failure and hot-swap HDD scenarios"
- **Germany relevance:** Exactly the resilience engineering Siemens/Bosch OT teams value

#### System 2: VAST1 — Recording Server (Maintained)
- Cross-platform recording server; inherited and maintained (did NOT write from scratch)
- **Tech:** C/C++ + wxWidgets + Boost (cross-platform Linux/Windows)
- ⚠️ Interview note: "maintained and extended" — not "built from scratch"
- **Resume framing:** "Maintained cross-platform recording server (C/C++ + wxWidgets + Boost) — owned ingest pipeline and playback reliability"

#### System 3: DeviceCenter — OpenVPN-based Global Camera Management Platform (Maintained/Extended)
- Based on VAST2 (which user did not build); user added OpenVPN client SDK and extended platform
- **Tech:** C/C++ + Qt + Boost (cross-platform)
- Wrote cross-platform OpenVPN client SDK in C; creates large-scale private overlay network for remote firmware update, config push, and multi-tenant management by integrators
- **Scale:** Architecture supports up to 3,000 cameras; personally observed 1,000+ camera deployment (recalled concern about Class C address space exhaustion at that scale)
- **Known public deployments during tenure:**
  - Thailand MRT Red Line — 570 cameras across trains (EN50155 railway standard)
  - Transit Australia Group (Queensland) — largest privately owned public transport depot
  - Japan Keihan Bus — LPR systems at bus depots
  - BPCL India — 1,000 petroleum stations, 5,000 cameras
  - Vehicle store-and-forward — cameras in moving vehicles (no live connectivity); batch upload on docking/station arrival or manual HDD swap; CMS ingests immediately on reconnect
  - ⚠️ Note: Use "large-scale Asia-Pacific deployments in transportation and utilities" — do not attribute specific deployments without confirmation
- **Team:** Led 3-person offshore team (2 engineers + 1 tech manager, India vendor) for DeviceCenter knowledge transfer
- **Resume framing:** "Architected OpenVPN-based device management platform managing 1,000+ IP cameras globally across transportation, petroleum, and enterprise — wrote embedded OpenVPN client SDK in C; led offshore team handoff"

#### MQTT
- Has MQTT exposure (relevant for IIoT / Industry 4.0 discussions)
- No OPC-UA / PLC experience yet — frame as "familiar with IIoT protocols, deepening OPC-UA knowledge"

---

### D2 Nova → E2 Nova (Apr 2021–Mar 2026) | 5 years
> **Company context:** D2 Nova was a Taiwan subsidiary of D2Tech (US). Rebranded to E2 Nova in 2023, restructured as independent Taiwan company for IPO preparation. Same engineering team, same product (evox platform). **5,008 enterprise clients, 33,031 users** at time of departure.

> ⚠️ **Interview prep — "Did you build all this from scratch?"**
> The platform infrastructure (5 AWS accounts, 3 regions, 479 CF templates, 155 Jenkins pipelines, 49 ASGs) was **inherited**. The E2 Nova codebase and IaC were established before I took DevOps ownership in 2023. My contribution was: **full platform ownership** (the single person who understood every component), plus **specific major architectural improvements** I designed and shipped:
> - ✅ ProxySQL cluster (designed + implemented)
> - ✅ RTPEngine cluster decoupling (designed + implemented)
> - ✅ ISBC cluster NLB/ASG/Lambda drain design (designed + implemented)
> - ✅ Grafana Alert IaC pipeline (designed + implemented)
> - ✅ LION-UT Kubernetes ephemeral test env (designed + implemented)
> - ✅ Reverseproxy ECS redesign (architecture designed, not deployed)
> - ✅ GreenBlueSwitcher migration framework (D2 Nova period, designed + implemented)
> - ✅ **Taipei region expansion (ap-east-2)** — led end-to-end migration from Tokyo local zone to AWS ap-east-2; fully handed over to team on departure
>
> **Interview framing:** "I inherited a complex multi-account platform and became the single engineer with full end-to-end understanding of it. I then drove several major architectural improvements — each one solving a specific production problem."

#### Role transition (2023): Senior Backend Engineer → DevOps Engineer
- **Deliberate career investment:** Voluntarily transitioned to DevOps to acquire Cloud infra, CI/CD, Kubernetes, SIP flows, and platform engineering depth
- Not a lateral move — a strategic upskilling while the company was scaling for IPO
- **Interview narrative:** "As the company prepared for IPO listing and needed to harden its infrastructure, I took ownership of the DevOps function — treating it as a structured learning investment in cloud-native engineering."

### D2 Nova (Apr 2021–2023) | Senior Backend Engineer | 2 years

#### Flagship: Migration System (GreenBlueSwitcher)
- **Design doc:** `~/Downloads/OPS-Migration + Switcher — DevOps Design Document-100326-010836.pdf`
- **Problem:** Manual, error-prone deployment upgrades ("migration hell" EVOX-5818)
- **Solution:** Flask app (GreenBlueSwitcher) on each reverseproxy EC2; Jenkins triggers by customer_id_list only; idempotent patches, multi-branch simultaneous support, UUID polling for async results
- **Architecture:** Jenkins → GreenBlueSwitcher (load-balanced) → mig service API (new deployment) + customerExit API (old deployment) → DB version record
- **Resume framing:** "Designed zero-downtime customer migration framework (GreenBlueSwitcher) — idempotent patch system, single Jenkins trigger by customer list, no version pinning required"

#### Other D2 Nova work
- Zero Trust input validation + SQL injection prevention
- Privileged account behavior audit logging
- Onboarding: reduced ramp time 6 months → 2 months (66%) — mechanism: built structured technical training curriculum, openly shared with team; new engineers adopted and onboarded faster
- RESTful API optimization: 3× response time improvement

---

### E2 Nova (2023–2026) | DevOps Engineer | 3 years

#### Scope
Full ownership of Public VPC + Private VPC — BE/FE handles app layer only; everything else (networking, compute, security groups, IaC, CI/CD, DR) is DevOps.

**Infrastructure scale:**
- 5 AWS accounts (d2dev, d2evoxstg, d2evoxpre, d2evoxprod, d2service)
- 3 regions: ap-northeast-1 Tokyo (primary), ap-east-2 Taipei (secondary), us-east-1 (backup)
- 479 CloudFormation templates, 155 Jenkins pipelines (38,900 lines), 6 Terraform modules, 15 Helm charts
- 49 ASGs, 20+ microservices, 40–80+ instances per environment
- **Verified platform traffic (CloudWatch Logs Insights, evoxprod-reverseproxy Apache access logs, Mar 17–20 2026):** 4–5 million HTTP requests/day on weekdays — confirmed "millions of daily requests" framing in resume is accurate and defensible in interview

#### Flagship 1: ProxySQL Cluster
- **Design doc:** `~/Downloads/OPS-ProxySQL Cluster Operations-090326-032959.pdf`
- **Problem:** No connection pooling in apps → Aurora exhaustion → 6,000+ timeouts/day → browser timeouts; rewriting 20+ services not feasible
- **Solution:** Infrastructure-layer ProxySQL — 29 persistent backend connections multiplex thousands of short-lived frontend connections; port-based RO/RW routing; zero app code changes
- **Impact:** DB P95 within 5ms: 53% → 87% (+34%); 6,000+ daily timeouts eliminated; 5,000 static connections → 29 persistent
- **Resume framing:** "Introduced ProxySQL connection-pooling layer: compressed 5,000 static DB connections to 29 persistent, improved query P95 from 53% → 87% within 5ms SLA, eliminated 6,000+ daily timeouts — zero app code changes"

#### Flagship 2: RTPEngine Cluster
- **Design doc:** `~/Downloads/OPS-RTPengine Cluster — Architecture & Operations-180326-213012.pdf`
- **Problem:** RTP co-located with OpenSIPS/ASBC → scale events disrupted active calls; media/signaling lifecycles coupled; customers need fixed EIP for carrier firewall rules
- **Solution:** Dedicated RTPEngine ASG, EIP pool per node, dual-mode set_id routing (0=local, 1=cluster), Lambda lifecycle drain, GreenBlueSwitcher cluster toggle
- **Resume framing:** "Designed dedicated RTPEngine media cluster — decoupled media/signaling lifecycles, EIP-per-node for carrier firewall compatibility, graceful drain via Lambda + ASG lifecycle hooks"

#### Flagship 3: ISBC Cluster
- **Design doc:** `~/Documents/working_test/OPS-1998/OPS-1998-ISBC-Cluster-Report-EN.html`
- **Architecture:** NLB (source IP hash stickiness) → ASG (disable scale-in, Lambda lifecycle drain) → Asterisk 22 + PJSIP Realtime (MySQL via ODBC + sorcery memory_cache)
- **Cutover:** Zero-restart — call_route DB update + `pjsip reload` for immediate effect
- **Migration:** ap-northeast-1 → ap-east-2 (new Taipei AWS region)
- **Resume framing:** "Architected ISBC cluster: NLB + ASG with Lambda drain lifecycle, Asterisk PJSIP Realtime over MySQL — zero-restart traffic cutover via DB record update"

#### Flagship 4: Grafana Alert IaC (OPS-2410)
- **Design doc:** `~/Downloads/OPS-Grafana Alert IaC — Implementation Guide-110326-071207.pdf`
- **Trigger:** ProxySQL Aurora incident 2026-03-10 — Grafana alerts were manual UI-created, stored only in MySQL, no version control, not reproducible
- **Solution:** All new alerts provisioned as IaC via Helm templates → Kubernetes ConfigMap (label `grafana_alert: "1"`) → grafana-sc-alerts sidecar → `/etc/grafana/provisioning/alerting/` — rules marked Provisioned in UI, cannot be edited manually
- **Pipeline:** CloudWatch Logs → CloudWatch Metric Filters → prometheus-cloudwatch-exporter → Prometheus → Grafana Managed Alert → OpsGenie (critical) / Email (minor)
- **Impact:** 12 alert rules now version-controlled, peer-reviewed, environment-specific, reproducible
- **Story:** "Incident → root cause → systemic fix" — this is the full reliability engineering loop
- **Resume framing:** "Following production incident, migrated Grafana alert management from manual UI to IaC (Helm + Kubernetes ConfigMap sidecar) — 12 alert rules now version-controlled and provisioned automatically across prod/stg/pre"

#### Flagship 5: Reverseproxy Redesign — Stateless Routing via ECS + Redis (OPS design)
- **Design doc:** `~/Downloads/OPS-Reverseproxy Redesign — Switcher Extraction to ECS-100326-011020 (1).pdf`
- **Problem:** GreenBlueSwitcher runs as Flask app on every reverseproxy EC2 with local state (routing config files) → Jenkins must update each instance individually; reverseproxy cannot scale freely because of local state
- **Solution:** Extract Switcher to centralized ECS service; ElastiCache Redis as shared routing table; reverseproxy reads Redis (with in-process TTL cache) → becomes fully stateless and can scale freely
- **Key design decisions:** per-key TTL (not global flush), thread-safe in-process cache, Redis fallback probability analysis, Apache vs NGINX evaluation for prg: bottleneck
- **Status at handoff:** Architecture design complete, migration plan written
- **Resume framing:** "Designed architectural evolution of routing layer: extracted stateful EC2-local Switcher to centralized ECS service with ElastiCache Redis — enables stateless reverseproxy auto-scaling"

#### Flagship 6: BE API Boundary — Domain Separation Design
- **Design doc:** `~/Downloads/OPS-BE API Boundary — Removing Direct DB Writes from Switcher-100326-011050.pdf`
- **Problem:** GreenBlueSwitcher (DevOps tool) directly writes to 3 DB tables across 2 databases (provision, isbc) and calls BE-internal APIs — violates domain boundary; breaks silently when BE changes schema; business logic split across two owners
- **Solution:** Single `POST /mig/private/v1/moveCustomer` API owned by Lion (BE); Switcher only controls routing layer, never touches application data layer
- **Value:** Shows architectural judgment — identifying and fixing a systemic design violation, not just keeping it running
- **Resume framing:** "Identified cross-domain boundary violation in migration framework (DevOps tooling writing directly to application DB); designed clean API contract eliminating 6 direct DB writes from DevOps layer"

#### Flagship 7: LION-UT — Kubernetes-Based Isolated Test Environment for BE Team
- **Location:** `~/Documents/E2Nova_playground/devops/jenkins3/LION/LION-UT/`
- **Problem:** BE engineers had to spin up a full Docker stack locally to run unit tests — complex setup, machine-specific, error-prone, blocks concurrent runs
- **Solution:** Jenkins pipeline that provisions an isolated Kubernetes namespace per test run (UUID-based), initializes fresh MySQL + MongoDB state, runs Maven test suite, then auto-cleans up
- **Key design:** UUID namespace (`lion-ut-{env}-{build}-{uuid}`) = complete isolation between concurrent test runs; Karpenter spot instances for cost efficiency; SVN branch/tag + revision as inputs
- **Dual-mode execution:** same test environment definition runs on Docker Desktop (local dev iteration) AND Jenkins + Kubernetes (UUID-isolated CI runs) — local-CI parity eliminates "works on my machine" class of failures
- **Resume framing:** "Designed Kubernetes-based ephemeral test environment pipeline — BE engineers run full unit test suite via single Jenkins trigger; each run provisioned in UUID-isolated K8s namespace with fresh DB state, automatically cleaned up post-run; eliminated local Docker dependency"

#### Flagship 8: Coredump Management & GDB Debugging Pipeline
- **Problem:** C/C++ services crashing in AWS cloud environments produced unreadable stack traces in logs.
- **Solution:** Engineered a centralized coredump extraction pipeline in the AWS infrastructure, preserving core files and attaching debug symbols.
- **Value:** Proves the rare "Edge-to-Cloud cross-layer competency" (Schnittstellenkompetenz). A DevOps architect who not only scales the cloud but also knows exactly how to use GDB to debug the low-level C++ services running inside it.
- **Resume framing:** "Engineered automated coredump extraction pipeline for C/C++ cloud services in AWS, bridging cloud infrastructure observability with low-level GDB memory debugging."

#### IaC Breadth
- 479 CloudFormation templates (prod/stg/pre/dev)
- 49 ASGs: Reverseproxy, Freeswitch, ASBC, ISBC, RTPEngine, ProxySQL, FAX, MTA, WPS, Asterisk, SipProxy...
- 155 Jenkins pipelines: deployment, AMI lifecycle, DB ops, health checks, billing, DR
- Terraform: EKS, RDS, networking; Helm: prometheus-stack, ELK, Jenkins, Vault, LDAP
- Multi-account IAM (least-privilege per microservice), KMS encryption, WAF + CloudFront
- Prometheus + Grafana; CloudWatch alarms; VPC Flow Logs; ELK

#### Security & Compliance
- ISO 27001/27701 audits + DR drills (3 consecutive years); leading ISO 27701 infra review
- **GenAI for ISO 27701 (confirmed in use):** Applied GenAI tooling to infrastructure compliance reviews — practical necessity given scope of 479 CF templates; not aspirational
- **DR drill scope (for interview):** Each annual exercise executed cross-region failover Tokyo→Taipei: ASG scale-out in standby region → Aurora replica promotion → S3 cross-region restore validation → Route 53 health-check cutover; reviewed by external auditors, zero major NCs all cycles
- AWS sBOM generator, Cppcheck static analysis
- IEC 62443 awareness (ISO 27001 background maps directly to OT security)

---

## Technical Skills

| Category | Skills |
|----------|--------|
| Languages | C/C++ (10yr production), Golang, Python, C#, Bash, Groovy |
| Cross-Platform C++ / Edge | GAEA SDK (Boost), VAST1 recording server (wxWidgets+Boost), DeviceCenter (Qt+Boost), OpenVPN client SDK, store-and-forward, Linux/Windows cross-platform |
| Cloud (AWS) | EC2, ASG, NLB/ALB, VPC, Route53, CloudFront, Aurora RDS, ElastiCache, Lambda, EventBridge, SNS, SSM, KMS, Secrets Manager, CloudWatch, ECR, ECS, EKS, S3, Backup, WAF, IAM |
| IaC | CloudFormation (479 templates), Terraform, Helm, Ansible |
| CI/CD | Jenkins 3 (155 Jenkinsfiles, 38,900 LoC), Docker, ECR |
| Kubernetes | EKS, cert-manager, cluster autoscaler, Helm |
| Databases | MySQL/Aurora (ProxySQL, PJSIP Realtime, ODBC), SQLite3 (embedded), Redis, MongoDB, PostgreSQL |
| Observability | Prometheus, Grafana, ELK, CloudWatch, node_exporter |
| Protocols | SIP, RTP (carrier-grade), OpenVPN, MQTT, HTTP/REST; WebRTC/WebSocket (direction) |
| Security | ISO 27001/27701, IEC 62443 (awareness), Zero Trust, KMS, WAF, sBOM, Cppcheck |

---

## Career Goal

### Primary: Germany (All Regions)
**Preferred roles (priority):**
1. Senior Software Architect / Industrial Software Architect
2. Senior Cloud/Platform Engineer
3. Staff / Principal Engineer (stretch)

**Avoid:** Pure DevOps/on-call, Solutions Architect (client-facing), VoIP-specific roles, startups

**Explicitly excluded — Telecom (Deutsche Telekom, Vodafone DE):**
Reason: recruiter's first impression from resume (SIP/RTP/ISBC/300k calls) will route to VoIP teams regardless of target role. Market opportunity cost too high vs industrial roles where background is differentiating.

**Must have:** Betriebsrat, Tarifvertrag (IG Metall/ver.di), >10,000 employees
**Reason:** 3-year tenure goal for Blaue Karte EU Niederlassungserlaubnis

### Secondary: Netherlands (conditional)
Gross salary >€100,000/year + large established company only.

### Target Companies
| Priority | Companies |
|----------|-----------|
| S tier | Siemens (Automation / Mobility / Energy / Healthineers), Bosch, Beckhoff |
| Strong | Weidmüller, Festo, Trumpf, Diehl, Continental, ZF |
| Hidden Champions | **SICK AG** (industrial sensors/machine vision — VIVOTEK background maps directly), Pilz (IEC 62443), ifm electronic (IIoT), Beckhoff |
| ❌ Removed | KUKA — 100% Chinese-owned (Midea Group, privatized 2022, 2024 loss, CEO exit) |
| By city | Munich: Siemens/MAN/BMW · Stuttgart: Bosch/Daimler/Trumpf · Hamburg: Airbus · Nuremberg: Siemens/Diehl · Berlin: Siemens Energy |

---

## Salary Expectations
| Scenario | Target |
|----------|--------|
| Large company (DAX/MDAX), strong benefits | €85,000 gross/year |
| Mittelstand / hidden champion | €90,000–€95,000 gross/year |
| Netherlands, top-tier | >€100,000 gross/year |

### Resume 薪資寫法策略（已實作於 HR 版）
| HR 版本 | 寫法 | 理由 |
|---------|------|------|
| `cloud-platform_HR` | €85,000–€95,000 | 科技公司 HR 熟悉市場行情，給範圍效率高，上限錨定談判 |
| `industrial_HR` | €85,000–€90,000 | 傳統工業公司 HR 對照薪資 band，保守上限易對齊 |
| `medical-tech_HR` | €85,000+ | 醫療設備公司薪資結構不透明，只給下限留談判彈性 |

**原則：HR 版給範圍（方便對照預算）；技術版不寫薪資（讓用人主管先對角色）**

### Siemens BU 對應版本（已研究 LinkedIn JD）
| Siemens 子公司 | 性質 | 送哪個版本 |
|--------------|------|----------|
| Digital Industries | 工廠自動化、PLCs、Xcelerator | `industrial` |
| Smart Infrastructure | 智慧建築、電網、edge-to-cloud | `industrial` |
| Mobility | 鐵路系統、Railigent X | `industrial` |
| Healthineers | 醫療設備、影像診斷平台 | `medical-tech` |
| Energy (已獨立) | 電力輸配、電網數位化 | `industrial` |
| Siemens AG 總部 IT | 內部雲平台、developer tooling | `cloud-platform` |

---

## Key Positioning

**For industrial roles (Siemens/Bosch):**
"15 years from C/C++ SDK development to cloud infrastructure — designed the on-device storage SDK inside surveillance cameras, the OpenVPN management network behind a 1,000+ camera fleet, and the IaC that runs 20+ microservices at carrier grade. I understand the full stack from C/C++ application layer to Kubernetes on AWS."

**For cloud platform roles:**
"Full VPC ownership: 479 CloudFormation templates, 155 Jenkins pipelines, 49 ASGs, 5 AWS accounts across 3 regions. ProxySQL eliminated 6,000 daily DB timeouts. RTPEngine decoupled media/signaling at carrier scale. AWS Certified Solutions Architect – Professional (March 2026)."

**German keyword:** Schnittstellenkompetenz — cross-layer OT/IT integration competency

**Correct self-positioning: Cross-Platform C++ Systems Developer, NOT Firmware Engineer**
- No: burning boards, BSP, bootloader, Yocto/Buildroot, image versioning
- Yes: application-layer C++ running on embedded Linux, cross-platform (Linux/Windows), COM/GDB debug, full-stack up
- VIVOTEK work = three layers: SDK (GAEA/Boost), desktop app (VAST1/wxWidgets+Boost), management app (DeviceCenter/Qt+Boost)
- Key distinction: the code runs *on* embedded Linux devices; I did not write the OS, drivers, or bootloader
- The gap is a feature: sits exactly between HW/firmware teams and cloud — that's the scarce role
- Title to use: **Edge-to-Cloud Software Architect**

**On AI-assisted engineering (internal note, not for interviews):**
- With AI, syntax cost → ~0; what remains valuable: knowing *what* to solve, *trade-off judgment*, *when to stop*
- 15 years of systems breaking in production = the taste AI cannot replicate
- **Interview phrasing (DO NOT say "AI helped me"):** → "I focus on architecture decisions and system constraints — implementation follows from there."

---

## Flagship Decisions (Interview Prep)
| Company | Decision | Outcome |
|---------|----------|---------|
| VIVOTEK | DeviceCenter: OpenVPN private overlay for global camera management | 1,000+ cameras/tenant; remote firmware + config without on-site visits |
| D2 Nova | GreenBlueSwitcher: idempotent migration framework | Zero-downtime customer migration, single Jenkins trigger, no version pinning |
| E2 Nova | ProxySQL: infra-layer DB connection pooling | 5,000 → 29 connections; +34% P95; 6,000+ timeouts/day → 0 |
| E2 Nova | RTPEngine cluster: decouple media from signaling | Independent scaling, EIP-per-node, graceful drain |
| E2 Nova | ISBC cluster: NLB + ASG + Asterisk PJSIP Realtime | Zero-restart cutover, carrier-grade SIP at scale |

### ⚠️ Resume / Interview Terminology Traps
| 用詞 | 問題 | 正確用法 |
|------|------|--------|
| **GitOps** | 特指 ArgoCD/Flux pull-based deploy；我們是 Jenkins push — 被 tech lead 追問會答不出 | 改用 **Pipeline-as-Code** 或 **CI/CD automation** |
| **Multi-Cloud** | 特指 AWS + Azure + GCP；我們是 multi-account AWS | 改用 **Multi-Account AWS** 或 **Multi-Region AWS** |
| **medical-grade hardware** | VIVOTEK 做的是監控攝影機，不是醫療設備；HR 查一下就知道 | 改用 **global surveillance hardware** |
| **Firmware Engineer** | 暗示 BSP/bootloader/Yocto；我做的是 application-layer C++，跑在 embedded Linux 上 | 用 **Cross-Platform C++ Systems Developer** 或 **Edge-to-Cloud Software Architect** |
| **Embedded Systems Engineer** | 德國市場聯想 RTOS/device driver/HAL；我的層次是 application/SDK layer | 改用 **cross-platform C++ systems development (Boost/Qt/wxWidgets)** |
| **transactions** (用於流量) | 讓人以為是金融交易筆數；6,000 "transactions" 讓平台規模看起來很小 | 改用 **requests** 或 **service timeouts** 視情境 |

---

## Reference Documents
| Document | Path |
|----------|------|
| Migration + Switcher Design | ~/Downloads/OPS-Migration + Switcher — DevOps Design Document-100326-010836.pdf |
| ProxySQL Cluster Ops | ~/Downloads/OPS-ProxySQL Cluster Operations-090326-032959.pdf |
| RTPEngine Architecture | ~/Downloads/OPS-RTPengine Cluster — Architecture & Operations-180326-213012.pdf |
| ISBC Handover (EN) | ~/Documents/working_test/OPS-1998/OPS-1998-ISBC-Cluster-Report-EN.html |
| IaC repos | ~/Documents/E2Nova_playground/devops · evoxOps · 3rdParty_trunk |
| Current resume (DHL) | ~/Downloads/DHL_IT Solution Architect _resume.pdf |

---

## LinkedIn — Final Copy (ready to paste)

### Headline
```
Senior Software Architect | AWS Certified Solutions Architect – Professional | Cross-Platform C++ · Cloud Infrastructure · IaC | Open to Work — Germany
```

### About
```
Senior Software Architect with 15 years building production systems across
two distinct layers: cross-platform C++ application development
(Boost · Qt · wxWidgets) and large-scale AWS cloud infrastructure.

At VIVOTEK (Delta Electronics subsidiary, deployed in 120+ countries), I
designed and shipped three successive platform generations over 10 years —
a crash-safe on-device storage SDK, a cross-platform recording server, and
a device management network covering 1,000+ IP cameras across
transportation, petroleum, and enterprise deployments worldwide.

At E2 Nova (5,000+ enterprise clients), I became the single engineer with
end-to-end understanding of a platform processing 4–5 million HTTP requests
per day across 5 AWS accounts and 3 global regions. Key contributions:
ProxySQL connection pooling (eliminated 6,000+ daily service timeouts),
RTPEngine media/signaling decoupling, IaC-driven observability,
GenAI-assisted ISO 27701 compliance reviews, and a full AWS Taipei region
migration I personally led from design to handoff.

Reduced new engineer onboarding from 6 months to 2 months by building and
openly sharing a structured technical training curriculum.

AWS Certified Solutions Architect – Professional (March 2026).

Based in Berlin from March 2026, open to opportunities across Germany — Chancenkarte holder, targeting Blue Card via employment.

Open to: Senior Software Architect · Industrial Cloud Architect ·
Platform Engineer · Edge-to-Cloud Architect
```

> ⚠️ **Interview note:** "Why Berlin?" story (children's education, German Kindergarten → primary school) — save for recruiter/HR conversation, not LinkedIn.

## LinkedIn Skills — Action List

### 🗑️ Remove (9個)
- DeviceCenter (company-specific, unknown outside VIVOTEK)
- VIVOCloud (company-specific)
- VAST / VAST2 (company-specific)
- GitHub (duplicate of Git; GitHub is a platform, not a skill)
- Software Development (too generic)
- JavaScript (not core, dilutes focus)
- C# (1 endorsement, not core)
- Node.js (not core)
- Google Cybersecurity → move to **Certifications** section instead

### ➕ Add (priority order)
🔴 最高優先
- [ ] **Amazon Web Services (AWS)**
- [ ] **Amazon CloudFormation**
- [ ] **Infrastructure as Code (IaC)**
- [ ] **Docker**
- [ ] **DevOps**

🟠 高優先
- [ ] **Kubernetes**
- [ ] **Terraform**
- [ ] **Jenkins**
- [ ] **MySQL**
- [ ] **Grafana**
- [ ] **Prometheus**
- [ ] **ISO 27001**

🟡 中優先
- [ ] **IEC 62443** (awareness — answer in interview: "studied the framework, maps to ISO 27001; not led a formal certification project")
- [ ] **Qt**
- [ ] **Boost**
- [ ] **MQTT**

### 📌 釘選前 3 (Pinned Skills)
1. Amazon Web Services (AWS)
2. C++
3. DevOps

### ✅ Keep as-is
C++, C (Programming Language), Python, Go, Linux, Git, TCP/IP, SQL, MongoDB, Cybersecurity

### Other LinkedIn actions
- [ ] Headline → paste final copy above ✅ ready
- [ ] About → paste final copy above ✅ ready
- [ ] AWS SA-Pro cert: update from "Pursuing" → "Certified, March 2026"
- [ ] German language: update from "Daily Learner" → "A1, actively learning"
- [ ] Open to Work: enable (recruiter-only), location: **Germany** (not just Berlin)
- [ ] VIVOTEK experience bullets: expand (GAEA, Recording Server, DeviceCenter, 1,000+ cameras, transport deployments)
- [ ] Google Cybersecurity: move from Skills → Certifications section

**LinkedIn URL:** https://www.linkedin.com/in/bin-hsu-taiwan/

## LinkedIn Gaps (legacy — superseded above)
| Item | Current | Action |
|------|---------|--------|
| AWS Certified Solutions Architect – Professional | "Pursuing" | → "Certified, March 2026" |
| Headline | "Senior Backend & Solution Architect" | → ✅ See final copy above |
| About | Leads with VoIP call volume | → ✅ See final copy above |
| VIVOTEK | 3 thin bullets | → Expand: GAEA, Recording Server, DeviceCenter 1,000+ cameras, transport deployments |
| German level | "Daily Learner" | → "A1, actively learning" |
| Open to Work | Unknown | → Enable (recruiter-only), location: Germany + NL |
| IEC 62443 | Missing | → Add to Skills |
| MQTT | Missing | → Add to Skills |

**LinkedIn URL:** https://www.linkedin.com/in/bin-hsu-taiwan/
| Xing | No account | → Create (DACH market) |

---

## Permanent Residency Roadmap
```
2026-03-25  Land Berlin
2026-03-27  Anmeldung
2026-04     Start job applications (Chancenkarte)
2026 Q2-Q3  Target offer at qualifying large company
2026        Apply Blaue Karte EU (salary qualifies at 85k+)
2028        21 months + B1 German = accelerated NE route
            OR 33 months = standard Blaue Karte NE
2031        Standard Niederlassungserlaubnis fallback (5yr social insurance)
```

---

## Immigration Checklist

### Anmeldung (2026-03-27)
- [ ] Terminbestätigung
- [ ] Anmeldeformular (fill online)
- [x] Passport
- [ ] Wohnungsgeberbestätigung (from Wunderflats)
- [x] Rental contract

### LEF — Chancenkarte Extension (service.berlin.de, after Anmeldung)
- [ ] Anmeldebescheinigung (from 3/27)
- [ ] ZAB degree recognition *(color print)*
- [ ] Blocked account proof *(color print)*
- [ ] Health insurance Educare24 DE *(color print)*
- [ ] IELTS certificate *(color print)*
- [ ] Biometric photos (35x45mm)
- [ ] CV *(B&W OK)*
- [ ] Passport copies *(B&W OK)*

---

## Open Items (Next Sessions)
- [ ] Rewrite resume: Siemens/Bosch variant (lead VIVOTEK + DeviceCenter + GAEA)
- [ ] Rewrite resume: Cloud Platform variant (lead ProxySQL + IaC scale metrics)
- [ ] LinkedIn: headline, About, VIVOTEK bullets, skills, Open to Work
- [ ] Create Xing profile
- [ ] Draft German cover letter template
- [ ] Start OPC-UA self-study (bridges MQTT background to Industry 4.0)
