"""Allow running as: python -m screenshot_tool"""

import sys

from screenshot_tool.cli import main

if __name__ == "__main__":
    sys.exit(main())
