# Feature Backlog

Bucket for ideas + future features captured during day-to-day use of the
dashboard / templates that aren't urgent enough to do *now*. Add the rule
and the *why* — future-you (or a future Claude session) decides priority.

Format per entry:
- short title
- **Source:** who/when it surfaced
- **Why:** the user pain or opportunity it solves
- **Sketch:** rough scope, file pointers, or open questions

---

## Customer reviews on the website

**Source:** Prashant, 2026-05-11 — found while reviewing the
`order_delivered_feedback` email rendering in Gmail.

**Why:** The "⭐ Share Your Feedback" CTA in that email currently points to
`himalayanfibres.com/reviews`, which doesn't exist. Patched to a `mailto:`
link as interim. Long-term we want a real reviews page so customers can
self-serve and so reviews are public social proof for other buyers (key
for the sample-first trial phase — see auto-memory
`project_sample_first_phase.md`).

**Sketch:**
- New Wix page at `/reviews` (or `/customer-stories`) — captures
  star-rating + photo upload + free-text testimonial.
- Curated, moderated. We approve before publishing. Show 6–10 on the
  page; lifestyle photos > studio shots.
- Wire the CTA in `hf_dashboard/templates/emails/order_delivered_feedback.html`
  back from `mailto:…` to `https://www.himalayanfibres.com/reviews` once
  the page is live.
- Stretch: structured-data markup (`Review` schema) so Google can pick
  up the stars on search results.
- Even further: pull approved reviews into product pages, not just a
  standalone page.
