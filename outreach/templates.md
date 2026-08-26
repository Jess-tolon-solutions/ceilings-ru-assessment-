# DBPR Violation Outreach Templates

Use these templates with the enriched contact data. Personalization fields are in `{{brackets}}`.

---

## Email Sequence

### Email 1: Initial Outreach (Same day as enrichment)

**Subject:** {{restaurant_name}} — ceiling inspection follow-up

Hi {{first_name}},

I noticed {{restaurant_name}} was recently cited for ceiling and ventilation issues during your DBPR inspection ({{latest_inspection}}).

We specialize in commercial ceiling cleaning for restaurants — specifically the tile, grid, and vent work that triggers Violation 36. We've helped dozens of South Florida restaurants clear re-inspection after being cited.

Would it make sense to schedule a quick walkthrough? We can usually quote same-day and get you cleaned before your follow-up.

Best,
Jonathan
Ceilings R Us
(954) 452-0004

---

### Email 2: Follow-up (3 days later, if no reply)

**Subject:** Re: {{restaurant_name}} ceiling inspection

Hi {{first_name}},

Just following up on my note about the ceiling/ventilation citation at {{restaurant_name}}.

We work with restaurants in {{city}} regularly — most cleanings take a few hours overnight and we handle everything from tile replacement to vent covers.

Happy to send over some before/after photos from similar jobs if helpful.

Jonathan
(954) 452-0004

---

### Email 3: Final touch (7 days later)

**Subject:** Quick question, {{first_name}}

Hi {{first_name}},

I'll keep this short — is ceiling cleaning something you're handling internally, or would it help to get a quote from us?

Either way, no worries. Just wanted to make sure you had the option before your re-inspection.

Jonathan
Ceilings R Us

---

## LinkedIn Messages (Dripify Sequence)

### Connection Request

Hi {{first_name}} — I work with restaurants in {{city}} on ceiling and ventilation maintenance. Noticed {{restaurant_name}} and thought I'd connect. Would love to be a resource if you ever need ceiling tile or vent cleaning.

---

### Message 1 (After connection accepted, Day 1)

Thanks for connecting, {{first_name}}!

I actually came across {{restaurant_name}} because of the recent DBPR inspection — specifically the ceiling/ventilation citation. We specialize in exactly that kind of work for restaurants.

If you need help getting it resolved before re-inspection, happy to chat. Either way, nice to connect.

---

### Message 2 (Day 4, if no reply)

Hi {{first_name}} — just wanted to follow up. We've done a lot of ceiling cleanings for restaurants in {{city}} after DBPR citations.

Would you be open to a quick call to see if we can help? No pressure either way.

---

## Jonathan's Call Script

**Opening:**
> Hi, this is Jonathan with Ceilings R Us. I'm calling about {{restaurant_name}} — I noticed you had a DBPR inspection recently that cited some ceiling and ventilation issues.

**If they confirm:**
> Yeah, Violation 36 is one of the most common citations we see. We specialize in commercial ceiling cleaning — tile, grid, vents, all of it. Most restaurant jobs we can do overnight so you're not disrupting service.

> Would it help if I swung by to take a look and give you a quote? We can usually get you cleaned before your re-inspection window.

**If they ask about pricing:**
> It depends on the square footage and condition, but for a typical restaurant we're usually in the $1,200-$1,500 range. I can give you an exact number after a quick walkthrough — takes about 15 minutes.

**If they push back:**
> No problem at all. If you want, I can just send over some info and you can reach out if you need us down the road. What's the best email?

**Close:**
> Great, I'll send that over. And if anything comes up before your follow-up inspection, just give us a call — (954) 452-0004. We can usually get out there within a few days.

---

## Personalization Fields

These fields are available in the CSV exports:

| Field | Source | Use |
|-------|--------|-----|
| `{{first_name}}` | Apollo | Personal greeting |
| `{{last_name}}` | Apollo | Full name if needed |
| `{{restaurant_name}}` | DBPR | Restaurant name |
| `{{city}}` | DBPR | Location reference |
| `{{total_violations}}` | DBPR | Severity context |
| `{{latest_inspection}}` | DBPR | Recency/urgency |
| `{{outreach_hook}}` | DBPR | Full violation summary |
| `{{priority}}` | DBPR | HOT/WARM/MONITOR |

---

## Dripify Setup Notes

1. Import `dripify_linkedin_{date}.csv`
2. Map fields:
   - LinkedIn_URL → Profile URL
   - First_Name, Last_Name → Name fields
   - Company, Violations, Hook, City → Custom fields for personalization
3. Set sequence timing:
   - Connection request → Day 0
   - Message 1 → Day 1 (after accept)
   - Message 2 → Day 4 (if no reply)
4. Daily limit: 20-25 connection requests to stay safe

---

## Email Tool Setup

For email campaigns, import `email_campaign_{date}.csv` into your email tool:

- **Mailchimp:** Create campaign → Import CSV → Use merge tags
- **SendGrid:** Create dynamic template → Upload contacts
- **Instantly/Smartlead:** Import CSV → Set up sequence with personalization

Recommended sending:
- Max 50/day from Jonathan's email (warm domain)
- Send between 8am-11am EST (restaurant managers checking email)
- 3-day gap between sequence emails
