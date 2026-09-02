"""`convo api [--host H] [--port N] [--reload]`: run the control plane and the console UI."""

import argparse


def main(argv: list[str]) -> int:
    """Serve `convo.api.app:app` with uvicorn on the given address."""
    parser = argparse.ArgumentParser(prog="convo api", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--reload", action="store_true", help="restart on code changes")
    args = parser.parse_args(argv)
    import uvicorn

    uvicorn.run("convo.api.app:app", host=args.host, port=args.port, reload=args.reload)
    return 0
