#!/usr/bin/env python3
"""Analyze vendor emails to create parsers"""

import re

import psycopg2
from bs4 import BeautifulSoup
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "host": "localhost",
    "port": "5433",
    "user": "spending_user",
    "password": "aC0_Xbvulrw8ldPgU6sa",
    "database": "spending_db",
}


def connect_db():
    return psycopg2.connect(**DB_CONFIG)


def analyze_charles_tyrwhitt():
    """Analyze Charles Tyrwhitt emails to understand format"""
    conn = connect_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT gr.message_id, gr.subject, gec.body_html, gec.body_text
        FROM gmail_receipts gr
        JOIN gmail_email_content gec ON gr.message_id = gec.message_id
        WHERE gr.merchant_name = 'Charles Tyrwhitt'
        LIMIT 1
    """)

    email = cursor.fetchone()
    if not email:
        print("No Charles Tyrwhitt emails found")
        return

    print("=" * 80)
    print("CHARLES TYRWHITT EMAIL ANALYSIS")
    print("=" * 80)
    print(f"Subject: {email['subject']}\n")

    # Parse HTML
    if email["body_html"]:
        soup = BeautifulSoup(email["body_html"], "html.parser")
        text = soup.get_text()

        # Look for amounts
        amounts = re.findall(r"£\s*([0-9,]+\.[0-9]{2})", text)
        print(f"Found amounts: {amounts[:10]}\n")

        # Look for totals
        total_matches = re.findall(
            r"(?:Total|Grand Total|Order Total)[:\s]*£\s*([0-9,]+\.[0-9]{2})",
            text,
            re.IGNORECASE,
        )
        print(f"Total matches: {total_matches}\n")

        # Look for order IDs
        order_ids = re.findall(
            r"Order\s*(?:Number|ID|#)[:\s]*([A-Z0-9\-]+)", text, re.IGNORECASE
        )
        print(f"Order IDs: {order_ids}\n")

        # Look for items
        print("Sample text (first 1000 chars):")
        print(text[:1000])

    cursor.close()
    conn.close()


def analyze_world_of_books():
    """Analyze World of Books emails"""
    conn = connect_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT gr.message_id, gr.subject, gec.body_html, gec.body_text
        FROM gmail_receipts gr
        JOIN gmail_email_content gec ON gr.message_id = gec.message_id
        WHERE gr.merchant_name = 'World of Books'
        LIMIT 1
    """)

    email = cursor.fetchone()
    if not email:
        print("No World of Books emails found")
        return

    print("\n" + "=" * 80)
    print("WORLD OF BOOKS EMAIL ANALYSIS")
    print("=" * 80)
    print(f"Subject: {email['subject']}\n")

    if email["body_html"]:
        soup = BeautifulSoup(email["body_html"], "html.parser")
        text = soup.get_text()

        amounts = re.findall(r"£\s*([0-9,]+\.[0-9]{2})", text)
        print(f"Found amounts: {amounts[:10]}\n")

        total_matches = re.findall(
            r"(?:Total|Grand Total|Order Total)[:\s]*£\s*([0-9,]+\.[0-9]{2})",
            text,
            re.IGNORECASE,
        )
        print(f"Total matches: {total_matches}\n")

        order_ids = re.findall(
            r"Order\s*(?:Number|ID|#)[:\s]*([A-Z0-9\-]+)", text, re.IGNORECASE
        )
        print(f"Order IDs: {order_ids}\n")

        print("Sample text (first 1000 chars):")
        print(text[:1000])

    cursor.close()
    conn.close()


def analyze_uniqlo():
    """Analyze Uniqlo emails"""
    conn = connect_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    cursor.execute("""
        SELECT gr.message_id, gr.subject, gec.body_html, gec.body_text
        FROM gmail_receipts gr
        JOIN gmail_email_content gec ON gr.message_id = gec.message_id
        WHERE gr.merchant_name = 'Uniqlo'
        LIMIT 1
    """)

    email = cursor.fetchone()
    if not email:
        print("No Uniqlo emails found")
        return

    print("\n" + "=" * 80)
    print("UNIQLO EMAIL ANALYSIS")
    print("=" * 80)
    print(f"Subject: {email['subject']}\n")

    if email["body_html"]:
        soup = BeautifulSoup(email["body_html"], "html.parser")
        text = soup.get_text()

        amounts = re.findall(r"£\s*([0-9,]+\.[0-9]{2})", text)
        print(f"Found amounts: {amounts[:10]}\n")

        total_matches = re.findall(
            r"(?:Total|Grand Total|Order Total)[:\s]*£\s*([0-9,]+\.[0-9]{2})",
            text,
            re.IGNORECASE,
        )
        print(f"Total matches: {total_matches}\n")

        order_ids = re.findall(
            r"Order\s*(?:Number|ID|#)[:\s]*([A-Z0-9\-]+)", text, re.IGNORECASE
        )
        print(f"Order IDs: {order_ids}\n")

        print("Sample text (first 1000 chars):")
        print(text[:1000])

    cursor.close()
    conn.close()


if __name__ == "__main__":
    analyze_charles_tyrwhitt()
    analyze_world_of_books()
    analyze_uniqlo()
