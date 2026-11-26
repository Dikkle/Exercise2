"""clean_and_merge.py

Reads customer and order data files, cleans duplicates, converts all amounts
to CNY, merges the two datasets on 'customer_id', writes the merged data to
an SQLite database, and creates a summary table (average amount_cny by region).

Usage:
    python clean_and_merge.py                       # use default file paths
    python clean_and_merge.py data/customer.txt data/order.txt
"""

import argparse
import os
import sqlite3

import pandas as pd

# ---------------------------------------------------------------------------
# Configuration (defaults; can be overridden via command-line arguments)
# ---------------------------------------------------------------------------
DEFAULT_CUSTOMER_FILE = r"C:\Users\ydlou\Desktop\MIS2001(customer).txt"
DEFAULT_ORDER_FILE = r"C:\Users\ydlou\Desktop\MIS2001(order).txt"
DB_FILE = "merged_data.db"

# Currency conversion rates to CNY
CURRENCY_TO_CNY = {
    "USD": 6.9,
    "EUR": 7.5,
    "CNY": 1.0,
    "JPY": 0.05,
}


def read_data(customer_path: str, order_path: str):
    """Read the two data files into DataFrames."""
    customers = pd.read_csv(customer_path)
    orders = pd.read_csv(order_path)
    return customers, orders


def clean_duplicates(customers: pd.DataFrame, orders: pd.DataFrame):
    """Remove duplicate rows from both datasets."""
    customers_before = len(customers)
    orders_before = len(orders)

    customers = customers.drop_duplicates().reset_index(drop=True)
    orders = orders.drop_duplicates().reset_index(drop=True)

    print(f"Customers: {customers_before} -> {len(customers)} rows after dedup")
    print(f"Orders:    {orders_before} -> {len(orders)} rows after dedup")
    return customers, orders


def convert_amounts(orders: pd.DataFrame) -> pd.DataFrame:
    """Convert all amount values to CNY and store in a new column 'amount_cny'."""
    orders = orders.copy()

    # Normalise currency codes (strip whitespace, upper-case) for safe lookup
    currency_norm = orders["currency"].astype(str).str.strip().str.upper()
    unknown = set(currency_norm) - set(CURRENCY_TO_CNY)
    if unknown:
        raise ValueError(f"Unknown currency codes found: {sorted(unknown)}")

    rates = currency_norm.map(CURRENCY_TO_CNY)
    orders["amount_cny"] = pd.to_numeric(orders["amount"], errors="coerce") * rates

    print("Converted amounts to CNY:")
    print(orders[["order_id", "amount", "currency", "amount_cny"]].to_string(index=False))
    return orders


def merge_data(customers: pd.DataFrame, orders: pd.DataFrame) -> pd.DataFrame:
    """Connect (join) order data and customer data on 'customer_id'."""
    merged = orders.merge(customers, on="customer_id", how="inner")
    print(f"\nMerged data: {len(merged)} rows")
    return merged


def write_to_database(merged: pd.DataFrame, db_path: str) -> None:
    """Write the merged data and the region summary table to SQLite."""
    # Summary: average amount_cny by region
    summary = (
        merged.groupby("region", as_index=False)["amount_cny"]
        .mean()
        .rename(columns={"amount_cny": "avg_amount_cny"})
    )

    conn = sqlite3.connect(db_path)
    try:
        merged.to_sql("merged_orders", conn, if_exists="replace", index=False)
        summary.to_sql("avg_amount_by_region", conn, if_exists="replace", index=False)
        conn.commit()
    finally:
        conn.close()

    print(f"\nSaved merged data to table 'merged_orders' in {db_path}")
    print(f"Saved summary table 'avg_amount_by_region' in {db_path}")
    print("\nAverage amount_cny by region:")
    print(summary.to_string(index=False))


def parse_args():
    parser = argparse.ArgumentParser(description="Clean, convert and merge order/customer data into SQLite.")
    parser.add_argument("customer_file", nargs="?", default=DEFAULT_CUSTOMER_FILE,
                        help="Path to the customer data file (txt/csv)")
    parser.add_argument("order_file", nargs="?", default=DEFAULT_ORDER_FILE,
                        help="Path to the order data file (txt/csv)")
    return parser.parse_args()


def main():
    args = parse_args()
    customers, orders = read_data(args.customer_file, args.order_file)
    customers, orders = clean_duplicates(customers, orders)
    orders = convert_amounts(orders)
    merged = merge_data(customers, orders)
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DB_FILE)
    write_to_database(merged, db_path)


if __name__ == "__main__":
    main()
