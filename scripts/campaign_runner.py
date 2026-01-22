#!/usr/bin/env python3
"""
Campaign Runner CLI for Himalayan Fibers Email Marketing.

Usage:
    # Test SMTP connection
    python scripts/campaign_runner.py test-connection

    # Send test email
    python scripts/campaign_runner.py test-email your@email.com

    # List available campaigns
    python scripts/campaign_runner.py list-campaigns

    # Preview campaign (dry run)
    python scripts/campaign_runner.py preview b2b_introduction --limit 5

    # Send campaign
    python scripts/campaign_runner.py send b2b_introduction --limit 10

    # Send to specific segment
    python scripts/campaign_runner.py send tariff_advantage --segment potential_b2b --limit 50
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.email_sender import EmailSender, CAMPAIGNS, list_campaigns
from app.data_manager import DataManager


def test_connection():
    """Test SMTP connection."""
    print("\n" + "="*60)
    print("TESTING SMTP CONNECTION")
    print("="*60)

    sender = EmailSender()
    print(f"\nSMTP Host: {sender.smtp_host}")
    print(f"SMTP Port: {sender.smtp_port}")
    print(f"SMTP User: {sender.smtp_user}")
    print(f"From Name: {sender.from_name}")

    result = sender.test_connection()

    if result["success"]:
        print(f"\n✅ {result['message']}")
    else:
        print(f"\n❌ {result['message']}")

    return result["success"]


def send_test_email(to_email: str):
    """Send a test email."""
    print("\n" + "="*60)
    print(f"SENDING TEST EMAIL TO: {to_email}")
    print("="*60)

    sender = EmailSender()
    result = sender.send_test_email(to_email)

    if result["success"]:
        print(f"\n✅ {result['message']}")
    else:
        print(f"\n❌ {result['message']}")

    return result["success"]


def show_campaigns():
    """List available campaigns."""
    print("\n" + "="*60)
    print("AVAILABLE CAMPAIGNS")
    print("="*60)

    campaigns = list_campaigns()

    for camp in campaigns:
        print(f"\n📧 {camp['id']}")
        print(f"   Name: {camp['name']}")
        print(f"   Description: {camp['description']}")
        print(f"   Template: {camp['template']}")
        print(f"   Subject: {camp['subject']}")
        print(f"   Target Segment: {camp['segment']}")


def preview_campaign(campaign_id: str, limit: int = 5, segment: str = None):
    """Preview campaign without sending (dry run)."""
    print("\n" + "="*60)
    print(f"PREVIEW CAMPAIGN: {campaign_id}")
    print("="*60)

    campaign = CAMPAIGNS.get(campaign_id)
    if not campaign:
        print(f"\n❌ Campaign '{campaign_id}' not found.")
        print("Available campaigns:", list(CAMPAIGNS.keys()))
        return False

    print(f"\nCampaign: {campaign['name']}")
    print(f"Subject: {campaign['subject']}")
    print(f"Template: {campaign['template']}")

    # Get contacts
    dm = DataManager()
    segment_filter = segment or campaign.get("segment")

    if segment_filter:
        contacts = dm.search_contacts(customer_type=segment_filter)
    else:
        contacts = dm.get_all_contacts()

    # Filter out placeholder emails
    contacts = [c for c in contacts if 'placeholder.local' not in c.email]

    print(f"\nTotal contacts in segment: {len(contacts)}")
    print(f"Previewing first {min(limit, len(contacts))} contacts:\n")

    for i, contact in enumerate(contacts[:limit]):
        print(f"  {i+1}. {contact.email}")
        print(f"     Company: {contact.company}")
        print(f"     Name: {contact.first_name} {contact.last_name}")
        print()

    return True


def run_campaign(
    campaign_id: str,
    limit: int = None,
    segment: str = None,
    dry_run: bool = False,
    batch_size: int = 50,
    delay: int = 60
):
    """Run a campaign."""
    print("\n" + "="*60)
    print(f"{'DRY RUN - ' if dry_run else ''}RUNNING CAMPAIGN: {campaign_id}")
    print("="*60)

    campaign = CAMPAIGNS.get(campaign_id)
    if not campaign:
        print(f"\n❌ Campaign '{campaign_id}' not found.")
        print("Available campaigns:", list(CAMPAIGNS.keys()))
        return False

    print(f"\nCampaign: {campaign['name']}")
    print(f"Subject: {campaign['subject']}")
    print(f"Template: {campaign['template']}")

    # Get contacts
    dm = DataManager()
    segment_filter = segment or campaign.get("segment")

    if segment_filter:
        contacts = dm.search_contacts(customer_type=segment_filter)
    else:
        contacts = dm.get_all_contacts()

    # Filter out placeholder emails
    contacts = [c for c in contacts if 'placeholder.local' not in c.email]

    if limit:
        contacts = contacts[:limit]

    print(f"\nContacts to send: {len(contacts)}")
    print(f"Batch size: {batch_size}")
    print(f"Delay between batches: {delay}s")

    if not dry_run:
        confirm = input(f"\n⚠️  About to send {len(contacts)} emails. Continue? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Cancelled.")
            return False

    # Send campaign
    sender = EmailSender()

    print(f"\nStarted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 40)

    result = sender.send_batch_campaign(
        contacts=contacts,
        template_path=campaign['template'],
        subject=campaign['subject'],
        batch_size=batch_size,
        delay_between_batches=delay,
        dry_run=dry_run
    )

    print("-" * 40)
    print(f"\n📊 CAMPAIGN RESULTS:")
    print(f"   Total: {result['total']}")
    print(f"   Sent: {result['sent']}")
    print(f"   Failed: {result['failed']}")
    print(f"   Skipped: {result['skipped']}")

    if result['errors']:
        print(f"\n❌ Errors ({len(result['errors'])}):")
        for err in result['errors'][:10]:
            print(f"   - {err['email']}: {err['error']}")

    print(f"\nCompleted at: {result.get('completed_at', 'N/A')}")

    return result['failed'] == 0


def show_stats():
    """Show contact and campaign statistics."""
    print("\n" + "="*60)
    print("CONTACT & CAMPAIGN STATISTICS")
    print("="*60)

    dm = DataManager()
    stats = dm.get_contact_stats()

    print(f"\n📊 CONTACTS: {stats['total']}")
    print("\nBy Customer Type:")
    for ct, count in stats['by_customer_type'].items():
        print(f"  - {ct}: {count}")

    print("\nBy Geography:")
    for geo, count in stats['by_geography'].items():
        print(f"  - {geo}: {count}")

    # Segment counts
    print("\n📁 SEGMENT COUNTS:")
    for segment in dm.get_all_segments():
        count = dm.get_segment_count(segment.id)
        if count > 0:
            print(f"  - {segment.name}: {count}")

    # Campaigns
    print("\n📧 AVAILABLE CAMPAIGNS:")
    for camp_id, camp in CAMPAIGNS.items():
        print(f"  - {camp_id}: {camp['name']}")


def main():
    parser = argparse.ArgumentParser(
        description="Himalayan Fibers Email Campaign Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s test-connection
  %(prog)s test-email prashant@example.com
  %(prog)s list-campaigns
  %(prog)s stats
  %(prog)s preview b2b_introduction --limit 10
  %(prog)s send b2b_introduction --limit 5 --dry-run
  %(prog)s send tariff_advantage --limit 50
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # test-connection
    subparsers.add_parser('test-connection', help='Test SMTP connection')

    # test-email
    test_email_parser = subparsers.add_parser('test-email', help='Send test email')
    test_email_parser.add_argument('email', help='Email address to send test to')

    # list-campaigns
    subparsers.add_parser('list-campaigns', help='List available campaigns')

    # stats
    subparsers.add_parser('stats', help='Show contact and campaign statistics')

    # preview
    preview_parser = subparsers.add_parser('preview', help='Preview campaign (dry run)')
    preview_parser.add_argument('campaign', help='Campaign ID')
    preview_parser.add_argument('--limit', type=int, default=5, help='Number of contacts to show')
    preview_parser.add_argument('--segment', help='Filter by segment')

    # send
    send_parser = subparsers.add_parser('send', help='Send campaign')
    send_parser.add_argument('campaign', help='Campaign ID')
    send_parser.add_argument('--limit', type=int, help='Limit number of emails')
    send_parser.add_argument('--segment', help='Filter by segment')
    send_parser.add_argument('--dry-run', action='store_true', help='Simulate without sending')
    send_parser.add_argument('--batch-size', type=int, default=50, help='Emails per batch')
    send_parser.add_argument('--delay', type=int, default=60, help='Seconds between batches')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == 'test-connection':
        test_connection()
    elif args.command == 'test-email':
        send_test_email(args.email)
    elif args.command == 'list-campaigns':
        show_campaigns()
    elif args.command == 'stats':
        show_stats()
    elif args.command == 'preview':
        preview_campaign(args.campaign, args.limit, args.segment)
    elif args.command == 'send':
        run_campaign(
            args.campaign,
            limit=args.limit,
            segment=args.segment,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            delay=args.delay
        )


if __name__ == "__main__":
    main()
