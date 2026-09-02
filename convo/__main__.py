"""`python -m convo <group> <verb> [args]`: the command line, one module per group."""

import sys

from convo.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
