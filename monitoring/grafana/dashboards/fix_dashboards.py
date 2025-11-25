#!/usr/bin/env python3
"""
Fix Grafana dashboard templates to use correct datasource UIDs.

This script processes dashboard JSON files that use __inputs placeholders
and replaces them with actual datasource UIDs configured in datasources.yaml
"""

import json
import sys
from pathlib import Path

# Datasource UID mapping (matches datasources.yaml)
DATASOURCE_MAPPING = {
    "DS_PROMETHEUS": "prometheus-uid",
    "DS_LOKI": "loki-uid",
    "DS_TEMPO": "tempo-uid",
}


def fix_dashboard(dashboard_path: Path) -> bool:
    """
    Fix a single dashboard file by replacing datasource placeholders.

    Returns True if file was modified, False otherwise.
    """
    print(f"\n📄 Processing: {dashboard_path.name}")

    try:
        with open(dashboard_path, "r") as f:
            content = f.read()

        original_content = content
        modified = False

        # Remove __inputs and __requires sections (not needed after provisioning)
        data = json.loads(content)

        if "__inputs" in data:
            print(f"  ✓ Removing __inputs section")
            del data["__inputs"]
            modified = True

        if "__requires" in data:
            print(f"  ✓ Removing __requires section")
            del data["__requires"]
            modified = True

        # Convert back to string for regex replacements
        content = json.dumps(data, indent=2)

        # Replace datasource placeholder variables: ${DS_PROMETHEUS} -> prometheus-uid
        for placeholder, uid in DATASOURCE_MAPPING.items():
            old_pattern = f"${{{placeholder}}}"
            if old_pattern in content:
                count = content.count(old_pattern)
                content = content.replace(old_pattern, uid)
                print(f"  ✓ Replaced {count}x: ${{{placeholder}}} → {uid}")
                modified = True

        if modified:
            # Parse back to JSON to ensure valid format
            data = json.loads(content)

            # Set null id to enable provisioning
            if data.get("id") is not None:
                data["id"] = None
                print(f"  ✓ Set dashboard id to null (for provisioning)")

            # Write back with pretty formatting
            with open(dashboard_path, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")  # Add trailing newline

            print(f"  ✅ Dashboard fixed successfully")
            return True
        else:
            print(f"  ⏭️  No changes needed")
            return False

    except json.JSONDecodeError as e:
        print(f"  ❌ JSON parsing error: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False


def main():
    """Process all dashboard JSON files in current directory."""
    dashboards_dir = Path(__file__).parent

    print("=" * 60)
    print("🔧 Grafana Dashboard Fixer")
    print("=" * 60)
    print(f"\n📁 Working directory: {dashboards_dir}")
    print(f"\n🎯 Datasource mappings:")
    for placeholder, uid in DATASOURCE_MAPPING.items():
        print(f"   ${{{placeholder}}} → {uid}")

    # Find all JSON dashboard files (exclude this script and other non-dashboard files)
    dashboard_files = [
        f for f in dashboards_dir.glob("*.json") if f.name not in ["fix_dashboards.py"]
    ]

    if not dashboard_files:
        print("\n⚠️  No dashboard JSON files found")
        return 1

    print(f"\n📊 Found {len(dashboard_files)} dashboard(s) to process")

    # Process each dashboard
    modified_count = 0
    for dashboard_file in sorted(dashboard_files):
        if fix_dashboard(dashboard_file):
            modified_count += 1

    # Summary
    print("\n" + "=" * 60)
    print(f"✨ Summary: {modified_count}/{len(dashboard_files)} dashboards modified")
    print("=" * 60)

    if modified_count > 0:
        print("\n✅ Dashboards fixed successfully!")
        print("\nNext steps:")
        print("1. Restart Grafana: docker compose restart grafana")
        print("2. Check dashboards at: http://localhost:3000/dashboards")
        return 0
    else:
        print("\n✓ All dashboards already configured correctly")
        return 0


if __name__ == "__main__":
    sys.exit(main())
