---
layout: post
title: Using a LLM to Classify Unstructured Text in the Electronic Health Record
subtitle: Peer-reviewed article
cover-img: "assets/img/woman-ipad.png"
thumbnail-img: "assets/img/woman-ipad.png"
share-img: "assets/img/woman-ipad.png"
tags: [large language model, predictive modeling, electronic health record, electronic medical record]
---

My colleagues and I published an article “Classifying Unstructured Text in Electronic Health Records for Mental Health Prediction Models: Large Language Model Evaluation Study" in JMIR Medical Informatics.

Here’s a quick overview of some important points

**TL;DR:** Large Language Models (LLMs) can be helpful assistants in extracting meaningful clinical features from electronic health record text for a predictive model in a mental health care setting.

**Can Large Language Models replicate clinician judgement when classifying terms from clinical notes?**
* Large Language Models (LLMs), like OpenAI’s GPT models, can streamline the classification and coding of unstructured EHR text due to their massive training data sets and advanced text processing (1, 2).
* Preliminary evidence shows that LLMs outperform crowd workers when annotating electronic medical record text data [3, 4].
* However, the reliability of LLMs in replicating clinical judgement in mental health remains uncertain, especially when considering the inherent complexities of mental health disorders. 

**We evaluated ChatGPT's behavior when classifying electronic health record terms:**
* We extracted terms from de-identified electronic health record data from the Optum Labs Data Warehouse, a longitudinal, real-world data asset, from >50 US healthcare provider organizations that encompass >700 hospitals
* A board-certified psychiatrist and licensed clinical psychologist categorized each term into 1 of 61 categories (42 mental health categories and 19 physical health categories).
* We prompted the model with 3 classification tasks which involved (1) determining whether a given term was physical health or mental health related, (2) assingining the mental health terms to one of 42 mental health categories, and (3) assigning the physical health terms to one of 19 physical health categories. 

**ChatGPT's performance varied both within and across categories**
* There was high agreement between the LLM and clinical experts when categorizing 4553 terms as “mental health” or “physical health” (κ=0.77, 95% CI 0.75-0.80)
*  However, there was still considerable variability in LLM-clinician agreement on the classification of mental health terms (κ=0.62, 95% CI 0.59‐0.66) and physical health terms (κ=0.69, 95% CI 0.67‐0.70).

**How can we integrate LLMs into health care prediction models?**

* The accuracy of clinical term classification is essential for downstream predictive models that rely on structured data, as inaccuracies can propagate through the model pipeline.
* As LLMs advance, there is potential for these models to bypass the traditional 2-stage process and make direct predictions from unstructured text (5).
* One day... LLMs have the potential to be integrated into EHR systems to create text-based features for real-time prediction models.

**References:**
1. Bousselham H, Nfaoui EH, Mourhir A. Fine-tuning GPT on biomedical NLP tasks: an empirical evaluation. Presented at: 2024 International Conference on Computer, Electrical & Communication Engineering (ICCECE); Feb 2-3, 2024; Kolkata, India.
2. OpenAI, Achiam J, Adler S, et al. GPT-4 technical report. arXiv. Preprint posted online on Mar 15, 2023.
3. Gilardi F, Alizadeh M, Kubli M. ChatGPT outperforms crowd workers for text-annotation tasks. Proc Natl Acad Sci U S Jul 25, 2023;120(30):e2305016120
4. Törnberg P. ChatGPT-4 outperforms experts and crowd workers in annotating political twitter messages with zero-shot learning. arXiv. Preprint posted online on Apr 13, 2023


[Link to to the publication at *JMIR Medical Informatics.*](https://medinform.jmir.org/2025/1/e65454/)

