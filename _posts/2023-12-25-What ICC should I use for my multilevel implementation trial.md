---
layout: post
title: What ICC should I use for my multilevel implementation trial?
subtitle: A conference abstract
cover-img: "https://en.wikipedia.org/wiki/Intraclass_correlation#/media/File:ICC-example2.svg"
thumbnail-img: "https://en.wikipedia.org/wiki/Intraclass_correlation#/media/File:ICC-example2.svg"
share-img: "https://en.wikipedia.org/wiki/Intraclass_correlation#/media/File:ICC-example2.svg"
tags: [dissemination, implementation science, ICC, multilevel modeling]
---

I recently presented an abstact at the 16th Annual Dissemination and Implementation Conference by AcademyHealth, "Meaningful clustering coefficient estimates for multilevel implementation trials in behavioral health." Here's a primer about clustering:

TLDR: If you're designing a study with clusters (e.g. providers within clinics, patients within providers), it's crucial to account for the correlation of responses within clusters. 

**ICCs are critical but not frequently reported in implementation research.**
* The intraclass correlation coefficient (ICC) is a critical parameter in statistical power analyses for multilevel implementation studies but is frequently not reported in published manuscripts (1).
* Intraclass correlations are inversely related to power (2).

**We reviewed published cluster-randomized control trials in implementation science and asked for their data.**
* We collected primary data of implementation and clinical outcomes from NIMH-funded cluster randomized studies 2010-2020.
* We pooled estimates of ICCs and examined drivers of ICC magnitude.
* Seventeen trials met inclusion criteria. We extracted the essential statistics to compute ICCs and standard errors of n=31 outcomes from n=10 studies.

**How your data is structured matters:**
* Cross-sectional ICCs at level 3 and level 2 were 0.10 (95% CI = 0.05-0.15) and 0.13 (95% CI =  0.07-0.20), respectively.
* Estimates of ICCs of multiple measurement occasions within units was 0.44 (95% CI = 0.31-0.55).

**How your outcomes are measured matters:**
* Although ICC estimates of implementation outcomes and clinical outcomes were not significantly different (0.26 vs. 0.24, p = .80), externally measured outcomes (e.g. rater coded, observation, etc.) had significantly lower ICC estimates relative to outcomes measured via provider self-report (0.15 vs. 0.22, p = .03).

**You might not be able to see ICC, but its there!**
* The estimates of ICC presented here contribute to the production of impactful and replicable implementation science, more efficient use of research resources, and refinement of strategies to improve healthcare delivery in behavioral health. 

**References:**
1. Hedges LV, Hedberg EC. Intraclass Correlation Values for Planning Group-Randomized Trials in Education. Educational Evaluation and Policy Analysis. 2007;29:60–87.
2. Snijders TAB, Bosker RJ. Multilevel analysis: an introduction to basic and advanced multilevel modeling. London ; Thousand Oaks, Calif: Sage Publications; 1999.
3. Proctor, E., Silmere, Ha Raghavan, R., Hovmand, P., Aarons, G., Bunger, A., ... & Hensley, M. (2011). Outcomes for implementation research: conceptual distinctions, measurement challenges, and research agenda. Administration and policy in mental health and mental health services research, 38, 65-76.
4. Zeileis, A., Lumley, T., Berger, S., Graham, N., & Zeileis, M. A. (2019). Package ‘sandwich’. R package version, 2-5.


[Link to to the conference abstact at *AcademyHealth*](https://academyhealth.confex.com/academyhealth/2023di/meetingapp.cgi/Paper/62932)

