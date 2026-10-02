---
name: seo
description: Comprehensive Technical SEO, Schema.org, Core Web Vitals, and Generative Engine Optimization (GEO / AI search readiness) audit and optimization suite. Use when auditing website SEO, generating or validating JSON-LD schemas, configuring robots.txt/sitemaps, optimizing for Google AI Overviews / Perplexity, or fixing crawlability and social meta tags.
---

# SEO & Generative Engine Optimization (GEO) Suite

A comprehensive, 2026-compliant SEO audit and optimization workflow for modern web applications, ported from the `claude-seo` architecture into a native Antigravity skill.

## 1. Audit Workflow

When asked to audit a website, page, or repository:

1. **Discovery & Crawlability**:
   - Inspect `robots.txt` (allowed/disallowed paths, sitemap declarations, AI crawler directives).
   - Check `sitemap.xml` (valid XML format, absolute canonical URLs, priorities, and change frequencies).
   - Verify canonical link tags (`<link rel="canonical" href="..." />`) to prevent duplicate content penalties.
   - Detect Client-Side Rendering (CSR/SPA) vs Server-Side Rendering (SSR). If the page requires client-side JS to render `<head>` meta tags or main body content, flag the risk for search engines that defer JS execution.
   - Check for auth redirects: Ensure pages listed in `sitemap.xml` do not immediately redirect unauthenticated crawlers to `/login` (Soft 404).

2. **Structured Data & Schema.org (2026 Standards)**:
   - **Supported High-Impact Schemas**:
     - `SoftwareApplication` / `WebApplication` for SaaS & web apps (`applicationCategory`, `operatingSystem`, `offers`, `featureList`).
     - `Organization` with `logo`, `sameAs`, `contactPoint`, and `url`.
     - `WebSite` with `SearchAction` (Sitelinks Searchbox).
     - `Product` & `Offer` for pricing tiers.
     - `Article` / `BlogPosting` for content pages.
   - **Deprecated Schemas to Flag/Avoid**:
     - ⚠️ `FAQPage`: Google completely retired FAQ rich snippets for commercial websites on May 7, 2026. Do not rely on FAQPage schema for SERP enhancements; use genuine `QAPage` only for user forum communities.
     - ⚠️ `HowTo`: Deprecated by Google since Sept 2023.
     - ⚠️ `SpecialAnnouncement`: Deprecated July 2025.
   - **Validation Checklist**:
     - Valid JSON-LD inside `<script type="application/ld+json">`.
     - Absolute HTTPS URLs for all `@id`, `url`, and `logo` properties.
     - No orphan schemas; interconnect entities using `@graph`.

3. **Core Web Vitals & Performance (2026 Thresholds)**:
   - **INP (Interaction to Next Paint)**:
     - Good: $\le$ 200ms
     - Needs Improvement: 200ms – 500ms
     - Poor: > 500ms
     *(FID is deprecated; INP is the sole metric for user interactivity).*
   - **LCP (Largest Contentful Paint)**: Good $\le$ 2.5s.
   - **CLS (Cumulative Layout Shift)**: Good $\le$ 0.1.

4. **Generative Engine Optimization (GEO) & AI Search Readiness**:
   - **AI Bot Directives**: Ensure `robots.txt` explicitly addresses modern AI agents:
     ```txt
     User-agent: GPTBot
     Allow: /

     User-agent: ClaudeBot
     Allow: /

     User-agent: PerplexityBot
     Allow: /

     User-agent: Google-Extended
     Allow: /

     User-agent: Applebot-Extended
     Allow: /
     ```
   - **`llms.txt` and `llms-full.txt`**:
     - Provide `/llms.txt` in the root public directory summarizing project purpose, core capabilities, and key links.
     - Provide `/llms-full.txt` for comprehensive technical specs, API references, and architecture details.
   - **Citability & Inverted Pyramid**:
     - Place direct, factual, declarative answers in the first 200 words of pages and feature sections so LLMs (ChatGPT, Perplexity, Google AI Overviews) can quote them directly.
   - **Lighthouse Agentic Browsing Readiness**:
     - Accessible names (`aria-label`) on all interactive buttons/icons.
     - Explicit `<label for="...">` bindings for all form fields.
     - Semantic landmark tags (`<header>`, `<nav>`, `<main>`, `<section>`, `<footer>`).

5. **Social Metadata & Open Graph**:
   - `<meta property="og:title" ... />`
   - `<meta property="og:description" ... />`
   - `<meta property="og:image" ... />` (must point to an existing, valid image or SVG asset with 1200x630 dimensions).
   - `<meta name="twitter:card" content="summary_large_image" />`
   - Theme color, favicon, and Apple touch icon declarations.

## 2. Generating Audit Reports

When executing a full audit, produce a structured markdown report containing:
1. **Executive Summary & Overall Health Score (0-100)**.
2. **Critical Findings (P0 - Immediate Fixes)**: Broken links, missing assets, auth walls on sitemap URLs, missing title/description.
3. **High-Priority Improvements (P1)**: Schema.org JSON-LD upgrades, AI crawler directives, OpenGraph assets.
4. **Medium-Priority Optimizations (P2)**: `llms-full.txt` creation, semantic ARIA landmarks, Core Web Vitals optimizations.
5. **Step-by-Step Prioritized Action Plan**.
