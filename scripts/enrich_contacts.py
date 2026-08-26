#!/usr/bin/env python3
"""
DBPR Violation Contact Enrichment via Apollo.io

Reads violation data, enriches with contact details from Apollo,
and outputs files ready for:
  1. Jonathan's call list
  2. Dripify LinkedIn import
  3. Email campaign

Usage:
    export APOLLO_API_KEY="your-api-key-here"
    python3 scripts/enrich_contacts.py

Or pass key directly:
    python3 scripts/enrich_contacts.py --api-key YOUR_KEY
"""

import json
import os
import sys
import csv
import time
import urllib.request
import urllib.parse
from datetime import date, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

HERE = Path(__file__).parent
REPO = HERE.parent
VIOLATION_DATA = REPO / "violation-data.json"
OUTPUT_DIR = REPO / "outreach"

APOLLO_API_BASE = "https://api.apollo.io/v1"

# Target titles for restaurant decision-makers
TARGET_TITLES = [
    "owner",
    "general manager",
    "facility manager",
    "operations manager",
    "district manager",
    "regional manager",
    "managing partner",
    "proprietor",
    "ceo",
    "president",
    "director of operations",
]

USER_AGENT = "CRU-Outreach/1.0"

# ---------------------------------------------------------------------------
# Apollo API Functions
# ---------------------------------------------------------------------------

def apollo_request(endpoint: str, api_key: str, data: dict) -> dict:
    """Make a POST request to Apollo API."""
    url = f"{APOLLO_API_BASE}/{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "X-Api-Key": api_key,
    }

    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        print(f"  Apollo API error {e.code}: {error_body[:200]}")
        return {}
    except Exception as e:
        print(f"  Apollo request failed: {e}")
        return {}


def search_organization(api_key: str, name: str, city: str, state: str = "FL") -> dict:
    """Search for an organization by name and location."""
    data = {
        "q_organization_name": name,
        "organization_locations": [f"{city}, {state}"],
        "per_page": 1,
    }

    result = apollo_request("mixed_companies/search", api_key, data)
    orgs = result.get("organizations", [])
    return orgs[0] if orgs else {}


def search_contacts(api_key: str, org_id: str = None, org_name: str = None,
                    city: str = None, titles: list = None) -> list:
    """Search for contacts at an organization."""
    data = {
        "per_page": 5,
        "person_titles": titles or TARGET_TITLES,
    }

    if org_id:
        data["organization_ids"] = [org_id]
    elif org_name:
        data["q_organization_name"] = org_name
        if city:
            data["person_locations"] = [f"{city}, FL"]

    result = apollo_request("mixed_people/search", api_key, data)
    return result.get("people", [])


def enrich_contact(api_key: str, person_id: str) -> dict:
    """Get full contact details including email."""
    data = {"id": person_id}
    result = apollo_request("people/match", api_key, data)
    return result.get("person", {})


# ---------------------------------------------------------------------------
# Main Processing
# ---------------------------------------------------------------------------

def load_violations() -> list:
    """Load violation data from JSON."""
    with open(VIOLATION_DATA) as f:
        data = json.load(f)

    # Handle both formats (list or dict with 'restaurants' key)
    if isinstance(data, list):
        return data
    return data.get("restaurants", [])


def enrich_violations(api_key: str, violations: list) -> list:
    """Enrich each violation record with contact data."""
    enriched = []

    for i, v in enumerate(violations, 1):
        name = v.get("name", "")
        city = v.get("city", "")

        print(f"[{i}/{len(violations)}] {name}...")

        record = {
            "restaurant_name": name,
            "address": v.get("address", ""),
            "city": city,
            "zip": v.get("zip", ""),
            "total_violations": v.get("total_violations", v.get("totalViolations", 0)),
            "priority": v.get("priority", ""),
            "outreach_hook": v.get("outreach_hook", ""),
            "latest_inspection": v.get("latest_inspection", ""),
            "disposition": v.get("disposition", ""),
            "license": v.get("license", ""),
            "contacts": [],
        }

        # Search for organization first
        org = search_organization(api_key, name, city)
        time.sleep(0.3)  # Rate limiting

        org_id = org.get("id") if org else None

        # Search for contacts
        contacts = search_contacts(
            api_key,
            org_id=org_id,
            org_name=name if not org_id else None,
            city=city,
            titles=TARGET_TITLES
        )
        time.sleep(0.3)

        for contact in contacts[:3]:  # Max 3 contacts per restaurant
            c = {
                "name": f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip(),
                "first_name": contact.get("first_name", ""),
                "last_name": contact.get("last_name", ""),
                "title": contact.get("title", ""),
                "email": contact.get("email", ""),
                "phone": "",
                "linkedin_url": contact.get("linkedin_url", ""),
                "organization": contact.get("organization", {}).get("name", name),
            }

            # Try to get phone if available
            phones = contact.get("phone_numbers", [])
            if phones:
                c["phone"] = phones[0].get("sanitized_number", "")

            record["contacts"].append(c)
            print(f"    Found: {c['name']} - {c['title']}")

        if not contacts:
            print(f"    No contacts found")

        enriched.append(record)

    return enriched


def generate_outputs(enriched: list):
    """Generate output files for outreach."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    today = date.today().isoformat()

    # 1. Jonathan's Call List
    call_list_path = OUTPUT_DIR / f"jonathan_call_list_{today}.csv"
    with open(call_list_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Restaurant", "Contact_Name", "Title", "Phone", "Email",
            "Violations", "Priority", "Hook", "Address", "City"
        ])

        for r in enriched:
            for c in r["contacts"]:
                if c.get("phone") or c.get("email"):
                    writer.writerow([
                        r["restaurant_name"],
                        c["name"],
                        c["title"],
                        c["phone"],
                        c["email"],
                        r["total_violations"],
                        r["priority"],
                        r["outreach_hook"],
                        r["address"],
                        r["city"],
                    ])

    print(f"\nCreated: {call_list_path}")

    # 2. Dripify LinkedIn Import
    dripify_path = OUTPUT_DIR / f"dripify_linkedin_{today}.csv"
    with open(dripify_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "LinkedIn_URL", "First_Name", "Last_Name", "Company", "Title",
            "Violations", "Hook", "City"
        ])

        for r in enriched:
            for c in r["contacts"]:
                if c.get("linkedin_url"):
                    writer.writerow([
                        c["linkedin_url"],
                        c["first_name"],
                        c["last_name"],
                        r["restaurant_name"],
                        c["title"],
                        r["total_violations"],
                        r["outreach_hook"],
                        r["city"],
                    ])

    print(f"Created: {dripify_path}")

    # 3. Email Campaign CSV
    email_path = OUTPUT_DIR / f"email_campaign_{today}.csv"
    with open(email_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Email", "First_Name", "Last_Name", "Company", "Title",
            "Violations", "Priority", "Hook", "Inspection_Date", "City", "Address"
        ])

        for r in enriched:
            for c in r["contacts"]:
                if c.get("email"):
                    writer.writerow([
                        c["email"],
                        c["first_name"],
                        c["last_name"],
                        r["restaurant_name"],
                        c["title"],
                        r["total_violations"],
                        r["priority"],
                        r["outreach_hook"],
                        r["latest_inspection"],
                        r["city"],
                        r["address"],
                    ])

    print(f"Created: {email_path}")

    # 4. Full enriched JSON (for reference/debugging)
    json_path = OUTPUT_DIR / f"enriched_violations_{today}.json"
    with open(json_path, "w") as f:
        json.dump(enriched, f, indent=2)

    print(f"Created: {json_path}")

    # Summary
    total_contacts = sum(len(r["contacts"]) for r in enriched)
    with_phone = sum(1 for r in enriched for c in r["contacts"] if c.get("phone"))
    with_email = sum(1 for r in enriched for c in r["contacts"] if c.get("email"))
    with_linkedin = sum(1 for r in enriched for c in r["contacts"] if c.get("linkedin_url"))

    print(f"\n{'='*50}")
    print(f"ENRICHMENT SUMMARY")
    print(f"{'='*50}")
    print(f"Restaurants processed:  {len(enriched)}")
    print(f"Contacts found:         {total_contacts}")
    print(f"  With phone:           {with_phone}")
    print(f"  With email:           {with_email}")
    print(f"  With LinkedIn:        {with_linkedin}")
    print(f"{'='*50}")


def main():
    # Get API key
    api_key = os.environ.get("APOLLO_API_KEY")

    if "--api-key" in sys.argv:
        idx = sys.argv.index("--api-key")
        if idx + 1 < len(sys.argv):
            api_key = sys.argv[idx + 1]

    if not api_key:
        print("Error: Apollo API key required")
        print()
        print("Set it via environment variable:")
        print("  export APOLLO_API_KEY='your-key-here'")
        print()
        print("Or pass directly:")
        print("  python3 scripts/enrich_contacts.py --api-key YOUR_KEY")
        sys.exit(1)

    print("DBPR Violation Contact Enrichment")
    print("=" * 50)

    # Load violations
    violations = load_violations()
    print(f"Loaded {len(violations)} violation records\n")

    # Enrich with Apollo
    enriched = enrich_violations(api_key, violations)

    # Generate output files
    generate_outputs(enriched)

    print("\nDone! Files ready in:", OUTPUT_DIR)


if __name__ == "__main__":
    main()
