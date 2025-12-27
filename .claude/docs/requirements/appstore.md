# Brief:
This brief is for a redesign of the Apple App Store import function.

# UI scope:
- Page: Settings
- Tab: Pre-AI
- Component: Vendor Data table
- row: Apple App Store
- Button: Import

# Problem #1:
Apple App Store only provides information about its user's purchase history on this web page: https://reportaproblem.apple.com/.  This is behind apple's user log-in.

# Problem #2:
The App Store purchase history is only available in the web page.  To convert this to usable data the page must be parsed.  It is a complicated page to parse.  Prior work has alreayd generated a Apple App Store Purchases parser (/mcp/apple_parser.py)

# Feature Description:
1. When the user needs to import apple transactions, the app should spawn a browser using Microsoft Playwright (or similar) for https://reportaproblem.apple.com/.
2. The user will then enter their log-in credentials.
3. When the transactions are displayed, then the app will capture the page HTML and parse to extract purchase data.
4. The up to date purchase data will be appended to existing Apple App Store data
5. The user can then use existing funcitonality to enrich Apple App Store transactions  with details of their recent purchases.
