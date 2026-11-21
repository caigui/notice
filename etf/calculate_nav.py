import pandas as pd
import requests
from datetime import datetime

# Constants
PCF_URL = "https://www.sse.com.cn/assortment/fund/list/etfinfo/basic/index.shtml?FUNDID=511520"
BOND_VALUATION_URL = "https://www.csindex.com.cn/valuation"  # Placeholder URL
OUTPUT_FILE = "c:\\Users\\admin\\Documents\\MCGA\\notice\\etf\\nav_records.txt"

def fetch_pcf_data():
    """
    Fetch yesterday's PCF data from SSE.
    Returns a DataFrame with bond codes, full price, and holdings.
    """
    try:
        # Simulate fetching data from SSE
        data = {
            "债券代码": ["220203.IB", "200215.IB", "210312.IB"],
            "估值全价_PCF(元)": [115.1397, 114.8833, 112.6711],
            "持仓张数": [1_000_000, 800_000, 600_000],
        }
        return pd.DataFrame(data)
    except Exception as e:
        print(f"Error fetching PCF data: {e}")
        raise

def fetch_bond_valuation():
    """
    Fetch today's bond valuation data from ChinaBond/CSI.
    Returns a dictionary mapping bond codes to their full prices.
    """
    try:
        # Simulate fetching data from ChinaBond/CSI
        return {
            "220203.IB": 115.2399,
            "200215.IB": 114.9502,
            "210312.IB": 112.7405,
        }
    except Exception as e:
        print(f"Error fetching bond valuation data: {e}")
        raise

def calculate_nav(pcf_data, bond_valuation, cash_component, total_shares):
    """
    Calculate the Net Asset Value (NAV) of the fund.
    Args:
        pcf_data (pd.DataFrame): Yesterday's PCF data.
        bond_valuation (dict): Today's bond valuation data.
        cash_component (float): Cash component from PCF.
        total_shares (int): Total shares of the fund.
    Returns:
        float: Calculated NAV.
    """
    # Add today's valuation full price to the DataFrame
    pcf_data["估值全价_Today"] = pcf_data["债券代码"].map(bond_valuation)

    # Calculate today's bond market value
    pcf_data["市值_Today"] = pcf_data["估值全价_Today"] * pcf_data["持仓张数"]

    # Sum up today's total assets
    total_assets = pcf_data["市值_Today"].sum() + cash_component

    # Calculate NAV
    nav = total_assets / total_shares
    return nav

def save_nav_record(nav, official_valuation):
    """
    Save the NAV record to a local text file.
    Args:
        nav (float): Calculated NAV.
        official_valuation (float): Official valuation for comparison.
    """
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")
    price = 2.045  # Example price
    premium = ((price - nav) / nav) * 100  # Premium calculation
    error = ((nav - official_valuation) / official_valuation) * 100  # Error calculation

    record = (
        f"{date_str} {price:.3f} {nav:.4f} {premium:.2f}% "
        f"{official_valuation:.3f} {time_str} {error:.2f}%\n"
    )

    with open(OUTPUT_FILE, "a") as file:
        file.write(record)

def main():
    try:
        # Step 1: Fetch PCF data
        pcf_data = fetch_pcf_data()

        # Step 2: Fetch bond valuation data
        bond_valuation = fetch_bond_valuation()

        # Step 3: Define constants from PCF
        cash_component = -1_256_400  # Example cash component
        total_shares = 300_000_000  # Example total shares
        official_valuation = 1.1755  # Example official valuation

        # Step 4: Calculate NAV
        nav = calculate_nav(pcf_data, bond_valuation, cash_component, total_shares)

        # Step 5: Save NAV record
        save_nav_record(nav, official_valuation)

        print(f"NAV calculated and saved successfully: {nav:.4f}")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()