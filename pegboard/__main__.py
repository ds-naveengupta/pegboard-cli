"""Pegboard CLI entry point script."""
# pegboard/__main__.py

from pegboard import cli, __app_name__

def main():
    cli.app(prog_name=__app_name__)

if __name__ == "__main__":
    main()