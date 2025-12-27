"""
Gmail API Client Module

Handles Gmail API interactions for fetching receipt emails.
Includes rate limiting, pagination, and error handling.
"""

import base64
import os
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials

# Load environment variables (Docker env vars take precedence)
load_dotenv(override=False)

# Rate limiting configuration
RATE_LIMIT_DELAY = 0.1  # 100ms between requests (10 req/sec)
MAX_RETRIES = 3
BACKOFF_MULTIPLIER = 2

# Google OAuth configuration (needed for automatic token refresh)
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Gmail API base URL
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"


def build_gmail_service(access_token: str, refresh_token: str = None):
    """
    Build Gmail API session with credentials.

    Uses requests-based AuthorizedSession to completely avoid httplib2
    and its TLS compatibility issues. Returns session object for direct API calls.

    Args:
        access_token: Valid OAuth access token
        refresh_token: Optional refresh token for automatic refresh

    Returns:
        AuthorizedSession object for making Gmail API requests
    """
    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=GOOGLE_TOKEN_URL,
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    )

    # Create requests-based session (completely avoids httplib2)
    # This eliminates all SSL/TLS errors from httplib2 + OpenSSL incompatibility
    session = AuthorizedSession(credentials)
    session.timeout = 60  # Set default timeout for all requests

    return session


def fetch_with_backoff(
    session, method: str, url: str, max_retries: int = MAX_RETRIES, **kwargs
):
    """
    Execute Gmail API request with exponential backoff using requests.

    Args:
        session: AuthorizedSession object
        method: HTTP method ('GET', 'POST', etc.)
        url: Full API URL
        max_retries: Maximum number of retries
        **kwargs: Additional arguments to pass to session.request()

    Returns:
        Response JSON dict

    Raises:
        requests.HTTPError: If request fails after all retries
    """
    delay = 1
    last_error = None

    for attempt in range(max_retries):
        try:
            # Rate limiting
            time.sleep(RATE_LIMIT_DELAY)

            response = session.request(method, url, timeout=60, **kwargs)
            response.raise_for_status()

            return response.json()

        except requests.HTTPError as e:
            last_error = e
            # Check if retryable (429 rate limit, 500 server error)
            if e.response.status_code in [429, 500, 503]:
                print(
                    f"   ⚠️  Gmail API rate limited (attempt {attempt + 1}/{max_retries}), retrying in {delay}s..."
                )
                time.sleep(delay)
                delay *= BACKOFF_MULTIPLIER
            else:
                # Non-retryable error
                raise
        except requests.RequestException as e:
            last_error = e
            print(
                f"   ⚠️  Gmail API request failed (attempt {attempt + 1}/{max_retries}), retrying in {delay}s..."
            )
            time.sleep(delay)
            delay *= BACKOFF_MULTIPLIER

    raise last_error


def build_receipt_query(from_date: datetime = None, to_date: datetime = None) -> str:
    """
    Build Gmail search query for receipt emails.

    Based on requirements document, searches for:
    - Common receipt keywords in subject
    - From known receipt senders
    - Within date range

    Args:
        from_date: Start date for search
        to_date: End date for search

    Returns:
        Gmail search query string
    """
    # Keywords that typically appear in receipt emails
    receipt_keywords = [
        "receipt",
        "order confirmation",
        "your order",
        "payment confirmation",
        "purchase confirmation",
        "invoice",
        "booking confirmation",
        "e-receipt",
        "digital receipt",
        "transaction",
        "your purchase",
        "thank you for your purchase",
    ]

    # Build subject query
    subject_query = " OR ".join([f'subject:"{kw}"' for kw in receipt_keywords])

    # Known receipt senders (common domains)
    receipt_senders = [
        "amazon.co.uk",
        "amazon.com",
        "apple.com",
        "paypal.com",
        "paypal.co.uk",
        "uber.com",
        "deliveroo.com",
        "just-eat.co.uk",
        "trainline.com",
        "booking.com",
        "netflix.com",
        "spotify.com",
        "microsoft.com",
        "tesco.com",
        "sainsburys.co.uk",
        "ocado.com",
        "ebay.co.uk",
        "ebay.com",
        "woolrich.com",
        "fastspring.com",
    ]

    # Build from query
    from_query = " OR ".join([f"from:{sender}" for sender in receipt_senders])

    # Combine with OR (either subject match OR from known sender)
    base_query = f"({subject_query}) OR ({from_query})"

    # Add date filters
    if from_date:
        date_str = from_date.strftime("%Y/%m/%d")
        base_query = f"{base_query} after:{date_str}"

    if to_date:
        date_str = to_date.strftime("%Y/%m/%d")
        base_query = f"{base_query} before:{date_str}"

    return base_query


def list_receipt_messages(
    session, query: str = None, page_token: str = None, max_results: int = 100
) -> dict:
    """
    List messages matching receipt query using requests.

    Args:
        session: AuthorizedSession object
        query: Search query (defaults to receipt query)
        page_token: Pagination token
        max_results: Maximum messages per page (max 500)

    Returns:
        Dictionary with 'messages' list and 'nextPageToken'
    """
    if query is None:
        query = build_receipt_query()

    try:
        url = f"{GMAIL_API_BASE}/users/me/messages"
        params = {"q": query, "maxResults": min(max_results, 500)}
        if page_token:
            params["pageToken"] = page_token

        result = fetch_with_backoff(session, "GET", url, params=params)

        return {
            "messages": result.get("messages", []),
            "nextPageToken": result.get("nextPageToken"),
            "resultSizeEstimate": result.get("resultSizeEstimate", 0),
        }

    except requests.HTTPError as e:
        print(f"❌ Gmail list messages error: {e}")
        raise


def get_message_content(session, message_id: str) -> dict:
    """
    Fetch full email content including body using requests.

    Args:
        session: AuthorizedSession object
        message_id: Gmail message ID

    Returns:
        Dictionary with email metadata and decoded body
    """
    try:
        url = f"{GMAIL_API_BASE}/users/me/messages/{message_id}"
        params = {"format": "full"}

        message = fetch_with_backoff(session, "GET", url, params=params)

        # Parse headers
        headers = {
            h["name"].lower(): h["value"]
            for h in message.get("payload", {}).get("headers", [])
        }

        # Extract body content
        body_html = None
        body_text = None

        payload = message.get("payload", {})

        # Check for direct body
        if payload.get("body", {}).get("data"):
            body = payload["body"]
            decoded = base64.urlsafe_b64decode(body["data"]).decode(
                "utf-8", errors="ignore"
            )
            if payload.get("mimeType") == "text/html":
                body_html = decoded
            else:
                body_text = decoded

        # Check for multipart body
        parts = payload.get("parts", [])
        for part in parts:
            mime_type = part.get("mimeType", "")
            part_data = part.get("body", {}).get("data")

            if part_data:
                decoded = base64.urlsafe_b64decode(part_data).decode(
                    "utf-8", errors="ignore"
                )
                if mime_type == "text/html":
                    body_html = decoded
                elif mime_type == "text/plain":
                    body_text = decoded

            # Handle nested multipart
            nested_parts = part.get("parts", [])
            for nested in nested_parts:
                nested_mime = nested.get("mimeType", "")
                nested_data = nested.get("body", {}).get("data")
                if nested_data:
                    decoded = base64.urlsafe_b64decode(nested_data).decode(
                        "utf-8", errors="ignore"
                    )
                    if nested_mime == "text/html":
                        body_html = decoded
                    elif nested_mime == "text/plain":
                        body_text = decoded

        # Parse internal date (Unix timestamp in ms)
        internal_date = message.get("internalDate")
        received_at = None
        if internal_date:
            received_at = datetime.utcfromtimestamp(int(internal_date) / 1000)

        # Extract attachment metadata
        attachments = []

        def extract_attachments(parts_list):
            """Recursively extract attachment info from parts."""
            for part in parts_list:
                filename = part.get("filename", "")
                mime_type = part.get("mimeType", "")
                body = part.get("body", {})
                attachment_id = body.get("attachmentId")

                # If it has a filename and attachment ID, it's an attachment
                if filename and attachment_id:
                    attachments.append(
                        {
                            "filename": filename,
                            "mime_type": mime_type,
                            "attachment_id": attachment_id,
                            "size": body.get("size", 0),
                        }
                    )

                # Check nested parts
                if part.get("parts"):
                    extract_attachments(part["parts"])

        if parts:
            extract_attachments(parts)

        return {
            "message_id": message_id,
            "thread_id": message.get("threadId"),
            "subject": headers.get("subject", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "date": headers.get("date", ""),
            "received_at": received_at,
            "body_html": body_html,
            "body_text": body_text,
            "snippet": message.get("snippet", ""),
            "label_ids": message.get("labelIds", []),
            "size_estimate": message.get("sizeEstimate", 0),
            # Marketing detection headers
            "list_unsubscribe": headers.get("list-unsubscribe", ""),
            "x_mailer": headers.get("x-mailer", ""),
            # Attachments metadata
            "attachments": attachments,
        }

    except requests.HTTPError as e:
        print(f"❌ Gmail get message error: {e}")
        raise


def get_attachment_content(session, message_id: str, attachment_id: str) -> bytes:
    """
    Fetch attachment content from a Gmail message using requests.

    Args:
        session: AuthorizedSession object
        message_id: Gmail message ID
        attachment_id: Attachment ID from message parts

    Returns:
        Raw attachment bytes (decoded from base64)
    """
    try:
        url = f"{GMAIL_API_BASE}/users/me/messages/{message_id}/attachments/{attachment_id}"

        attachment = fetch_with_backoff(session, "GET", url)

        # Attachment data is base64url encoded
        data = attachment.get("data", "")
        if data:
            return base64.urlsafe_b64decode(data)

        return b""

    except requests.HTTPError as e:
        print(f"❌ Gmail get attachment error: {e}")
        raise


def get_pdf_attachments(session, message_id: str, attachments: list) -> list:
    """
    Fetch all PDF attachments from a message using requests.

    Args:
        session: AuthorizedSession object
        message_id: Gmail message ID
        attachments: List of attachment metadata from get_message_content()

    Returns:
        List of dicts with filename and content (bytes)
    """
    pdf_attachments = []

    for attachment in attachments:
        mime_type = attachment.get("mime_type", "").lower()
        filename = attachment.get("filename", "").lower()

        # Check if it's a PDF
        if mime_type == "application/pdf" or filename.endswith(".pdf"):
            attachment_id = attachment.get("attachment_id")
            if attachment_id:
                content = get_attachment_content(session, message_id, attachment_id)
                if content:
                    pdf_attachments.append(
                        {
                            "filename": attachment.get("filename"),
                            "content": content,
                            "size": len(content),
                        }
                    )

    return pdf_attachments


def get_message_batch(session, message_ids: list) -> list:
    """
    Fetch multiple messages using requests.

    Args:
        session: AuthorizedSession object
        message_ids: List of message IDs to fetch

    Returns:
        List of message content dictionaries
    """
    messages = []

    # Process in batches of 100 to avoid quota issues
    batch_size = 100

    for i in range(0, len(message_ids), batch_size):
        batch = message_ids[i : i + batch_size]

        for msg_id in batch:
            try:
                msg = get_message_content(session, msg_id)
                messages.append(msg)
            except requests.HTTPError as e:
                print(f"   ⚠️  Failed to fetch message {msg_id}: {e}")
                continue

    return messages


def get_history_changes(session, start_history_id: str) -> dict:
    """
    Get incremental changes since last sync using history API with requests.

    Args:
        session: AuthorizedSession object
        start_history_id: History ID from last sync

    Returns:
        Dictionary with new/modified message IDs and latest history ID
    """
    try:
        new_messages = []
        latest_history_id = start_history_id
        page_token = None

        while True:
            url = f"{GMAIL_API_BASE}/users/me/history"
            params = {
                "startHistoryId": start_history_id,
                "historyTypes": "messageAdded",
            }
            if page_token:
                params["pageToken"] = page_token

            result = fetch_with_backoff(session, "GET", url, params=params)

            # Process history records
            history_records = result.get("history", [])
            for record in history_records:
                messages_added = record.get("messagesAdded", [])
                for msg in messages_added:
                    new_messages.append(msg["message"]["id"])

            # Update latest history ID
            if result.get("historyId"):
                latest_history_id = result["historyId"]

            # Check for more pages
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return {"new_message_ids": new_messages, "latest_history_id": latest_history_id}

    except requests.HTTPError as e:
        # History ID might be too old (404)
        if e.response.status_code == 404:
            print("   ⚠️  History ID expired, full sync required")
            return {
                "new_message_ids": [],
                "latest_history_id": None,
                "full_sync_required": True,
            }
        raise


def get_user_profile(session) -> dict:
    """
    Get Gmail user profile including email and history ID using requests.

    Args:
        session: AuthorizedSession object

    Returns:
        User profile dictionary with email and historyId
    """
    try:
        url = f"{GMAIL_API_BASE}/users/me/profile"
        profile = fetch_with_backoff(session, "GET", url)

        return {
            "email_address": profile.get("emailAddress"),
            "messages_total": profile.get("messagesTotal", 0),
            "threads_total": profile.get("threadsTotal", 0),
            "history_id": profile.get("historyId"),
        }

    except requests.HTTPError as e:
        print(f"❌ Gmail profile error: {e}")
        raise


def parse_sender_email(from_header: str) -> tuple:
    """
    Parse email address and display name from From header.

    Args:
        from_header: Raw From header string

    Returns:
        Tuple of (email, display_name)
    """
    import re

    # Pattern: "Display Name" <email@example.com> or just email@example.com
    match = re.match(r'^(?:"?([^"<]*)"?\s*)?<?([^>]+@[^>]+)>?$', from_header.strip())

    if match:
        display_name = match.group(1).strip() if match.group(1) else ""
        email = match.group(2).strip()
        return email, display_name

    # Fallback - treat entire string as email
    return from_header.strip(), ""


def extract_sender_domain(email: str) -> str:
    """
    Extract domain from email address.

    Args:
        email: Email address string

    Returns:
        Domain string
    """
    if "@" in email:
        return email.split("@")[1].lower()
    return ""
