#!/usr/bin/env python3
"""Local Hub interface; files are addressed inside one named agent's area."""
import argparse
import json
from hub_operations import execute

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['list','read','review','sandbox'])
    parser.add_argument('--agent', required=True, choices=['jessica','harvey','louis','mike','rachel','donna','benjamin'])
    parser.add_argument('--path', default='inbox')
    parser.add_argument('--limit', type=int, default=12000)
    parser.add_argument('--question'); parser.add_argument('--offset', type=int, default=0)
    args = vars(parser.parse_args())
    if args['action'] in ('list','read'):args.pop('question', None)
    print(json.dumps(execute(args), indent=2))

if __name__ == '__main__':
    try:main()
    except Exception as error:raise SystemExit('Hub operation failed: ' + type(error).__name__ + '. No successful operation is claimed.')
