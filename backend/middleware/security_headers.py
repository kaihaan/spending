"""
Security headers middleware

Implements financial-grade security headers including CSP, HSTS, and other protections.
Fix #3: CSP without unsafe-eval (uses script hashes instead)
Fix #8: HSTS without preload initially (add after 30 days)
"""

from flask import request


def set_security_headers(response):
    """Apply security headers to all responses.

    Implements:
    - Content Security Policy (CSP) without unsafe-eval
    - HTTP Strict Transport Security (HSTS)
    - X-Frame-Options (clickjacking protection)
    - X-Content-Type-Options (MIME sniffing protection)
    - X-XSS-Protection (XSS filter)
    - Referrer-Policy (privacy)
    - Permissions-Policy (feature restrictions)

    Args:
        response: Flask response object

    Returns:
        Modified response with security headers
    """

    # ============================================================================
    # CONTENT SECURITY POLICY (Fix #3 - NO unsafe-eval)
    # ============================================================================
    #
    # IMPORTANT: Vite inline scripts need to be hashed.
    # Generate hash using: echo -n "<script>content</script>" | openssl dgst -sha256 -binary | base64
    #
    # For development, you may need to update hashes when Vite changes.
    # Production builds should have stable hashes.

    csp_directives = [
        # Default: Only allow resources from same origin
        "default-src 'self'",
        # Scripts: self + specific hashes (NO unsafe-eval)
        # TODO: Update VITE_HASH after building frontend
        "script-src 'self'",  # Add 'sha256-<VITE_HASH>' when available
        # Styles: self + inline styles (Tailwind requires this)
        "style-src 'self' 'unsafe-inline'",
        # Images: self + data URIs + HTTPS
        "img-src 'self' data: https:",
        # Fonts: self + data URIs
        "font-src 'self' data:",
        # Connect: API endpoints and external services
        "connect-src 'self' "
        "https://api.truelayer.com "
        "https://auth.truelayer.com "
        "https://eu.business-api.amazon.com "
        "https://www.amazon.co.uk "
        "https://gmail.googleapis.com "
        "https://www.googleapis.com",
        # Prevent framing (clickjacking)
        "frame-ancestors 'none'",
        # Base URI restriction
        "base-uri 'self'",
        # Form submission restriction
        "form-action 'self'",
        # Upgrade insecure requests (HTTP -> HTTPS)
        "upgrade-insecure-requests",
    ]

    response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

    # ============================================================================
    # HTTP STRICT TRANSPORT SECURITY (Fix #8 - NO preload initially)
    # ============================================================================
    #
    # IMPORTANT: Only add 'preload' after 30 days of monitoring.
    # Preload list submission is permanent and can break sites if misconfigured.
    #
    # After 30 days:
    # response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'

    if request.is_secure:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; "  # 1 year
            "includeSubDomains"  # Apply to all subdomains
            # NO preload yet - add after 30 days
        )

    # ============================================================================
    # CLICKJACKING PROTECTION
    # ============================================================================

    response.headers["X-Frame-Options"] = "DENY"

    # ============================================================================
    # MIME SNIFFING PROTECTION
    # ============================================================================

    response.headers["X-Content-Type-Options"] = "nosniff"

    # ============================================================================
    # XSS FILTER (Legacy browsers)
    # ============================================================================

    response.headers["X-XSS-Protection"] = "1; mode=block"

    # ============================================================================
    # REFERRER POLICY
    # ============================================================================

    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # ============================================================================
    # PERMISSIONS POLICY
    # ============================================================================
    # Disable unnecessary browser features

    permissions_policy = [
        "geolocation=()",  # No location access
        "microphone=()",  # No microphone access
        "camera=()",  # No camera access
        "payment=()",  # No payment API
        "usb=()",  # No USB access
        "magnetometer=()",  # No magnetometer
        "gyroscope=()",  # No gyroscope
        "accelerometer=()",  # No accelerometer
    ]

    response.headers["Permissions-Policy"] = ", ".join(permissions_policy)

    # ============================================================================
    # ADDITIONAL SECURITY HEADERS
    # ============================================================================

    # Prevent DNS prefetching
    response.headers["X-DNS-Prefetch-Control"] = "off"

    # Disable download prompts for cross-origin resources
    response.headers["X-Download-Options"] = "noopen"

    # Prevent content type sniffing in old IE
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

    return response


def init_app(app):
    """Register security headers middleware with Flask app.

    Args:
        app: Flask application instance
    """

    @app.after_request
    def apply_security_headers(response):
        """Apply security headers to all responses."""
        return set_security_headers(response)


# ============================================================================
# VITE SCRIPT HASH GENERATION (Development Helper)
# ============================================================================
#
# Use this function to generate CSP hashes for Vite inline scripts:
#
# from hashlib import sha256
# import base64
#
# def generate_script_hash(script_content: str) -> str:
#     """Generate SHA-256 hash for CSP script-src."""
#     hash_bytes = sha256(script_content.encode('utf-8')).digest()
#     hash_b64 = base64.b64encode(hash_bytes).decode('utf-8')
#     return f"'sha256-{hash_b64}'"
#
# # Example:
# # vite_script = "<script>window.__VITE__=true</script>"
# # print(generate_script_hash(vite_script))
# # Output: 'sha256-abc123...'
#
# Then add to CSP:
# "script-src 'self' 'sha256-abc123...'"
