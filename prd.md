# AI Customer Acquisition OS — Comprehensive Product Requirements Document

**Document version:** 1.0  
**Status:** Product Definition / Build Specification  
**Product category:** AI-powered B2B customer acquisition platform  
**Primary market:** African startups and SMEs  
**Secondary market:** International startups, SaaS companies, agencies, B2B service companies, and businesses entering African markets  
**Frontend:** React + TypeScript + Tailwind CSS  
**Public web recommendation:** Next.js/React SSR or SSG for SEO-critical pages  
**Backend:** Django + Django REST Framework  
**Database:** PostgreSQL  
**Async jobs:** Celery + Redis  
**Object storage:** S3-compatible storage  
**Search:** PostgreSQL initially; OpenSearch/Elasticsearch as scale requires  
**AI:** Provider-agnostic LLM layer  
**Deployment:** Docker + cloud infrastructure  
**Architecture:** Multi-tenant, API-first SaaS

---

# 1. Executive Summary

The product is an AI-powered Customer Acquisition Operating System (CAOS) that helps businesses discover, research, contact, qualify, and convert potential customers.

It must not be positioned as merely:

- a lead scraper
- a contact database
- a cold-email sender
- an AI copywriter
- a CRM
- an autonomous spam tool

Instead, it owns the journey:

**Business → ICP → Opportunity Discovery → Prospect Research → Buying Signals → Outreach → Conversation → Qualification → Meeting → Opportunity → Customer → Revenue**

The central product promise is:

> **Find the businesses most likely to need what you sell, reach the right people with relevant messaging, and help turn conversations into paying customers.**

The north-star metric is therefore **paying customers and revenue generated**, not emails sent.

---

# 2. Vision

Become a trusted customer-acquisition infrastructure layer for African businesses and, over time, a global AI sales and growth platform.

The long-term product should allow a business to provide:

- website
- product/service
- target market
- preferred geography
- optional sales constraints

and receive:

- AI-generated ICP
- recommended markets
- target industries
- target companies
- decision makers
- buying signals
- company intelligence
- opportunity scores
- personalized outreach
- multi-channel campaigns
- AI-assisted conversations
- qualified opportunities
- booked meetings
- CRM pipeline
- revenue attribution
- continuous optimization recommendations

---

# 3. Problem Statement

Many startups and SMEs can build products but struggle to consistently acquire customers.

Existing sales tools often optimize for activity:

- number of leads
- number of contacts
- emails sent
- open rates
- reply rates

These metrics do not necessarily translate into revenue.

The product must solve the deeper problem:

> **Which companies should I approach, why should I approach them now, how should I approach them, and which activities are actually producing paying customers?**

African businesses face additional challenges:

- fragmented company information
- uneven business-data quality
- strong reliance on WhatsApp
- cross-border market complexity
- multiple currencies
- varying data availability
- multilingual markets
- different sales practices
- limited access to sophisticated sales infrastructure

The platform must treat these as first-class product requirements rather than afterthoughts.

---

# 4. Product Goals

## 4.1 Primary Goals

1. Help businesses identify high-fit prospects.
2. Explain why each prospect is potentially valuable.
3. Detect buying signals.
4. Research prospects automatically.
5. Generate relevant personalized outreach.
6. Support compliant multi-channel communication.
7. Qualify replies.
8. Help book meetings.
9. Track opportunities through a CRM pipeline.
10. Attribute acquisition activity to revenue.
11. Continuously recommend improvements.
12. Make African markets first-class while supporting international expansion.

## 4.2 Secondary Goals

1. Build proprietary African business intelligence.
2. Create a scalable B2B data network.
3. Build a defensible intent and conversion-data moat.
4. Provide an API and integrations ecosystem.
5. Become a continuous customer-acquisition engine rather than a one-off campaign tool.

---

# 5. Non-Goals

The initial product must not attempt to:

- build the world's largest contact database
- replace every CRM
- automate every social platform
- provide unrestricted autonomous outreach
- bypass platform restrictions
- scrape protected/private data
- guarantee customers
- guarantee revenue
- become an all-purpose marketing automation platform
- launch every communication channel simultaneously
- build a full enterprise sales suite before validating the core workflow

---

# 6. Target Customers

## 6.1 Primary Customer Segments

### African B2B Startups

Examples:

- SaaS
- fintech infrastructure
- cybersecurity
- logistics
- HR technology
- health technology
- education technology
- AI companies
- developer tools
- business software

### African SMEs

Examples:

- consulting firms
- software agencies
- marketing agencies
- professional services
- logistics companies
- manufacturers
- distributors
- B2B service providers

### Agencies

- marketing agencies
- software agencies
- web-development agencies
- SEO agencies
- advertising agencies
- consulting companies

## 6.2 Secondary Customer Segments

International companies looking to sell into Africa.

Example:

> A UK SaaS company wants qualified Nigerian fintech prospects.

The system should eventually support this workflow natively.

---

# 7. User Personas

## Persona A — Founder

Goal: acquire first customers.

Pain:

> "I built the product but do not know how to consistently get customers."

Needs:

- simple onboarding
- ICP generation
- prospect discovery
- campaign generation
- minimal configuration
- measurable results

## Persona B — Growth Lead

Goal: create a repeatable acquisition engine.

Needs:

- segmentation
- intent signals
- experiments
- analytics
- attribution
- CRM integrations

## Persona C — Sales Representative

Goal: find and convert qualified prospects.

Needs:

- prospect research
- talking points
- follow-ups
- pipeline
- task management
- conversation intelligence

## Persona D — Agency Owner

Goal: acquire and manage clients.

Needs:

- multiple workspaces
- client reporting
- white-label features
- reusable campaigns
- permissions

## Persona E — Enterprise Sales Team

Goal: account-based selling.

Needs:

- account intelligence
- territories
- buying signals
- CRM integration
- audit logs
- permissions
- compliance
- API

---

# 8. Product Principles

## 8.1 Revenue over activity

The system must optimize for qualified opportunities, customers, and revenue rather than raw message volume.

## 8.2 Intent over volume

A smaller list of highly relevant prospects is more valuable than a huge list of random contacts.

## 8.3 Evidence over AI guesses

AI recommendations should show supporting evidence and confidence whenever possible.

## 8.4 Human control

Users control targeting, campaigns, sensitive actions, and autonomous behavior.

## 8.5 Africa-first, not Africa-only

The architecture must support African requirements while remaining globally scalable.

## 8.6 Compliance by design

Privacy, consent, opt-out, suppression, data provenance, and regional requirements must be built into the architecture.

## 8.7 Product-led learning

The product should learn from actual conversion outcomes rather than only engagement metrics.

---

# 9. Core User Journey

```text
Website
   ↓
AI Company Understanding
   ↓
ICP Generation
   ↓
Market Recommendation
   ↓
Prospect Discovery
   ↓
Buying Signal Detection
   ↓
Opportunity Scoring
   ↓
Prospect Research
   ↓
User Approval
   ↓
Personalized Outreach
   ↓
Conversation
   ↓
AI Classification / Qualification
   ↓
Meeting
   ↓
Opportunity
   ↓
Deal
   ↓
Customer
   ↓
Revenue Attribution
   ↓
Optimization
```

---

# 10. Product Modules

The product consists of the following major modules:

1. Marketing Website
2. Authentication
3. Organization / Workspace
4. Onboarding
5. AI Company Understanding
6. ICP Builder
7. Market Intelligence
8. Prospect Discovery
9. Company Intelligence
10. Buying Signals
11. Opportunity Scoring
12. AI Research
13. Campaign Builder
14. Outreach
15. AI Sales Agent
16. Unified Inbox
17. CRM
18. Meetings
19. Revenue Attribution
20. Analytics
21. Website Sales Audit
22. AI Growth Advisor
23. Integrations
24. Billing
25. Compliance
26. Developer API
27. Documentation
28. Content / SEO / AEO
29. Admin
30. Trust / Security / Status

---

# 11. Public Website Information Architecture

Required public routes:

```text
/
 /product
 /features
 /features/ai-prospecting
 /features/buying-signals
 /features/company-intelligence
 /features/ai-sales-agent
 /features/email-outreach
 /features/whatsapp-sales
 /features/linkedin-prospecting
 /features/crm
 /features/revenue-attribution
 /features/lead-scoring
 /features/website-analysis

 /pricing
 /customers
 /resources
 /blog
 /guides
 /research
 /glossary
 /tools

 /industries/*
 /use-cases/*
 /countries/*

 /compare/*
 /integrations/*
 /docs
 /developers
 /security
 /trust
 /status
 /about
 /contact
 /privacy
 /terms
 /cookies
 /acceptable-use
 /data-processing
```

---

# 12. Homepage Requirements

## Hero

Headline:

> **Turn your website into a customer acquisition engine.**

Subheading:

> AI finds the companies most likely to need your product, identifies the right decision makers, starts relevant conversations, and helps turn prospects into paying customers.

Primary CTA:

**Find My Customers**

Secondary CTA:

**See How It Works**

## Homepage sections

1. Hero
2. Problem
3. How it works
4. Website-to-ICP demonstration
5. Prospect intelligence
6. Buying signals
7. AI research
8. Personalized outreach
9. AI sales agent
10. CRM and pipeline
11. Revenue attribution
12. Africa-first capabilities
13. International capabilities
14. Integrations
15. Case studies
16. Security
17. Pricing
18. FAQ / educational questions
19. Final CTA

---

# 13. Country Pages

Initial countries:

- Nigeria
- Kenya
- Ghana
- South Africa
- Egypt
- Rwanda
- Uganda
- Tanzania
- Senegal
- Côte d'Ivoire

Example route:

```text
/countries/nigeria
```

Each country page must contain real localized value:

- local market overview
- business targeting capabilities
- supported channels
- relevant industries
- currency
- market-specific sales considerations
- relevant compliance information
- examples
- case studies when available

Avoid thin automated localization.

---

# 14. Industry Pages

Initial industries:

- SaaS
- fintech
- cybersecurity
- logistics
- healthcare
- education
- ecommerce
- manufacturing
- agriculture
- real estate
- consulting
- marketing agencies
- software development
- HR
- professional services

---

# 15. Use-Case Pages

Required:

- Get first customers
- Find B2B leads
- Find African businesses
- SaaS outbound
- Agency client acquisition
- Startup sales
- Account-based marketing
- Lead qualification
- Automated sales
- WhatsApp sales
- International market entry

---

# 16. Competitor Comparison Pages

Routes:

```text
/compare/getlead
/compare/explee
/compare/apollo
/compare/hubspot
/compare/instantly
/compare/lemlist
```

Rules:

- factual
- fair
- evidence-based
- no deceptive claims
- clearly state where competitor is stronger
- explain ideal use cases

---

# 17. Free Acquisition Tools

Build free tools that attract high-intent visitors:

1. ICP Builder
2. Lead List Cleaner
3. Email Verifier
4. Website Lead Audit
5. Customer Acquisition Score
6. Cold Email ROI Calculator
7. CAC Calculator
8. Lead Score Calculator
9. Website Sales Audit
10. B2B Outreach Cost Calculator

Each tool should have:

- useful free result
- optional signup
- relevant CTA
- SEO metadata
- structured data where applicable
- internal links

---

# 18. Blog / Research / Knowledge Base

Content categories:

- B2B sales
- African startups
- SaaS growth
- customer acquisition
- AI sales
- outbound sales
- WhatsApp business
- African business intelligence
- lead generation
- startup marketing
- international expansion

Long-term content should include original research generated from lawful aggregated platform data.

Examples:

- State of B2B Sales in Nigeria
- African Startup Customer Acquisition Benchmark
- African SaaS Sales Benchmark
- African B2B Buying Trends

---

# 19. SEO Requirements

Public pages must support:

- crawlable HTML
- server rendering or static generation
- semantic HTML
- canonical URLs
- XML sitemaps
- robots.txt
- OpenGraph
- social metadata
- structured data
- breadcrumbs
- optimized images
- internal links
- clean URLs
- pagination
- 404 pages
- redirect management
- hreflang
- Core Web Vitals optimization
- noindex controls

Recommended public frontend:

**Next.js/React**

Django remains the core API/backend.

---

# 20. AEO / Generative Search Requirements

Content must be structured for direct-answer discovery.

Each major content page should provide:

- clear questions
- concise direct answers
- detailed supporting explanation
- examples
- tables
- definitions
- evidence
- author information
- publication date
- update date
- related questions
- internal links

Do not mass-produce low-value AI pages.

The content strategy must prioritize:

**Originality + expertise + evidence + usefulness.**

---

# 21. Structured Data

Use valid schema types where appropriate:

- Organization
- SoftwareApplication
- Product
- Service
- Article
- BreadcrumbList
- WebSite
- WebPage
- ProfilePage
- Dataset

FAQ content can exist for users, but structured data must only be used where eligible and supported by search-engine guidelines.

---

# 22. International SEO

Architecture should support:

```text
/en/
/en-ng/
/en-ke/
/en-gh/
/en-za/
/fr/
/fr-ci/
/fr-sn/
/ar/
/pt/
```

Do not generate thousands of empty localized pages.

Localized pages require genuine market-specific value.

---

# 23. Authentication

Support:

- email/password
- Google OAuth
- Microsoft OAuth
- magic link
- MFA
- password reset
- email verification

Enterprise:

- SSO/SAML later

---

# 24. Organization / Workspace

Every customer belongs to an organization.

Organizations can contain multiple workspaces.

Example:

```text
Organization
 ├── Main Sales
 ├── Nigeria
 ├── Kenya
 └── Enterprise
```

Support:

- members
- roles
- permissions
- billing ownership
- workspace settings

---

# 25. Onboarding

## Step 1 — Website

User enters website.

## Step 2 — AI analysis

Analyze public company information.

## Step 3 — Confirm business

User confirms:

- product
- industry
- target market
- pricing
- business model

## Step 4 — ICP

AI generates ICP.

## Step 5 — Markets

Recommend target countries and industries.

## Step 6 — Communication

Connect channels.

## Step 7 — Prospects

Generate initial prospect list.

## Step 8 — Campaign

Generate first campaign.

## Step 9 — Launch

User reviews and approves.

---

# 26. AI Company Understanding

Input:

- website
- pricing pages
- product pages
- documentation
- public blog
- uploaded materials
- public social information where permitted

Output:

```text
Company
Product
Industry
Business model
Target customers
Value proposition
Pricing
Use cases
Pain points solved
Competitors
Geographies
Buyer personas
```

All AI-generated data must be editable.

---

# 27. ICP Builder

Generate:

## Company profile

- industry
- location
- employee range
- estimated business size
- business model
- technology
- growth stage

## Buyer profile

- job title
- department
- seniority
- responsibilities

## Pain signals

- hiring
- funding
- expansion
- product launch
- advertising
- technology changes
- website changes

Allow manual editing.

---

# 28. Market Recommendation Engine

AI should recommend markets using:

- product fit
- company density
- industry density
- estimated demand
- competition
- communication availability
- regulatory constraints
- language
- purchasing power

Example:

> Nigeria — High fit  
> Kenya — Medium-high fit  
> South Africa — High fit  
> Ghana — Medium fit

Each recommendation must explain its reasoning.

---

# 29. Prospect Discovery

Search by:

- country
- city
- industry
- employee count
- revenue range
- technology
- keyword
- business model
- job title
- company stage
- funding
- hiring
- advertising
- website technology
- public business signals

---

# 30. African Business Intelligence

Support first-class fields for:

- country
- city
- region
- industry
- website
- public business contact
- public phone
- public social profiles
- company size estimate
- technology
- public business status
- public registration data where legally sourced
- signals
- provenance

Initial markets:

Nigeria, Kenya, Ghana, South Africa, Egypt, Rwanda, Uganda, Tanzania, Senegal, Côte d'Ivoire.

---

# 31. Prospect Detail

Show:

```text
Company
Country
City
Industry
Size
Website
Opportunity Score
Intent
```

Sections:

- Why this company?
- Buying signals
- Company summary
- Products
- Recent events
- Decision makers
- Contact channels
- AI research
- Recommended approach
- Conversation
- CRM status
- Activity history

---

# 32. Opportunity Score

Score 0–100.

Initial weighting:

```text
ICP fit              25%
Buying intent        20%
Pain evidence        15%
Company growth       10%
Technology fit       10%
Geographic fit        5%
Contact quality       5%
Engagement           10%
```

Weights must be configurable.

The platform must explain the score.

---

# 33. Buying Signal Engine

Signals:

### Corporate

- funding
- hiring
- expansion
- acquisition
- new office
- leadership change

### Website

- new pages
- product launch
- pricing changes
- technology changes
- website changes

### Marketing

- advertising
- content growth
- social activity

### Sales

- hiring
- procurement signals
- partnerships

Every signal stores:

- type
- source
- timestamp
- confidence
- evidence
- expiration/staleness

---

# 34. AI Research Agent

For high-value prospects:

Research:

- company
- website
- products
- recent events
- market
- likely pain
- relevant decision makers
- possible use case

Output:

- research summary
- why they may buy
- suggested approach
- personalization points
- confidence
- evidence

---

# 35. “Why Contact This Company?”

Every high-priority prospect should have a concise explanation.

Example:

> ABC Logistics recently expanded into Ghana and is hiring regional sales staff. Your sales automation product could help them manage the growing outbound team.

The explanation must be evidence-based.

---

# 36. Campaign Builder

Fields:

- campaign name
- ICP
- target market
- industry
- prospect count
- channel
- messaging
- sequence
- schedule
- sending limits
- AI personalization
- approval mode

Before launch show:

- estimated audience
- estimated AI cost
- expected message volume
- compliance warnings
- sample messages

---

# 37. AI Campaign Planner

User can write:

> “I sell cybersecurity software to Nigerian fintech companies.”

AI should generate:

- ICP
- target companies
- decision makers
- buying signals
- outreach strategy
- campaign
- personalization
- objections
- follow-up sequence
- qualification questions

User must approve before launch.

---

# 38. Outreach

Initial channels:

- email
- WhatsApp Business Platform where appropriate
- SMS where appropriate

Future:

- LinkedIn only through compliant supported mechanisms
- voice
- additional channels

The platform must not encourage spam, platform abuse, or evasion of anti-abuse systems.

---

# 39. Email Infrastructure

Support:

- Gmail
- Outlook
- SMTP
- Amazon SES
- SendGrid
- Mailgun
- Postmark

Capabilities:

- domain verification
- SPF guidance
- DKIM guidance
- DMARC guidance
- bounce tracking
- complaint tracking
- unsubscribe
- suppression
- sending limits
- sender reputation monitoring

---

# 40. WhatsApp

Use official WhatsApp Business infrastructure.

Capabilities:

- approved templates
- inbound conversations
- outbound permitted business messages
- opt-out handling
- message classification
- AI-assisted replies

Do not use unauthorized WhatsApp automation.

---

# 41. AI Sales Agent

The agent can:

- classify replies
- summarize conversations
- answer approved questions
- detect objections
- qualify prospects
- recommend next steps
- propose meetings
- stop communication when requested

Modes:

### Manual

AI only provides recommendations.

### Copilot

AI drafts responses; user approves.

### Autopilot

AI operates within predefined policies.

Autopilot requires:

- approved knowledge base
- communication policy
- prohibited topics
- escalation rules
- rate limits
- audit logs

---

# 42. Reply Classification

Classify:

- interested
- meeting request
- question
- objection
- not interested
- unsubscribe
- wrong person
- out of office
- referral
- spam
- angry
- unclear

---

# 43. Unified Inbox

Consolidate supported channels.

Conversation view:

- company
- contact
- opportunity score
- AI summary
- conversation
- recommended response
- CRM stage
- next action
- history

---

# 44. CRM

Default pipeline:

```text
New
 ↓
Contacted
 ↓
Engaged
 ↓
Qualified
 ↓
Meeting
 ↓
Proposal
 ↓
Negotiation
 ↓
Won
 ↓
Lost
```

Support custom pipelines.

---

# 45. Meetings

Integrate:

- Google Calendar
- Microsoft Calendar
- Calendly
- Cal.com

Capabilities:

- meeting links
- availability
- booking
- reminders
- meeting status
- opportunity association

---

# 46. Revenue Attribution

Track:

```text
Campaign
 ↓
Prospect
 ↓
Conversation
 ↓
Meeting
 ↓
Opportunity
 ↓
Deal
 ↓
Customer
 ↓
Revenue
```

Dashboard must answer:

> Which campaigns are generating money?

Metrics:

- pipeline value
- closed revenue
- revenue per campaign
- CAC
- ROI

---

# 47. Analytics

## Acquisition

- visitors
- signups
- prospects
- qualified prospects

## Engagement

- messages
- replies
- positive replies

## Sales

- meetings
- opportunities
- proposals
- wins

## Financial

- revenue
- pipeline
- CAC
- ROI
- LTV
- churn

---

# 48. AI Growth Advisor

User asks:

> “Why aren't I getting customers?”

AI analyzes:

- ICP
- audience
- targeting
- signals
- messaging
- reply rates
- qualification
- meetings
- website
- pricing where available
- funnel conversion

It returns:

- diagnosis
- evidence
- recommendations
- expected impact
- experiment suggestions

---

# 49. Website Sales Audit

Input:

URL

Output:

- value proposition score
- ICP clarity
- CTA score
- trust score
- pricing clarity
- conversion score
- SEO score
- AEO readiness
- performance observations
- recommendations

---

# 50. CRM Integrations

Initial:

- HubSpot
- Salesforce
- Pipedrive
- Zoho
- Close

Future:

- Freshsales
- Monday
- Microsoft Dynamics

Integration requirements:

- OAuth where supported
- sync configuration
- field mapping
- conflict handling
- retries
- webhook support
- logs

---

# 51. Lead Import

Support:

- CSV
- XLSX
- API

Import:

- company
- name
- title
- email
- phone
- website
- country
- industry

Automatically:

- deduplicate
- validate
- enrich
- score

---

# 52. Lead Export

Support:

- CSV
- XLSX
- API

---

# 53. API

Initial API:

```text
/api/v1/auth/
/api/v1/organizations/
/api/v1/companies/
/api/v1/people/
/api/v1/leads/
/api/v1/icp/
/api/v1/signals/
/api/v1/research/
/api/v1/campaigns/
/api/v1/messages/
/api/v1/conversations/
/api/v1/opportunities/
/api/v1/deals/
/api/v1/customers/
/api/v1/analytics/
/api/v1/integrations/
/api/v1/billing/
/api/v1/webhooks/
```

Use versioned APIs.

---

# 54. Webhooks

Events:

```text
lead.created
lead.enriched
lead.scored
signal.detected
campaign.started
message.sent
reply.received
lead.qualified
meeting.booked
opportunity.created
deal.won
deal.lost
customer.created
```

Webhook requirements:

- signing secret
- retries
- idempotency
- event IDs
- delivery logs

---

# 55. Developer Portal

Routes:

```text
/developers
/docs
/docs/api
/docs/webhooks
/docs/sdks
```

Provide:

- API keys
- documentation
- examples
- SDKs
- rate limits
- webhook docs
- authentication docs

Future SDKs:

- Python
- JavaScript
- PHP

---

# 56. AI Architecture

Provider abstraction:

```text
AIProvider
 ├── OpenAIProvider
 ├── AnthropicProvider
 ├── GeminiProvider
 └── LocalProvider
```

Services:

```text
CompanyResearchAgent
ICPAgent
MarketResearchAgent
ProspectDiscoveryAgent
SignalDetectionAgent
LeadScoringAgent
PersonalizationAgent
OutreachAgent
ReplyClassificationAgent
SalesAgent
CampaignOptimizationAgent
GrowthAdvisorAgent
```

---

# 57. AI Guardrails

All agents must have:

- system policies
- tool permissions
- data-access boundaries
- output validation
- audit logs
- escalation rules
- prompt/version tracking
- model/version tracking

Never allow an AI agent to:

- access arbitrary private data
- send unrestricted messages
- bypass security controls
- bypass platform restrictions
- fabricate evidence
- invent prospect information

---

# 58. AI Evidence

When the AI says:

> “This company recently expanded.”

the system should retain:

- evidence source
- source URL
- retrieval time
- confidence

Where evidence is unavailable, the AI should state uncertainty.

---

# 59. AI Usage and Cost

Track:

- organization
- user
- feature
- model
- request
- token usage
- estimated cost
- timestamp

Use model routing:

```text
Low-cost models
 → classification
 → simple extraction
 → formatting

Advanced models
 → research
 → strategy
 → high-value personalization
 → complex reasoning
```

---

# 60. Lead Data Quality

Every contact should include:

- email status
- phone status
- verification date
- source
- confidence
- last seen

Statuses:

- verified
- risky
- unknown
- invalid
- bounced
- unsubscribed

---

# 61. Data Provenance

Store:

```text
source
source_url
collected_at
last_verified_at
confidence
license/usage category where applicable
```

Data providers must be reviewed for legal and contractual usage rights.

---

# 62. Privacy / Compliance

Required:

- privacy policy
- terms
- acceptable-use policy
- data-processing terms
- consent/permission handling where required
- unsubscribe
- suppression
- deletion
- export
- retention
- audit logs
- regional policy controls

Support configurable policies for:

- Nigeria
- Kenya
- South Africa
- EU/GDPR
- UK
- US
- other markets

Legal review is required before production use of large-scale personal-data enrichment.

---

# 63. Global Suppression

If a person requests no contact:

- immediately suppress them
- prevent accidental re-enrollment
- record timestamp
- preserve minimum data necessary to honor suppression obligations

---

# 64. Abuse Prevention

Detect:

- spam behavior
- excessive sending
- high complaint rates
- suspicious account creation
- malicious links
- phishing-like content
- repeated opt-out violations

Actions:

- warning
- rate limiting
- campaign pause
- identity verification
- account review
- suspension

---

# 65. Multi-Tenant Data Isolation

Every tenant-owned record must be scoped to an organization/workspace.

Required:

- tenant-aware querysets
- permission checks
- database constraints where practical
- object-level authorization
- audit logging
- tests for cross-tenant access

---

# 66. Roles

### Owner

Full access.

### Admin

Workspace and team management.

### Manager

Campaigns, prospects, analytics.

### Sales Rep

Prospects, conversations, pipeline.

### Viewer

Read-only.

Future:

- billing admin
- compliance admin
- analyst

---

# 67. Billing

Support:

- subscriptions
- usage billing
- credits
- add-ons
- seats
- invoices
- tax information
- upgrades
- downgrades
- cancellations

African payment priority:

- Paystack
- Flutterwave

International:

- Stripe
- appropriate merchant-of-record/payment infrastructure

---

# 68. Suggested Plans

## Free

- limited prospect discovery
- limited AI research
- limited campaigns
- basic CRM

## Starter

For early startups.

## Growth

For growing businesses.

## Agency

Multi-client workspaces and reporting.

## Enterprise

Custom limits, API, security, support and data options.

Pricing must be validated with real customers rather than assumed.

---

# 69. Credit System

Credits may represent:

- deep research
- enrichment
- verified contacts
- AI research
- premium intelligence

Before expensive operations show estimated credit consumption.

---

# 70. African Communication Layer

Channel selection should support country-specific preferences.

Example:

```text
Nigeria
Email + WhatsApp

Kenya
Email + WhatsApp

South Africa
Email + LinkedIn-supported workflows

France
Email
```

Channel recommendations must be based on legitimate business communication practices and user-configured preferences.

---

# 71. African Market Intelligence

Country profile object:

```text
Country
Currency
Languages
Timezones
Major industries
Business hubs
Communication patterns
Regulatory references
Market metadata
```

Future market intelligence:

- city-level business clusters
- industry density
- company growth
- cross-border opportunities

---

# 72. Currency

Initial:

- NGN
- KES
- GHS
- ZAR
- EGP
- RWF
- UGX
- TZS
- XOF
- USD
- EUR
- GBP

---

# 73. Notifications

Channels:

- email
- in-app
- WhatsApp where appropriate
- push later

Events:

- hot lead
- reply
- meeting
- opportunity
- campaign completion
- credits low
- integration error
- campaign paused

---

# 74. Security

Required:

- HTTPS
- secure cookies
- CSRF protection
- OAuth security
- MFA
- rate limiting
- encrypted secrets
- API key hashing
- permission checks
- audit logs
- encryption at rest where supported
- tenant isolation
- secret rotation
- suspicious-login detection

---

# 75. Admin Dashboard

Internal dashboard:

- users
- organizations
- subscriptions
- revenue
- AI usage
- lead volume
- campaign volume
- messages
- deliverability
- complaints
- abuse
- system health

---

# 76. Trust Center

Route:

`/trust`

Sections:

- security
- privacy
- compliance
- data handling
- subprocessors
- uptime
- incident response
- contact

---

# 77. Status Page

Route:

`/status`

Services:

- API
- Dashboard
- AI
- Enrichment
- Messaging
- Integrations

---

# 78. Documentation

Documentation:

```text
Getting Started
Authentication
Organizations
Prospecting
Signals
Campaigns
Messaging
CRM
AI
Billing
Compliance
Webhooks
Troubleshooting
```

---

# 79. Django Backend Architecture

Suggested apps:

```text
apps/
    accounts/
    organizations/
    billing/
    companies/
    contacts/
    leads/
    intelligence/
    signals/
    campaigns/
    messaging/
    conversations/
    crm/
    opportunities/
    analytics/
    ai/
    integrations/
    notifications/
    compliance/
    content/
    api/
```

Use service layers for complex business logic rather than placing everything inside serializers/views.

---

# 80. Core Data Model

Initial entities:

```text
User
Organization
Membership
Workspace
Subscription
CreditBalance

Company
Person
CompanyTechnology
CompanyEvent
Lead
LeadSource
LeadSignal
LeadScore
ICP

Campaign
Sequence
Message
Conversation

Opportunity
Deal
Customer
RevenueEvent

Integration
APIKey
Webhook
SuppressionEntry

AIJob
AIUsage
AIConversationContext

AuditLog
Notification
```

Use UUID public IDs.

---

# 81. Background Jobs

Celery tasks:

- website analysis
- website crawling
- company enrichment
- lead enrichment
- email verification
- signal detection
- AI research
- scoring
- campaign scheduling
- message delivery
- reply synchronization
- CRM synchronization
- analytics aggregation
- report generation
- sitemap generation

Tasks must be idempotent where possible.

---

# 82. Caching

Use Redis for:

- rate limiting
- short-lived AI context
- job coordination
- frequently accessed market metadata
- temporary search results

Do not use Redis as the system of record for critical business data.

---

# 83. Search

MVP:

PostgreSQL full-text and indexed filtering.

Scale:

OpenSearch/Elasticsearch.

Search dimensions:

- company
- person
- industry
- country
- city
- technology
- signal
- intent
- company size

---

# 84. Data Acquisition Strategy

Do not attempt to create a massive database from scratch.

Initial strategy:

1. licensed data providers
2. customer-imported data
3. public business information where legally permitted
4. first-party company research
5. integrations
6. user-generated enrichment
7. proprietary signals

Long-term:

Build proprietary African business intelligence through lawful sources and accumulated conversion data.

---

# 85. Data Moat

The defensibility loop:

```text
More customers
 ↓
More campaigns
 ↓
More interactions
 ↓
More outcomes
 ↓
More conversion data
 ↓
Better scoring
 ↓
Better targeting
 ↓
Better acquisition
 ↓
More customers
```

The LLM is not the moat.

The moat is:

**Data + intent + outcomes + workflows + distribution.**

---

# 86. Content System

CMS must support:

- blog
- guides
- glossary
- research
- comparison pages
- industry pages
- country pages
- use cases
- case studies
- landing pages

Content fields:

```text
title
slug
excerpt
body
author
reviewer
published_at
updated_at
canonical
seo_title
meta_description
og_image
schema_type
noindex
```

---

# 87. Internal Linking

Content editor should support:

- related content
- feature links
- country links
- industry links
- tool links
- case-study links

Future AI suggestions can recommend links but editors retain control.

---

# 88. Case Studies

Route:

`/customers/{slug}`

Include:

- customer
- problem
- implementation
- prospects
- meetings
- opportunities
- customers
- revenue
- timeline

Only verified metrics should be published.

---

# 89. Product Analytics

Track activation funnel:

```text
Visitor
 ↓
Signup
 ↓
Onboarding complete
 ↓
ICP created
 ↓
First prospect found
 ↓
First campaign
 ↓
First reply
 ↓
First qualified opportunity
 ↓
First meeting
 ↓
First customer
```

---

# 90. North-Star Metric

## Paying customers generated per active customer account

Secondary:

- qualified opportunities
- meetings
- positive replies
- pipeline value
- revenue
- acquisition ROI

Do not use:

- emails sent
- database size
- AI credits consumed

as the primary product success metric.

---

# 91. Activation Metrics

A customer is activated when they:

1. complete onboarding
2. generate an ICP
3. find at least one highly relevant prospect
4. launch a campaign
5. receive a meaningful conversation

The strongest activation event:

> **First genuinely relevant prospect discovered.**

The ultimate success event:

> **First paying customer acquired.**

---

# 92. MVP Scope

MVP must contain:

1. Authentication
2. Organization/workspace
3. Website onboarding
4. AI company analysis
5. ICP builder
6. African market filters
7. Prospect discovery
8. Company intelligence
9. Buying signals
10. Opportunity scoring
11. AI prospect research
12. Email integration
13. AI personalization
14. Campaigns
15. Reply detection
16. Unified inbox
17. Basic CRM
18. Meeting booking
19. Revenue/opportunity analytics
20. Billing
21. Suppression/compliance
22. Website sales audit

---

# 93. Post-MVP

Phase 2:

- WhatsApp
- CRM integrations
- advanced signals
- additional countries
- agency workspaces
- AI sales agent
- advanced analytics
- more integrations

Phase 3:

- global intelligence database
- semantic company search
- account-based marketing
- predictive intent
- advanced enterprise features
- API marketplace

Phase 4:

- voice
- advanced autonomous sales agents
- continuous opportunity discovery
- international customer acquisition network

---

# 94. Features Explicitly Delayed

Do not initially build:

- massive proprietary global database
- AI phone calls
- every CRM
- every messaging channel
- unauthorized social automation
- full enterprise CRM
- dozens of languages
- complex autonomous agents
- complex attribution models

First prove the core business proposition.

---

# 95. TryNoBot as Internal Design Partner

Use TryNoBot as the first real customer-acquisition laboratory.

The platform should discover potential TryNoBot customers such as:

- advertisers
- agencies
- ecommerce companies
- high-traffic websites
- companies running paid campaigns
- businesses potentially exposed to low-quality traffic

Track:

```text
Prospects
 ↓
Qualified
 ↓
Contacted
 ↓
Replies
 ↓
Meetings
 ↓
Trials
 ↓
Paid customers
 ↓
Revenue
```

If the system cannot produce meaningful acquisition results for the founder's own product, the product should not yet be marketed as a proven customer-acquisition engine.

---

# 96. Initial Vertical

Start with:

## African B2B SaaS and technology companies

Reasons:

- founder has domain understanding
- easier prospect research
- clear B2B economics
- relatively measurable acquisition
- strong international expansion potential
- easier initial case studies

Potential verticals:

- SaaS
- cybersecurity
- fintech
- logistics
- software agencies
- AI startups

---

# 97. Launch Strategy

Do not initially market:

> "AI sales platform for everyone."

Start with a narrow promise.

Example:

> **Get your first 10 qualified B2B prospects without hiring an SDR.**

Initial customer acquisition should be founder-led.

### First 10 customers

Manual onboarding.

### First 50

Productize repeated workflows.

### First 500

Automate acquisition and onboarding.

### First 5,000

Build deeper data/network effects.

---

# 98. Customer Success Strategy

For early customers:

- onboarding call
- ICP review
- first campaign setup
- prospect review
- campaign review
- weekly acquisition report
- conversion review

The objective is to learn what actually generates customers.

---

# 99. Product Positioning

Avoid:

> AI lead generator

Avoid:

> Cold email software

Avoid:

> Lead database

Preferred:

# AI Customer Acquisition OS

Short tagline:

> **Find the right customers. Start the right conversations. Close more business.**

Long description:

> An AI-powered customer acquisition platform that discovers high-intent companies, researches prospects, creates personalized outreach, manages conversations, books meetings, and connects sales activity directly to revenue.

---

# 100. African Positioning

Core message:

> **Built for African businesses. Ready for the world.**

The platform should help:

- Nigerian companies sell internationally
- Kenyan companies sell internationally
- Ghanaian companies sell internationally
- South African companies expand globally
- international companies enter African markets

---

# 101. Competitive Strategy

Do not compete initially on database size.

Competitors can have enormous databases.

Compete on:

1. African business intelligence
2. buying signals
3. evidence-backed opportunity scoring
4. “why contact this company?”
5. multi-channel acquisition
6. AI qualification
7. revenue attribution
8. local payment/communication support
9. market-entry intelligence
10. vertical playbooks

The product should be **better at deciding who deserves attention**, not merely better at producing lists.

---

# 102. Quality Standards

A prospect should not be considered high-quality merely because contact information exists.

Minimum high-quality prospect requirements should include as many as available:

- ICP match
- valid company
- relevant industry
- relevant geography
- relevant buyer
- meaningful buying signal
- contact confidence
- evidence
- reason-to-contact

---

# 103. Performance Requirements

Initial targets:

- public pages optimized for excellent Core Web Vitals
- API p95 latency target under 500ms for normal CRUD endpoints
- background AI/enrichment jobs asynchronous
- search response target under 2 seconds for normal queries
- dashboard initial data load target under 2 seconds after API readiness

Long-running tasks must never block request threads.

---

# 104. Reliability

Required:

- retries
- dead-letter handling where appropriate
- idempotency
- job status
- integration error visibility
- database backups
- monitoring
- alerting
- audit logs

---

# 105. Observability

Track:

- API errors
- Celery failures
- AI failures
- provider failures
- message failures
- webhook failures
- database performance
- Redis health
- search health
- queue depth

---

# 106. Testing

## Backend

- unit tests
- API tests
- permission tests
- tenant isolation tests
- billing tests
- integration tests
- Celery task tests

## Frontend

- component tests
- integration tests
- critical E2E flows

## AI

- evaluation datasets
- classification tests
- hallucination tests
- prompt regression tests
- output schema validation

## Security

- authentication tests
- authorization tests
- tenant isolation
- rate limits
- injection testing
- secret handling

---

# 107. Critical E2E Test

The platform must have one complete automated journey:

```text
Signup
 ↓
Create organization
 ↓
Enter website
 ↓
AI analyzes company
 ↓
Generate ICP
 ↓
Search prospects
 ↓
Select prospect
 ↓
Generate research
 ↓
Create campaign
 ↓
Approve
 ↓
Send
 ↓
Receive reply
 ↓
Classify reply
 ↓
Create opportunity
 ↓
Book meeting
 ↓
Mark deal won
 ↓
Record revenue
 ↓
Revenue appears in analytics
```

---

# 108. Security & Privacy Testing

Test:

- cross-tenant access
- broken object-level authorization
- insecure direct object references
- privilege escalation
- webhook spoofing
- API key leakage
- sensitive log leakage
- unsafe file uploads
- prompt injection
- malicious prospect content
- SSRF during website analysis
- crawler abuse
- rate-limit bypass

Website crawling must be sandboxed and protected against SSRF.

---

# 109. Website Crawler Security

The crawler must:

- validate URLs
- block private IP ranges
- block localhost
- block internal network addresses
- restrict protocols
- enforce timeout
- enforce response-size limits
- limit redirects
- sanitize extracted content
- isolate execution

---

# 110. File Security

Uploaded files must have:

- size limits
- allowed MIME types
- virus/malware scanning where appropriate
- randomized storage names
- access controls
- tenant isolation

---

# 111. Audit Logging

Log sensitive actions:

- login
- role change
- API key creation
- integration creation
- campaign launch
- campaign pause
- data export
- deletion
- AI autopilot activation
- billing changes
- compliance changes

---

# 112. Accessibility

Target WCAG 2.2 AA.

Support:

- keyboard navigation
- semantic controls
- accessible forms
- screen readers
- contrast
- focus indicators
- reduced motion

---

# 113. Internationalization

Frontend must support translation keys rather than hardcoded text.

Initial:

- English

Next:

- French
- Arabic

Future:

- Portuguese
- Swahili
- Hausa
- Yoruba

AI-generated content should support locale-aware generation.

---

# 114. Design System

Build a reusable component system:

- Button
- Input
- Select
- Combobox
- Modal
- Drawer
- Tabs
- Card
- Table
- Data table
- Badge
- Tooltip
- Toast
- Alert
- Dropdown
- Pagination
- Empty state
- Skeleton
- Chart
- Command palette

The application should feel consistent across all modules.

---

# 115. Main Application Navigation

Suggested sidebar:

```text
Overview

Find Customers
  Prospects
  Companies
  Signals
  ICP

Engage
  Campaigns
  Inbox
  AI Sales Agent

Sell
  Pipeline
  Meetings
  Opportunities
  Customers

Analyze
  Analytics
  Revenue
  AI Advisor

Integrations

Billing

Settings
```

---

# 116. Dashboard Layout

Top:

```text
Customers Generated
Pipeline
Revenue
Meetings
```

Middle:

- acquisition funnel
- best campaigns
- hot opportunities
- recent conversations

Bottom:

- AI recommendations
- tasks
- system notifications

---

# 117. Prospect Table

Columns:

- company
- contact
- country
- industry
- score
- intent
- signals
- status
- campaign
- owner
- last activity

Actions:

- research
- add to campaign
- assign
- export
- suppress

---

# 118. Campaign Analytics

Show:

- audience
- messages sent
- delivery
- replies
- positive replies
- qualified
- meetings
- opportunities
- customers
- revenue
- ROI

The visual hierarchy must prioritize qualified opportunities and revenue.

---

# 119. AI Explainability

Whenever AI makes a recommendation, provide:

- recommendation
- reason
- evidence
- confidence
- editable assumptions

Example:

> **High opportunity**

> Confidence: 87%

> Evidence:
> - company is expanding
> - hiring relevant role
> - technology matches
> - target geography matches

---

# 120. Data Retention

Implement configurable retention policies for:

- messages
- contact information
- research
- AI logs
- analytics

Enterprise customers may require custom policies.

---

# 121. Account Deletion

Users must be able to request deletion.

Deletion flow:

1. confirmation
2. grace period where appropriate
3. revoke integrations
4. delete/anonymize eligible data
5. retain minimum legally required records
6. confirm completion

---

# 122. Export

Organization export should include:

- companies
- people
- leads
- campaigns
- conversations where permitted
- opportunities
- customers
- revenue
- configuration

Use asynchronous export jobs.

---

# 123. Enterprise Readiness

Future:

- SSO
- SAML
- SCIM
- audit exports
- advanced roles
- dedicated infrastructure
- custom retention
- SLA
- security questionnaires
- DPA
- custom data residency where viable

---

# 124. Business Model

Potential revenue streams:

1. Subscription
2. Usage
3. AI credits
4. Premium enrichment
5. Team seats
6. Enterprise contracts
7. API usage
8. Agency plans
9. Advanced intelligence

Do not make pricing unnecessarily complex.

---

# 125. Long-Term Product Expansion

### Stage 1

AI prospecting.

### Stage 2

Customer acquisition.

### Stage 3

AI sales.

### Stage 4

Revenue intelligence.

### Stage 5

Market intelligence.

### Stage 6

Global customer acquisition network.

The ultimate vision:

> A company can enter the platform, describe what it sells, and continuously receive the highest-probability business opportunities across the markets it wants to serve.

---

# 126. Long-Term Network Effect

Potential network loop:

```text
Businesses
   ↓
Prospects
   ↓
Interactions
   ↓
Sales outcomes
   ↓
Conversion intelligence
   ↓
Better predictions
   ↓
Better prospect recommendations
   ↓
More successful businesses
   ↓
More businesses
```

This creates a data advantage that becomes more valuable over time.

---

# 127. Founder Validation Strategy

Before building the full platform:

1. Use TryNoBot as internal customer.
2. Pick one narrow vertical.
3. Manually source prospects.
4. Manually research prospects.
5. Manually personalize outreach.
6. Track replies.
7. Track meetings.
8. Track customers.
9. Identify repeated tasks.
10. Automate only the repeated tasks.

The objective is to prove:

> **The workflow produces customer acquisition results before investing heavily in infrastructure.**

---

# 128. First Vertical Recommendation

Recommended initial vertical:

**African B2B technology companies.**

Subsegments:

- SaaS
- cybersecurity
- fintech infrastructure
- AI
- logistics software
- software agencies
- developer tools

---

# 129. First Customer Offer

Possible early offer:

> **We will build and run your first AI-powered B2B prospecting campaign and help you identify your first 100 high-fit prospects.**

Early customers receive high-touch onboarding.

Do not promise guaranteed customers.

Promise measurable work and transparent reporting.

---

# 130. First 10 Customer Strategy

Acquire through:

- founder network
- LinkedIn
- African startup communities
- direct founder outreach
- technology communities
- accelerator networks
- agencies
- existing professional contacts

Use the platform itself to acquire customers only after the basic engine works.

---

# 131. Success Criteria

MVP success requires evidence that:

- users can understand the product quickly
- AI produces useful ICPs
- prospect recommendations are relevant
- buying signals are useful
- users trust AI explanations
- campaigns can be launched safely
- conversations can be managed
- qualified opportunities are created
- customers can attribute revenue

Most importantly:

> **Real customers must report that the platform helped them create real business opportunities.**

---

# 132. Product Quality Bar

The product should never optimize for the appearance of intelligence.

It should optimize for:

**accurate data → relevant prospects → useful conversations → qualified opportunities → customers → revenue.**

---

# 133. Final Product Definition

## Product name

Working name:

**AI Customer Acquisition OS**

The final brand name can be decided separately.

## Category

AI-powered B2B customer acquisition platform.

## Initial customer

African B2B startups and SMEs.

## Global customer

B2B companies worldwide.

## Core input

Website + product/service + target market.

## Core output

Qualified opportunities and customers.

## Core promise

> **We help you find companies that need what you sell, reach the right decision makers, start relevant conversations, qualify opportunities, and connect acquisition activity to revenue.**

## Strategic positioning

> **Built for African businesses. Ready for the world.**

## Long-term ambition

Become the infrastructure connecting businesses that need customers with businesses that are ready to buy.

---

# 134. Recommended Build Order

The engineering team should implement in this order:

## Phase 0 — Validation

- TryNoBot internal experiment
- 5–10 external design partners
- manual prospecting
- manual research
- manual campaigns
- conversion tracking

## Phase 1 — Foundation

- Django
- DRF
- PostgreSQL
- Redis
- Celery
- authentication
- organizations
- billing foundation
- audit logging

## Phase 2 — Intelligence

- website analysis
- company understanding
- ICP
- prospect search
- company intelligence
- signals
- scoring

## Phase 3 — Acquisition

- email integrations
- personalization
- campaign builder
- sequences
- suppression
- inbox

## Phase 4 — Sales

- AI reply classification
- CRM
- meetings
- opportunities
- revenue attribution

## Phase 5 — African Advantage

- country intelligence
- WhatsApp Business integration
- local currencies
- localized playbooks
- French support
- African business research

## Phase 6 — Growth

- SEO website
- AEO content
- free tools
- research reports
- case studies
- comparison pages

## Phase 7 — Scale

- CRM integrations
- API
- enterprise
- advanced AI agents
- global data
- predictive intent

---

# 135. Definition of Done for MVP

The MVP is complete only when a new user can:

1. Register.
2. Create an organization.
3. Enter their website.
4. Receive an AI-generated company profile.
5. Confirm/edit the profile.
6. Generate an ICP.
7. Select a target country.
8. Search for prospects.
9. View company intelligence.
10. See why a prospect is recommended.
11. View buying signals.
12. Generate AI research.
13. Create personalized outreach.
14. Connect an email account.
15. Launch a compliant campaign.
16. Receive replies.
17. Have replies classified.
18. Qualify a prospect.
19. Book a meeting.
20. Create an opportunity.
21. Mark a deal as won.
22. Record revenue.
23. See the campaign's contribution to revenue.
24. Receive an AI recommendation for improving acquisition.
25. Export their data.
26. Manage opt-outs/suppression.
27. Manage billing.
28. Delete their account.

If this flow works reliably, the platform has the core product.

---

# 136. Final Strategic Rule

The product must always answer three questions:

### 1. Who should I sell to?

**Prospect intelligence.**

### 2. Why should I contact them now?

**Buying signals + evidence.**

### 3. Did contacting them make money?

**Revenue attribution.**

Everything else supports these three questions.

The company should not become another tool that proudly says:

> "We sent one million emails."

It should become the platform that can say:

> **"We helped our customers identify 2,400 high-intent companies, create 380 qualified opportunities, close 74 customers, and generate measurable revenue."**

That is the standard the product should be designed around.
