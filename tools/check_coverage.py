#!/usr/bin/env python3
"""Enforce separate statement and branch gates in addition to pytest-cov's total."""
import argparse
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    args=parser.parse_args()
    totals=json.loads(args.report.read_text())['totals']
    failed=False
    for label,covered,total in [('Statements',totals['covered_lines'],totals['num_statements']),
                                ('Branches',totals['covered_branches'],totals['num_branches'])]:
        percent=100*covered/total if total else 0
        print(f'{label}: {percent:.2f}% ({covered}/{total}); required 95%')
        failed=failed or percent<95
    return int(failed)


if __name__=='__main__':raise SystemExit(main())
