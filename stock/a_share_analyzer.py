import requests
import pandas as pd
import numpy as np
from typing import List, Dict, Any
import math
import sys
import os
from datetime import datetime

# Get the directory of the current file and add it to the path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Import the stock_hq_tool module directly
from stock_hq_tool import StockHQFromSina


class AShareMarketAnalyzer:
    """
    Analyzes the entire A-share market data to calculate trading volume and transaction amount statistics
    """
    
    def __init__(self):
        self.stock_hq_tool = StockHQFromSina()
        # A-share market stock prefixes
        self.shanghai_prefixes = ['60', '688', '689']  # Shanghai market prefixes
        self.shenzhen_prefixes = ['00', '30', '15', '16']  # Shenzhen market prefixes
    
    def generate_all_a_share_codes(self) -> List[str]:
        """
        Generate stock codes for major A-share stocks
        Reads from all_a_code.csv file in the same directory
        """
        # Get the directory of the current file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        csv_path = os.path.join(current_dir, 'all_a_code.csv')
        
        # Read the CSV file and extract the 'code' column
        try:
            df = pd.read_csv(csv_path, encoding='utf-8-sig', dtype={'code': str})  # Using utf-8-sig to handle BOM if present, and ensure code column is read as string
            codes = df['code'].dropna().apply(lambda x: str(x).strip()).tolist()  # Extract codes, remove NaN, ensure as string and strip whitespace
            
            # Filter out any empty strings and ensure codes are valid
            valid_codes = [code for code in codes if code != '']
            
            return valid_codes
        except FileNotFoundError:
            print(f"CSV file not found at {csv_path}")
            return []
        except KeyError:
            print("Column 'code' not found in the CSV file")
            return []
        except Exception as e:
            print(f"Error reading CSV file: {e}")
            return []
    
    def fetch_all_market_data(self, stock_codes: List[str] = None) -> pd.DataFrame:
        """
        Fetch data for all A-share stocks
        """
        if stock_codes is None:
            stock_codes = self.generate_all_a_share_codes()
        
        # Remove duplicates while preserving order
        unique_stock_codes = list(dict.fromkeys(stock_codes))
        
        # Process in batches to avoid request limits
        batch_size = 50
        all_data = []
        
        print(f"Fetching data for {len(unique_stock_codes)} unique stocks...")
        
        for i in range(0, len(unique_stock_codes), batch_size):
            batch = unique_stock_codes[i:i + batch_size]
            # print(f"Processing batch {i//batch_size + 1}/{math.ceil(len(unique_stock_codes)/batch_size)}...")
            
            try:
                result = self.stock_hq_tool.get_stock_hq(batch)
                if result['data']:
                    all_data.extend(result['data'])
            except Exception as e:
                print(f"Error fetching batch {i//batch_size + 1}: {e}")
                continue
        
        # Convert to DataFrame
        if all_data:
            df = pd.DataFrame(all_data)
            # Filter out stocks with zero or invalid volume and transaction amount
            df = df[(df['volume'] > 0) & (df['transaction_amount'] > 0)]
            return df
        else:
            return pd.DataFrame(columns=['code', 'name', 'current_price', 'volume', 'transaction_amount'])
    
    def calculate_top_volume_percentage(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate what percentage of total market volume is represented by the top 5% of stocks by volume
        """
        if df.empty or 'volume' not in df.columns:
            return {
                'top_5_percent_volume': 0,
                'total_market_volume': 0,
                'percentage_of_total': 0,
                'top_5_percent_count': 0,
                'total_count': 0
            }
        
        # Sort by volume descending
        df_sorted = df.sort_values('volume', ascending=False)
        
        # Calculate total market volume
        total_market_volume = df_sorted['volume'].sum()
        
        if total_market_volume == 0:
            return {
                'top_5_percent_volume': 0,
                'total_market_volume': 0,
                'percentage_of_total': 0,
                'top_5_percent_count': 0,
                'total_count': len(df_sorted)
            }
        
        # Calculate how many stocks represent the top 5%
        top_5_percent_count = max(1, int(len(df_sorted) * 0.05))
        
        # Get the top 5% by volume
        top_5_percent_df = df_sorted.head(top_5_percent_count)
        top_5_percent_volume = top_5_percent_df['volume'].sum()
        
        # Calculate percentage
        percentage_of_total = (top_5_percent_volume / total_market_volume) * 100
        
        return {
            'top_5_percent_volume': top_5_percent_volume,
            'total_market_volume': total_market_volume,
            'percentage_of_total': round(percentage_of_total, 2),
            'top_5_percent_count': top_5_percent_count,
            'total_count': len(df_sorted),
            'top_5_percent_stocks': top_5_percent_df[['code', 'name', 'volume', 'transaction_amount']].to_dict('records')
        }
    
    def calculate_top_transaction_amount_percentage(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate what percentage of total market transaction amount is represented by the top 5% of stocks by transaction amount
        """
        if df.empty or 'transaction_amount' not in df.columns:
            return {
                'top_5_percent_transaction_amount': 0,
                'total_market_transaction_amount': 0,
                'percentage_of_total': 0,
                'top_5_percent_count': 0,
                'total_count': 0
            }
        
        # Sort by transaction amount descending
        df_sorted = df.sort_values('transaction_amount', ascending=False)
        
        # Calculate total market transaction amount
        total_market_transaction_amount = df_sorted['transaction_amount'].sum()
        
        if total_market_transaction_amount == 0:
            return {
                'top_5_percent_transaction_amount': 0,
                'total_market_transaction_amount': 0,
                'percentage_of_total': 0,
                'top_5_percent_count': 0,
                'total_count': len(df_sorted)
            }
        
        # Calculate how many stocks represent the top 5%
        top_5_percent_count = max(1, int(len(df_sorted) * 0.05))
        
        # Get the top 5% by transaction amount
        top_5_percent_df = df_sorted.head(top_5_percent_count)
        top_5_percent_transaction_amount = top_5_percent_df['transaction_amount'].sum()
        
        # Calculate percentage
        percentage_of_total = (top_5_percent_transaction_amount / total_market_transaction_amount) * 100
        
        return {
            'top_5_percent_transaction_amount': top_5_percent_transaction_amount,
            'total_market_transaction_amount': total_market_transaction_amount,
            'percentage_of_total': round(percentage_of_total, 2),
            'top_5_percent_count': top_5_percent_count,
            'total_count': len(df_sorted),
            'top_5_percent_stocks': top_5_percent_df[['code', 'name', 'volume', 'transaction_amount']].to_dict('records')
        }
    
    def calculate_tmt_crowding_ratio(self, full_market_df: pd.DataFrame = None) -> Dict[str, Any]:
        """
        Calculate the TMT industry crowding ratio - the proportion of total market transaction amount
        represented by the stocks in the TMT industry (from tmt_industry_stocks.csv)
        """
        # Load TMT industry stocks from the CSV file
        tmt_csv_path = os.path.join(current_dir, 'tmt_industry_stocks.csv')
        
        try:
            tmt_df = pd.read_csv(tmt_csv_path, encoding='utf-8-sig')
            print(f"Loaded TMT industry stocks CSV with {len(tmt_df)} records")
        except FileNotFoundError:
            print(f"TMT industry stocks CSV file not found at {tmt_csv_path}")
            return {
                'tmt_transaction_amount': 0,
                'total_market_transaction_amount': 0,
                'tmt_crowding_ratio': 0,
                'tmt_stock_count': 0,
                'total_stock_count': 0,
                'tmt_in_top_5_percent': 0,
                'tmt_top_5_percent_share': 0
            }
        
        # Extract TMT stock codes
        if 'code' not in tmt_df.columns:
            print("Column 'code' not found in TMT industry stocks CSV")
            return {
                'tmt_transaction_amount': 0,
                'total_market_transaction_amount': 0,
                'tmt_crowding_ratio': 0,
                'tmt_stock_count': 0,
                'total_stock_count': 0,
                'tmt_in_top_5_percent': 0,
                'tmt_top_5_percent_share': 0
            }
        
        # Get unique TMT stock codes
        tmt_stock_codes = tmt_df['code'].dropna().astype(str).tolist()
        tmt_stock_codes = list(dict.fromkeys(tmt_stock_codes))  # Remove duplicates while preserving order
        
        print(f"Found {len(tmt_stock_codes)} unique TMT stock codes")
        
        # Fetch market data if not provided
        if full_market_df is None:
            all_market_df = self.fetch_all_market_data()
        else:
            all_market_df = full_market_df
        
        if all_market_df.empty:
            print("No market data fetched for crowding calculation.")
            return {
                'tmt_transaction_amount': 0,
                'total_market_transaction_amount': 0,
                'tmt_crowding_ratio': 0,
                'tmt_stock_count': 0,
                'total_stock_count': 0,
                'tmt_in_top_5_percent': 0,
                'tmt_top_5_percent_share': 0
            }
        
        # Calculate total market transaction amount
        total_market_transaction_amount = all_market_df['transaction_amount'].sum()
        total_stock_count = len(all_market_df)
        
        # Filter for TMT stocks in the market data
        tmt_stocks_in_market = all_market_df[all_market_df['code'].isin(tmt_stock_codes)]
        
        # Calculate TMT transaction amount
        tmt_transaction_amount = tmt_stocks_in_market['transaction_amount'].sum()
        tmt_stock_count = len(tmt_stocks_in_market)
        
        # Calculate crowding ratio
        if total_market_transaction_amount > 0:
            tmt_crowding_ratio = (tmt_transaction_amount / total_market_transaction_amount) * 100
        else:
            tmt_crowding_ratio = 0
        
        # Calculate top 5% of stocks by transaction amount
        all_market_sorted = all_market_df.sort_values('transaction_amount', ascending=False)
        top_5_percent_count = max(1, int(len(all_market_sorted) * 0.05))
        top_5_percent_df = all_market_sorted.head(top_5_percent_count)
        top_5_percent_transaction_amount = top_5_percent_df['transaction_amount'].sum()
        
        # Find TMT stocks in top 5% of all stocks
        tmt_in_top_5_percent_df = top_5_percent_df[top_5_percent_df['code'].isin(tmt_stock_codes)]
        tmt_in_top_5_percent_count = len(tmt_in_top_5_percent_df)
        tmt_transaction_in_top_5_amount = tmt_in_top_5_percent_df['transaction_amount'].sum()
        
        # Calculate TMT's share of top 5% transaction amount
        if top_5_percent_transaction_amount > 0:
            tmt_top_5_percent_share = (tmt_transaction_in_top_5_amount / top_5_percent_transaction_amount) * 100
        else:
            tmt_top_5_percent_share = 0
        
        print(f"TMT stocks in market data: {tmt_stock_count}/{len(tmt_stock_codes)}")
        print(f"TMT transaction amount: ¥{tmt_transaction_amount:,.0f}")
        print(f"Total market transaction amount: ¥{total_market_transaction_amount:,.0f}")
        print(f"TMT crowding ratio: {tmt_crowding_ratio:.2f}%")
        print(f"TMT stocks in top 5%: {tmt_in_top_5_percent_count}/{top_5_percent_count}")
        print(f"TMT share of top 5% transaction amount: {tmt_top_5_percent_share:.2f}%")
        
        return {
            'tmt_transaction_amount': tmt_transaction_amount,
            'total_market_transaction_amount': total_market_transaction_amount,
            'tmt_crowding_ratio': round(tmt_crowding_ratio, 2),
            'tmt_stock_count': tmt_stock_count,
            'total_stock_count': total_stock_count,
            'tmt_in_top_5_percent': tmt_in_top_5_percent_count,
            'tmt_top_5_percent_share': round(tmt_top_5_percent_share, 2),
            'tmt_stocks_data': tmt_stocks_in_market,
            'top_5_percent_stocks': top_5_percent_df,
            'tmt_in_top_5_data': tmt_in_top_5_percent_df
        }
    
    def analyze_market_concentration(self, stock_codes: List[str] = None) -> Dict[str, Any]:
        """
        Main method to analyze market concentration by both volume and transaction amount
        """
        print("Starting A-share market analysis...")
        
        # Fetch market data
        df = self.fetch_all_market_data(stock_codes)
        
        if df.empty:
            print("No market data fetched.")
            return {}
        
        print(f"Fetched data for {len(df)} stocks")
        
        # Output the securities codes
        # print(f"\nSecurities codes fetched ({len(df)} total):")
        # securities_codes = df['code'].tolist()
        # print(securities_codes)
        
        # Calculate top volume percentage
        volume_result = self.calculate_top_volume_percentage(df)
        
        # Calculate top transaction amount percentage
        transaction_result = self.calculate_top_transaction_amount_percentage(df)
        
        # Print combined results
        print(f"\n=== MARKET CONCENTRATION ANALYSIS RESULTS ===")
        print(f"Total stocks analyzed: {volume_result['total_count']}")
        print(f"Top 5% of stocks count: {volume_result['top_5_percent_count']}")
        
        # print(f"\n--- VOLUME ANALYSIS ---")
        # print(f"Total market volume: {volume_result['total_market_volume']:,.0f}")
        # print(f"Volume of top 5% stocks: {volume_result['top_5_percent_volume']:,.0f}")
        # print(f"Percentage of total volume held by top 5%: {volume_result['percentage_of_total']}%")
        
        print(f"\n--- TRANSACTION AMOUNT ANALYSIS ---")
        print(f"Total market transaction amount: ¥{transaction_result['total_market_transaction_amount']:,.0f}")
        print(f"Transaction amount of top 5% stocks: ¥{transaction_result['top_5_percent_transaction_amount']:,.0f}")
        print(f"Percentage of total transaction amount held by top 5%: {transaction_result['percentage_of_total']}%")
        
        print(f"\n--- TOP 5% STOCKS BY TRANSACTION AMOUNT ---")
        for i, stock in enumerate(transaction_result['top_5_percent_stocks'], 1):
            print(f"  {i}. {stock['code']} - {stock['name']} - Vol: {stock['volume']:,} - Trans: ¥{stock['transaction_amount']:,.0f}")
        
        return {
            'volume_analysis': volume_result,
            'transaction_analysis': transaction_result,
            'full_dataframe': df
        }
    
    def save_results_to_csv(self, transaction_result: Dict[str, Any], tmt_result: Dict[str, Any]):
        """
        Save the analysis results to amount_result.csv in the specified format
        """
        # Prepare the data row
        date_str = datetime.now().strftime('%Y-%m-%d')
        total_stocks = transaction_result['total_count']
        total_amount = transaction_result['total_market_transaction_amount']
        top_5_percent_amount = transaction_result['top_5_percent_transaction_amount']
        top_5_percent_ratio = transaction_result['percentage_of_total']
        tmt_amount = tmt_result['tmt_transaction_amount']
        tmt_ratio = tmt_result['tmt_crowding_ratio']
        
        # Create the data row
        data_row = {
            'date': date_str,
            'total stocks': total_stocks,
            'total amount': total_amount,
            '5% amount': top_5_percent_amount,
            'percentage': top_5_percent_ratio,
            'tmt amount': tmt_amount,
            'ratio': tmt_ratio
        }
        
        # Define CSV file path
        csv_file_path = os.path.join(current_dir, 'amount_result.csv')
        
        # Check if file exists
        if os.path.exists(csv_file_path):
            # Read existing data
            df_existing = pd.read_csv(csv_file_path)
            
            # Check if today's date already exists in the file
            if date_str in df_existing['date'].values:
                # Find the index of the row with today's date
                idx = df_existing.index[df_existing['date'] == date_str][0]
                
                # Update the values in that row
                df_existing.at[idx, 'total stocks'] = total_stocks
                df_existing.at[idx, 'total amount'] = total_amount
                df_existing.at[idx, '5% amount'] = top_5_percent_amount
                df_existing.at[idx, 'percentage'] = top_5_percent_ratio
                df_existing.at[idx, 'tmt amount'] = tmt_amount
                df_existing.at[idx, 'ratio'] = tmt_ratio
            else:
                # Append new row
                df_new_row = pd.DataFrame([data_row])
                df_existing = pd.concat([df_existing, df_new_row], ignore_index=True)
            
            # Write back to CSV
            df_existing.to_csv(csv_file_path, index=False)
        else:
            # Create new CSV file with the header and the data row
            df_new = pd.DataFrame([data_row])
            df_new.to_csv(csv_file_path, index=False)
        
        print(f"Results saved to {csv_file_path}")


def main():
    """
    Main function to demonstrate the A-share market analysis
    """
    analyzer = AShareMarketAnalyzer()
    
    # Perform the general analysis
    result = analyzer.analyze_market_concentration()
    
    # Get the full market DataFrame for TMT analysis
    full_market_df = result.get('full_dataframe', None)
    
    print(f"\n=== TMT INDUSTRY CROWDING ANALYSIS ===")
    # Perform TMT crowding analysis
    tmt_result = analyzer.calculate_tmt_crowding_ratio(full_market_df)
    
    print(f"\n--- TMT INDUSTRY CROWDING METRICS ---")
    print(f"TMT stocks in market data: {tmt_result['tmt_stock_count']}/{tmt_result['total_stock_count']} total stocks")
    print(f"TMT transaction amount: ¥{tmt_result['tmt_transaction_amount']:,.0f}")
    print(f"Total market transaction amount: ¥{tmt_result['total_market_transaction_amount']:,.0f}")
    print(f"TMT crowding ratio: {tmt_result['tmt_crowding_ratio']}%")
    
    print(f"\n--- TMT IN TOP 5% ANALYSIS ---")
    print(f"TMT stocks in top 5% by transaction amount: {tmt_result['tmt_in_top_5_percent']}/{int(tmt_result['total_stock_count']*0.05)} stocks")
    print(f"TMT share of top 5% transaction amount: {tmt_result['tmt_top_5_percent_share']}%")
    
    # Print top TMT stocks by transaction amount
    if not tmt_result['tmt_stocks_data'].empty:
        tmt_sorted = tmt_result['tmt_stocks_data'].sort_values('transaction_amount', ascending=False)
        print(f"\n--- TOP TMT STOCKS BY TRANSACTION AMOUNT ---")
        for i, (_, stock) in enumerate(tmt_sorted.head(10).iterrows(), 1):
            print(f"  {i}. {stock['code']} - {stock['name']} - Trans: ¥{stock['transaction_amount']:,.0f}")
    
    # Print TMT stocks in top 5% of all stocks
    if not tmt_result['tmt_in_top_5_data'].empty:
        tmt_in_top_sorted = tmt_result['tmt_in_top_5_data'].sort_values('transaction_amount', ascending=False)
        print(f"\n--- TMT STOCKS IN TOP 5% BY TRANSACTION AMOUNT ---")
        for i, (_, stock) in enumerate(tmt_in_top_sorted.head(10).iterrows(), 1):
            print(f"  {i}. {stock['code']} - {stock['name']} - Trans: ¥{stock['transaction_amount']:,.0f}")
    
    # Save results to CSV
    analyzer.save_results_to_csv(result['transaction_analysis'], tmt_result)
    
    return result, tmt_result


if __name__ == "__main__":
    main()
    #     这是极度扭曲的市场结构在今天开始溃散。这个结构有多扭曲呢？
    # 1、A股45%的成交量在科技股；
    # 2、从去年5月至今的一年中，新增融资余额1.1万亿全在科技股；
    # 3、A股股价前100只只有7、8只不是科技股，股价超过100的283只股票只有20只左右不是科技股；
    # 4、科创板次新股一个月涨3~5倍的比比皆是；
    # 5、某些知名基金经理从消费换仓到科技股。
    # 然而，树不可能涨到天上。当所有资金全部进入科技股，一旦后续资金不继，先知先觉的游资开始撤退，
    # 随即杠杆资金就开始踩踏。接下来的行情需要特别关注，可能还有一根标志性的断头铡。
    # 当然，百足之虫死而不僵，这么多资金拥挤在里面，纳指和韩国指数还在大涨，A股科技股行情还会有反复。
    # 但纳指和韩国科技公司挣的是真钱，英伟达挣了钱，花800亿美元回购注销，
    # 后续科技股行情即便反复，但风险很高了，一不小心就被断头铡给斩了。
    # 说实话，1.1万亿融资盘在里面、45%活跃资金在里面、那么多抱团资金在里面，
    # 我不相信他们都能把钱带走。因为大家都赚钱走人的话，那谁亏钱呢？
    # 2021年1月白酒抱团和医药抱团见顶，相关板块跌了5年还没有起色。
    # 这轮科技股如果见顶，1、2年内大概是不能碰了。现在我最关注的问题有两个，
    # 大盘会被科技股带下去多少？哪些板块会率先见底反弹？密切关注吧。
    #  英文缩写	英文全称	对应A股行业
    # T (Technology)	科技	电子、计算机
    # M (Media)	媒体	传媒
    # T (Telecom)	电信	通信