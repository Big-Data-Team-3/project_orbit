#!/usr/bin/env python3
"""
HITL CLI Tool

Command-line interface for managing HITL approval requests.
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
import requests

API_BASE = "http://localhost:8000"
HITL_APPROVALS_DIR = Path(__file__).parent.parent / "data" / "hitl_approvals"


def list_approvals(status: Optional[str] = None, use_api: bool = True):
    """List approval requests."""
    if use_api:
        try:
            url = f"{API_BASE}/hitl/approvals"
            if status:
                url += f"?status={status}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                approvals = response.json()
                return approvals
        except:
            pass
    
    # Fallback to file system
    approvals = []
    if HITL_APPROVALS_DIR.exists():
        for approval_file in HITL_APPROVALS_DIR.glob("*.json"):
            try:
                with open(approval_file, 'r') as f:
                    data = json.load(f)
                    if status:
                        is_pending = data.get("approved") is None
                        if status == "pending" and not is_pending:
                            continue
                        elif status == "approved" and data.get("approved") != True:
                            continue
                        elif status == "rejected" and data.get("approved") != False:
                            continue
                    approvals.append(data)
            except:
                continue
    
    return sorted(approvals, key=lambda x: x.get("paused_at", ""), reverse=True)


def get_approval(approval_id: str, use_api: bool = True):
    """Get approval details."""
    if use_api:
        try:
            response = requests.get(f"{API_BASE}/hitl/approvals/{approval_id}", timeout=5)
            if response.status_code == 200:
                return response.json()
        except:
            pass
    
    # Fallback to file system
    approval_file = HITL_APPROVALS_DIR / f"{approval_id}.json"
    if approval_file.exists():
        with open(approval_file, 'r') as f:
            return json.load(f)
    return None


def approve(approval_id: str, reviewer: str = "cli", notes: str = "", use_api: bool = True):
    """Approve an approval request."""
    if use_api:
        try:
            response = requests.post(
                f"{API_BASE}/hitl/approvals/{approval_id}/approve",
                json={"reviewer": reviewer, "review_notes": notes},
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"API error: {e}", file=sys.stderr)
    
    # Fallback to file system
    approval_file = HITL_APPROVALS_DIR / f"{approval_id}.json"
    if not approval_file.exists():
        print(f"Error: Approval {approval_id} not found", file=sys.stderr)
        return None
    
    with open(approval_file, 'r') as f:
        data = json.load(f)
    
    if data.get("approved") is not None:
        print(f"Error: Approval {approval_id} has already been reviewed", file=sys.stderr)
        return None
    
    data["approved"] = True
    data["reviewed_at"] = datetime.now().isoformat()
    data["reviewer"] = reviewer
    data["review_notes"] = notes
    
    with open(approval_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    return {"success": True, "approval_id": approval_id, "approved": True}


def reject(approval_id: str, reviewer: str = "cli", notes: str = "", use_api: bool = True):
    """Reject an approval request."""
    if use_api:
        try:
            response = requests.post(
                f"{API_BASE}/hitl/approvals/{approval_id}/reject",
                json={"reviewer": reviewer, "review_notes": notes},
                timeout=10
            )
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"API error: {e}", file=sys.stderr)
    
    # Fallback to file system
    approval_file = HITL_APPROVALS_DIR / f"{approval_id}.json"
    if not approval_file.exists():
        print(f"Error: Approval {approval_id} not found", file=sys.stderr)
        return None
    
    with open(approval_file, 'r') as f:
        data = json.load(f)
    
    if data.get("approved") is not None:
        print(f"Error: Approval {approval_id} has already been reviewed", file=sys.stderr)
        return None
    
    data["approved"] = False
    data["reviewed_at"] = datetime.now().isoformat()
    data["reviewer"] = reviewer
    data["review_notes"] = notes
    
    with open(approval_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    return {"success": True, "approval_id": approval_id, "approved": False}


def print_approval(approval: dict):
    """Print approval details."""
    approval_id = approval.get("approval_id", "unknown")
    company = approval.get("company_name", "Unknown")
    status = "pending" if approval.get("approved") is None else (
        "approved" if approval.get("approved") else "rejected"
    )
    
    print(f"\nApproval ID: {approval_id}")
    print(f"Company: {company}")
    print(f"Status: {status}")
    print(f"Risk Count: {approval.get('risk_count', 0)}")
    print(f"Paused At: {approval.get('paused_at', 'N/A')}")
    
    if approval.get("reviewed_at"):
        print(f"Reviewed At: {approval.get('reviewed_at')}")
        print(f"Reviewer: {approval.get('reviewer', 'N/A')}")
        if approval.get("review_notes"):
            print(f"Notes: {approval.get('review_notes')}")
    
    if approval.get("risks"):
        print("\nRisks:")
        for i, risk in enumerate(approval.get("risks", [])[:5], 1):
            print(f"  {i}. {risk.get('risk_type', 'unknown')} ({risk.get('severity', 'unknown')})")


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(description="HITL Approval CLI Tool")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List approval requests")
    list_parser.add_argument("--status", choices=["pending", "approved", "rejected"], help="Filter by status")
    list_parser.add_argument("--no-api", action="store_true", help="Don't use API, use file system only")
    
    # Get command
    get_parser = subparsers.add_parser("get", help="Get approval details")
    get_parser.add_argument("approval_id", help="Approval ID")
    get_parser.add_argument("--no-api", action="store_true", help="Don't use API, use file system only")
    
    # Approve command
    approve_parser = subparsers.add_parser("approve", help="Approve a request")
    approve_parser.add_argument("approval_id", help="Approval ID")
    approve_parser.add_argument("--reviewer", default="cli", help="Reviewer name")
    approve_parser.add_argument("--notes", default="", help="Review notes")
    approve_parser.add_argument("--no-api", action="store_true", help="Don't use API, use file system only")
    
    # Reject command
    reject_parser = subparsers.add_parser("reject", help="Reject a request")
    reject_parser.add_argument("approval_id", help="Approval ID")
    reject_parser.add_argument("--reviewer", default="cli", help="Reviewer name")
    reject_parser.add_argument("--notes", default="", help="Review notes")
    reject_parser.add_argument("--no-api", action="store_true", help="Don't use API, use file system only")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    use_api = not args.no_api
    
    if args.command == "list":
        approvals = list_approvals(status=args.status, use_api=use_api)
        print(f"\nFound {len(approvals)} approval request(s):\n")
        for approval in approvals:
            approval_id = approval.get("approval_id", "unknown")
            company = approval.get("company_name", "Unknown")
            status = "pending" if approval.get("approved") is None else (
                "approved" if approval.get("approved") else "rejected"
            )
            print(f"  {approval_id[:8]}... | {company:20} | {status}")
    
    elif args.command == "get":
        approval = get_approval(args.approval_id, use_api=use_api)
        if approval:
            print_approval(approval)
        else:
            print(f"Error: Approval {args.approval_id} not found", file=sys.stderr)
            sys.exit(1)
    
    elif args.command == "approve":
        result = approve(args.approval_id, args.reviewer, args.notes, use_api=use_api)
        if result:
            print(f"✅ Approved: {args.approval_id}")
        else:
            print(f"❌ Failed to approve: {args.approval_id}", file=sys.stderr)
            sys.exit(1)
    
    elif args.command == "reject":
        result = reject(args.approval_id, args.reviewer, args.notes, use_api=use_api)
        if result:
            print(f"❌ Rejected: {args.approval_id}")
        else:
            print(f"❌ Failed to reject: {args.approval_id}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()

