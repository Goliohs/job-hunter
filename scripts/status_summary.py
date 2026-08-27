"""Resumen rápido del estado de aplicaciones (ClickHouse y general)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.store import get_conn

conn = get_conn()

print("=== RESUMEN GLOBAL ===")
for r in conn.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status ORDER BY COUNT(*) DESC"):
    print(f"  {r[0]:<10} {r[1]}")

print(f"\n=== CLICKHOUSE (18+ targets) ===")
total_ch = conn.execute("SELECT COUNT(*) FROM jobs WHERE lower(company) LIKE '%clickhouse%'").fetchone()[0]
applied_ch = conn.execute("SELECT COUNT(*) FROM jobs WHERE lower(company) LIKE '%clickhouse%' AND status='applied'").fetchone()[0]
parked_ch = conn.execute("SELECT COUNT(*) FROM jobs WHERE lower(company) LIKE '%clickhouse%' AND status='parked'").fetchone()[0]
new_ch = conn.execute("SELECT COUNT(*) FROM jobs WHERE lower(company) LIKE '%clickhouse%' AND status='new'").fetchone()[0]
failed_ch = conn.execute("SELECT COUNT(*) FROM jobs WHERE lower(company) LIKE '%clickhouse%' AND status='failed'").fetchone()[0]
print(f"  Aplicados: {applied_ch}/{total_ch} | parked: {parked_ch} | new: {new_ch} | failed: {failed_ch}")

print("\n=== ULTIMOS 10 APLICADOS ===")
for r in conn.execute("SELECT id, substr(company,1,12), substr(title,1,40), applied_date FROM jobs WHERE status='applied' ORDER BY applied_date DESC LIMIT 10"):
    print(f"  {r[0]:<5} {r[1]:<12} {r[2]:<40} {r[3]}")

print("\n=== PARKED (requieren humano / semi-auto) ===")
for r in conn.execute("SELECT id, substr(company,1,12), match_score, substr(title,1,40) FROM jobs WHERE status='parked' ORDER BY match_score DESC LIMIT 12"):
    print(f"  {r[0]:<5} {r[1]:<12} s={r[2]:<3} {r[3]}")