#!/usr/bin/env python3
"""
Generate outreach lists from completed Sales Navigator lookup sheet.

Usage:
    python3 scripts/generate_outreach_lists.py outreach/sales_nav_lookup.xlsx
"""

import sys
import csv
from pathlib import Path
from datetime import date

try:
    import pandas as pd
except ImportError:
    print("Error: pandas required. Install with: pip install pandas openpyxl")
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        input_path = Path(__file__).parent.parent / "outreach" / "sales_nav_lookup.xlsx"
    else:
        input_path = Path(sys.argv[1])

    if not input_path.exists():
        print(f"Error: File not found: {input_path}")
        sys.exit(1)

    print(f"Reading: {input_path}")
    df = pd.read_excel(input_path, sheet_name='Lookup')

    # Filter to rows with contact info
    has_contact = df['Contact_Name'].notna() & (df['Contact_Name'] != '')
    contacts_df = df[has_contact].copy()

    if len(contacts_df) == 0:
        print("\nNo contacts found in the sheet yet.")
        print("Fill in the green columns (Contact_Name, Title, LinkedIn_URL, etc.) and run again.")
        sys.exit(0)

    print(f"Found {len(contacts_df)} contacts")

    output_dir = input_path.parent
    today = date.today().isoformat()

    # 1. Dripify LinkedIn Import
    has_linkedin = contacts_df['LinkedIn_URL'].notna() & (contacts_df['LinkedIn_URL'] != '')
    linkedin_df = contacts_df[has_linkedin]

    if len(linkedin_df) > 0:
        dripify_path = output_dir / f"dripify_import_{today}.csv"

        # Split name into first/last
        def split_name(name):
            parts = str(name).strip().split(' ', 1)
            return parts[0], parts[1] if len(parts) > 1 else ''

        linkedin_out = []
        for _, row in linkedin_df.iterrows():
            first, last = split_name(row['Contact_Name'])
            linkedin_out.append({
                'LinkedIn_URL': row['LinkedIn_URL'],
                'First_Name': first,
                'Last_Name': last,
                'Company': row['Restaurant'],
                'Title': row.get('Title', ''),
                'Violations': row['Violations'],
                'Hook': row['Outreach_Hook'],
                'City': row['City'],
            })

        pd.DataFrame(linkedin_out).to_csv(dripify_path, index=False)
        print(f"Created: {dripify_path} ({len(linkedin_out)} contacts)")

    # 2. Jonathan Call List (contacts with phone OR email)
    has_phone_or_email = (
        (contacts_df['Phone'].notna() & (contacts_df['Phone'] != '')) |
        (contacts_df['Email'].notna() & (contacts_df['Email'] != ''))
    )
    call_df = contacts_df[has_phone_or_email]

    if len(call_df) > 0:
        call_path = output_dir / f"jonathan_call_list_{today}.csv"

        call_out = []
        for _, row in call_df.iterrows():
            call_out.append({
                'Restaurant': row['Restaurant'],
                'Contact_Name': row['Contact_Name'],
                'Title': row.get('Title', ''),
                'Phone': row.get('Phone', ''),
                'Email': row.get('Email', ''),
                'Violations': row['Violations'],
                'Priority': row['Priority'],
                'Hook': row['Outreach_Hook'],
                'Address': row['Address'],
                'City': row['City'],
            })

        pd.DataFrame(call_out).to_csv(call_path, index=False)
        print(f"Created: {call_path} ({len(call_out)} contacts)")

    # 3. Email Campaign (contacts with email)
    has_email = contacts_df['Email'].notna() & (contacts_df['Email'] != '')
    email_df = contacts_df[has_email]

    if len(email_df) > 0:
        email_path = output_dir / f"email_campaign_{today}.csv"

        email_out = []
        for _, row in email_df.iterrows():
            first, last = split_name(row['Contact_Name'])
            email_out.append({
                'Email': row['Email'],
                'First_Name': first,
                'Last_Name': last,
                'Company': row['Restaurant'],
                'Title': row.get('Title', ''),
                'Violations': row['Violations'],
                'Priority': row['Priority'],
                'Hook': row['Outreach_Hook'],
                'Inspection_Date': row['Inspection_Date'],
                'City': row['City'],
                'Address': row['Address'],
            })

        pd.DataFrame(email_out).to_csv(email_path, index=False)
        print(f"Created: {email_path} ({len(email_out)} contacts)")

    # Summary
    print(f"\n{'='*50}")
    print("SUMMARY")
    print(f"{'='*50}")
    print(f"Total contacts enriched:  {len(contacts_df)}")
    print(f"  With LinkedIn URL:      {len(linkedin_df)}")
    print(f"  With phone or email:    {len(call_df)}")
    print(f"  With email:             {len(email_df)}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
