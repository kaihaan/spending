#!/usr/bin/env python3
"""Analyze which vendors should extract brand metadata"""

# Vendor categories and what brand metadata they should extract
VENDOR_BRAND_METADATA = {
    # Food delivery - should have restaurant/location
    "deliveroo": {"field": "restaurant", "status": "implemented", "source": "email"},
    "uber_eats": {"field": "restaurant", "status": "implemented", "source": "email"},
    "black_sheep_coffee": {
        "field": "location",
        "status": "implemented",
        "source": "email subject",
    },
    # Payment processors - should have merchant
    "paypal": {"field": "merchant", "status": "implemented", "source": "email"},
    "worldpay": {
        "field": "merchant",
        "status": "not_implemented",
        "source": "email",
        "priority": "medium",
    },
    # Travel - should have route/destination/property
    "british_airways": {
        "field": "route",
        "status": "not_implemented",
        "source": "email",
        "priority": "high",
    },
    "airbnb": {
        "field": "property_name",
        "status": "not_implemented",
        "source": "email",
        "priority": "high",
    },
    "dhl": {
        "field": "destination",
        "status": "not_implemented",
        "source": "email",
        "priority": "low",
    },
    # Ride sharing - should have route/location
    "uber": {
        "field": "route",
        "status": "not_implemented",
        "source": "email",
        "priority": "medium",
    },
    "lyft": {
        "field": "route",
        "status": "not_implemented",
        "source": "email",
        "priority": "low",
    },
    "lime": {
        "field": "location",
        "status": "not_implemented",
        "source": "email",
        "priority": "low",
    },
    # Fitness/wellness - should have studio/venue
    "mindbody": {
        "field": "studio_name",
        "status": "not_implemented",
        "source": "email",
        "priority": "medium",
    },
    "triyoga": {
        "field": "studio_name",
        "status": "not_implemented",
        "source": "email",
        "priority": "medium",
    },
    # Marketplaces - brand/seller requires API
    "amazon": {
        "field": "brand/manufacturer",
        "status": "impossible",
        "source": "requires Product API",
        "priority": "n/a",
    },
    "ebay": {
        "field": "seller_name",
        "status": "not_implemented",
        "source": "email",
        "priority": "medium",
    },
    "etsy": {
        "field": "seller_name",
        "status": "not_implemented",
        "source": "email",
        "priority": "medium",
    },
    "vinted": {
        "field": "seller_name",
        "status": "not_implemented",
        "source": "email",
        "priority": "low",
    },
    "reverb": {
        "field": "seller_name",
        "status": "not_implemented",
        "source": "email",
        "priority": "low",
    },
    # Digital products - developer not in emails
    "apple": {
        "field": "developer",
        "status": "impossible",
        "source": "not in email, use CSV import",
        "priority": "n/a",
    },
    "google": {
        "field": "developer/product",
        "status": "partial",
        "source": "product name extracted",
        "priority": "n/a",
    },
    "microsoft": {
        "field": "product_name",
        "status": "partial",
        "source": "product name may be extractable",
        "priority": "low",
    },
    # Others
    "anthropic": {
        "field": "service",
        "status": "n/a",
        "source": "single service (Claude API)",
        "priority": "n/a",
    },
}


def print_analysis():
    print("=" * 100)
    print("VENDOR BRAND METADATA ANALYSIS")
    print("=" * 100)
    print()

    # Group by status
    for status in ["implemented", "not_implemented", "partial", "impossible", "n/a"]:
        vendors = {
            k: v for k, v in VENDOR_BRAND_METADATA.items() if v["status"] == status
        }
        if vendors:
            print(f"\n{status.upper().replace('_', ' ')}:")
            print("-" * 100)
            for vendor, info in sorted(vendors.items()):
                priority = info.get("priority", "n/a")
                print(
                    f"  {vendor:20} | Field: {info['field']:25} | Source: {info['source']:30} | Priority: {priority}"
                )

    print("\n" + "=" * 100)
    print("\nHIGH PRIORITY RECOMMENDATIONS:")
    print("-" * 100)
    high_priority = {
        k: v
        for k, v in VENDOR_BRAND_METADATA.items()
        if v.get("priority") == "high" and v["status"] == "not_implemented"
    }
    for vendor, info in sorted(high_priority.items()):
        print(f"  • {vendor}: Extract '{info['field']}' from {info['source']}")

    print("\n" + "=" * 100)
    print("\nMEDIUM PRIORITY RECOMMENDATIONS:")
    print("-" * 100)
    medium_priority = {
        k: v
        for k, v in VENDOR_BRAND_METADATA.items()
        if v.get("priority") == "medium" and v["status"] == "not_implemented"
    }
    for vendor, info in sorted(medium_priority.items()):
        print(f"  • {vendor}: Extract '{info['field']}' from {info['source']}")


if __name__ == "__main__":
    print_analysis()
