# Tuning log

How phishscan's rules changed as they were tested against real email. Every change below
was made because a real sample behaved badly, and every change was rechecked against the
legitimate-mail set to make sure false positives did not creep in.

## Method

- **Legitimate set:** real emails exported from a personal inbox as `.eml`
  (newsletters, alerts, marketing). Kept out of the repo because they contain personal data.
- **Tuning set:** random emails from the phishing_pot honeypot corpus. Rounds 1 and 2 used
  50; from Round 3 on, a larger random sample of 500 (498 after removing duplicates, see below).
- **Holdout set:** a separate random 50 from the same corpus. Not examined while writing
  rules; only scored to measure them. It is checked for duplicates against the tuning set
  by content and Message-ID, not filename, because the corpus renumbers its files.
- **Metric:** an email is "detected" if the verdict is SUSPICIOUS or LIKELY PHISHING.
  A "false positive" is a legitimate email that gets that verdict.

## Round 1: false positives on legitimate email

| Email | Problem | Fix |
|---|---|---|
| Large tech-brand marketing email | Word "limited" in ordinary marketing copy triggered the pressure-language rule | Changed the phrase to "has been limited" |
| Health newsletter | `google-analytics.com` flagged as imitating Google | Added Google's real analytics, API and content domains to the brand allow-list |
| Small-business newsletter (score 65, LIKELY PHISHING) | `amazonses.com` (Amazon's real bulk-mail service) in the bounce address flagged as an Amazon imitation | Added `amazonses.com` and related domains; stopped lookalike-checking the Return-Path, which readers never see |
| Same email | Link text showed the sender's site but the link went through a marketing click-tracker | New rule: a mismatch whose destination is a known tracker domain drops to LOW **only if the email passed DMARC**; unknown redirect domains and unauthenticated emails stay HIGH |

Also changed: the report now summarizes URLs by domain instead of printing every link
(newsletters can contain 60+), which also stops tracking tokens being echoed in output.

Result: 0 false positives on the legitimate set.

## Round 2: missed phishing

First run on the 50-email tuning set: **20 of 50 detected (40%)**, with 30 missed.
Reviewing the misses (with `phishscan.triage`) showed repeating patterns:

| Pattern seen in real samples | Rule added |
|---|---|
| Sender domains with no TLD, invalid characters, or 28-character random strings | `invalid_sender_domain`, `random_sender_domain` (high) |
| From header with no email address at all | `no_sender_address` (medium) |
| Display names like "UPS.", "Trust Wallet", "Mercado Pago", "Total AV" on unrelated domains | Larger brand list; smarter name matching (whole words, run-together names, safe handling of short names like "ups") |
| Subject naming a brand ("McAfee ...") from an unrelated sender | `brand_in_subject_mismatch` (medium) |
| Links on `.store` / `.site` / `.art` domains | `risky_tld_link` (medium) |
| Links on `run.app`, `blogspot.com` and similar free platforms | `free_hosting_link` (medium) |
| Hostnames containing a raw IP address | `ip_in_hostname` (medium) |
| Advance-fee scam ("I got your contact ... this will be a surprise") | `scam_language` (medium, high with two or more phrases) |
| Account-lure wording: storage full, wallet/KYC, subscription expired | Added to the low-weight pressure phrases |
| More link shorteners (`goo.su` and others) | Added to the shortener list |

Safeguards added alongside: very short brand names only match as whole words, so
`upstream.com` is not read as UPS. URL-pattern rules are medium on purpose, so they only
push an email over the line when combined with other signals.

A corpus quirk is ignored deliberately: phishing_pot replaces the honeypot's own address
with `phishing@pot`. That is a collection artifact, so treating it as a signal would
inflate the results.

Result on the 50-email tuning set: **37 of 50 detected (74%)**, 0 false positives on the
legitimate set. This number is optimistic, because the rules were written after studying
these emails.

## Round 3: robustness, encoded IPs, free-webmail Reply-To

Switched to a larger tuning set (500 random phishing_pot emails). Baseline before this
round's rules: **349 of 500 detected (70%)**.

| Problem | Change |
|---|---|
| The holdout run crashed on a link like `http://[abc/x`: Python's `urlparse()` raises `ValueError` ("invalid IPv6 URL") on it | New `safe_hostname()` in `parser.py` returns `""` for malformed URLs; every module now uses it instead of calling `urlparse()` directly. One bad link can no longer stop a scan. Covered by a unit test and an end-to-end test |
| Links whose hostname is a bare number (`http://2997024026/`, or hex `0x...`) are IP addresses in disguise. Browsers accept them; legitimate mail does not use them | `encoded_ip_host` (high) in `urlchecks.py` |
| Messages from a business domain whose Reply-To sends answers to Gmail, Outlook, Yahoo and similar free webmail | `reply_to_freemail` (high) in `checks.py`. Only fires when the From domain is *not* itself free webmail |

Data hygiene: two holdout emails were also in the 500-email tuning set under different
filenames (byte-identical, same Message-ID). They were removed from the tuning set,
leaving 498.

Results with the current code:

| Set | Result |
|---|---|
| Tuning set | **354 of 498 detected (71%)**, up from 349/500 (70%) |
| Holdout | **35 of 50 detected (70%)** |
| Legitimate set | **0 of 7 false positives**. Neither new rule fired on legitimate mail (the set grew to 76 in Round 4) |

The tuning gain is small (+6 emails before de-duplication): the new rules target narrow,
high-confidence patterns rather than broad ones. Note that a free-webmail Reply-To also
triggers the existing `reply_to_mismatch`, so the two stack (45 points); that is
intended, as the combination is a strong signal on its own.

## Round 4: false positives on a 76-email legit set

The legitimate set grew from 7 to 76 emails (37 senders, 29 domains) by exporting a
mailbox and splitting it with `tools/mbox_to_eml.py`, which skips any Message-ID already
in the set. On the bigger set the false-positive rate was **7 of 76 (9%)**, so the 0/7
from earlier rounds had been hiding real problems.

All 7 came from two causes:

- **Job-alert emails from a job board (4):** subjects name the hiring company, which can be
  a brand on the brand list, and that fired `brand_in_subject_mismatch`, and a link to Apple's real
  `applemediaservices.com` was read as an Apple imitation (`brand_in_domain`, high).
- **Retail newsletters (3):** link text shows one of the sender's sites but the link goes
  through a click tracker, either the sender's own (`url.<sender-domain>`) or a
  marketing platform not on the tracker list. One of these scored LIKELY PHISHING.

Every sender involved passed DMARC. Each fix was made on its own and all three sets were
re-run after each one:

| Step | Change | Tuning (498) | Holdout (50) | Legit false positives (76) |
|---|---|---|---|---|
| 0 | Starting point | 354 (71.1%) | 35 (70%) | **7 (9.2%)** |
| 1 | No `link_text_mismatch` when the link goes to the sender's own registered domain **and** DMARC passed | 354 | 35 | 5 (6.6%) |
| 2 | `applemediaservices.com` added to Apple's real domains | 354 | 35 | 1 (1.3%) |
| 3 | `bloomreach.com` added to the known tracker list | 354 | 35 | **0 (0%)** |
| 4 | Urgent phrases must start at a word boundary; short ones (`kyc`) must be whole words | 354 | 35 | 0 |
| 5 | `brand_in_subject_mismatch` drops to low when DMARC passes (medium otherwise) | 354 | 35 | 0 |

Notes:

- **No phishing verdict changed** on either set at any step.
- Step 1 adds no finding at all, rather than a low one, because each low finding adds 5
  points and a newsletter with many self-tracked links would add up past the threshold.
- Step 4: `kyc` had been matching inside random tracking tokens in 62 tuning emails,
  quietly adding 5 points to each. A first version required a boundary on both ends,
  which also stopped "urgent" from matching "urgently" and the Portuguese "urgente"
  (7 tuning emails). The final rule only requires the end boundary for phrases shorter
  than 5 letters.
- Steps 4 and 5 changed scores but no verdicts. They were kept as safety margin: the job
  alerts now score 5, not 45, so a single extra weak signal can't push them over.
- **Caveat:** 0/76 is a tuning result, since the rules were fixed against these exact
  emails. Fresh legitimate mail is needed to measure the real rate. The holdout was
  scored after every step but never used to choose a change.

## Known misses (not fixed on purpose)

- German weight-loss spam from a clean, authenticated domain: spam rather than credential phishing.
- An empty message.
- A message that looks like a genuine "you have unsubscribed" confirmation, probably mislabeled in the corpus.
- Non-English, text-only scams: the wording rules are English only.

## Holdout result

Holdout set: **35 of 50 detected (70%)** with the Round 3 and Round 4 code. An earlier
run with the Round 2 code detected 34 of 50 (68%).

## Ideas not done

- Language-independent signals (sender/domain age, URL structure) instead of wording lists.
- Threshold sweep: plot detection vs false positives as the SUSPICIOUS cutoff moves.
- A fresh legitimate set that was not used for tuning, to measure the false-positive
  rate independently (the 76-email set has now been tuned against).
- Web interface for pasting an email or link.
