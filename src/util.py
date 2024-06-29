import sys


def create_logger(sender: str):
    def log(message: str):
        print(f'({sender}) {message}', file=sys.stderr)
    return log