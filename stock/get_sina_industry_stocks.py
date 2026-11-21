import akshare as ak
import pandas as pd
import os

def get_industry_mapping():
    """
    Get the 16 specific industries that need to be matched
    """
    industries = [
        "计算机、通信和其他电子设备制造业",
        "软件和信息技术服务业", 
        "互联网和相关服务",
        "电信、广播电视和卫星传输服务",
        "广播、电视、电影和影视录音制作业",
        "新闻和出版业",
        "文化艺术业",
        "科技推广和应用服务业",
        "专业技术服务业",
        "研究和试验发展",
        "仪器仪表制造业",
        "电气机械和器材制造业",
        "专用设备制造业",
        "铁路、船舶、航空航天和其他运输设备制造业",
        "印刷和记录媒介复制业",
        "机动车、电子产品和日用产品修理业"
    ]
    return industries

def match_industries_with_spot_data(spot_df, target_industries):
    """
    Match the target industries with data from stock_sector_spot
    """
    matched_industries = []
    
    # Check if spot_df has the right columns
    if '板块' not in spot_df.columns:
        print("Error: '板块' column not found in spot data")
        print(f"Available columns: {spot_df.columns.tolist()}")
        return matched_industries
    
    # Look for matches between target industries and spot data
    for target_industry in target_industries:
        # Check if the target industry exists in the spot data
        matched_rows = spot_df[spot_df['板块'].str.contains(target_industry, na=False, case=False)]
        
        if not matched_rows.empty:
            matched_industries.append({
                'target_name': target_industry,
                'matched_data': matched_rows
            })
            print(f"Found match for: {target_industry} ({len(matched_rows)} entries)")
        else:
            # Try partial matching
            for idx, row in spot_df.iterrows():
                if target_industry in row['板块'] or row['板块'] in target_industry:
                    matched_industries.append({
                        'target_name': target_industry,
                        'matched_data': pd.DataFrame([row])  # Wrap single row in DataFrame
                    })
                    print(f"Found partial match for: {target_industry} -> {row['板块']}")
                    break
    
    return matched_industries

def get_detailed_stocks_for_industries(matched_industries):
    """
    Get detailed stock information for each matched industry using stock_sector_detail
    """
    detailed_data = {}
    
    for item in matched_industries:
        target_name = item['target_name']
        matched_data = item['matched_data']
        
        # Get the label for the industry to use with stock_sector_detail
        if 'label' in matched_data.columns:
            label = matched_data.iloc[0]['label']  # Use the first match
            industry_name = matched_data.iloc[0]['板块']
        else:
            print(f"No label found for {target_name}, skipping...")
            continue
        
        print(f"Getting detailed stocks for {industry_name} (label: {label})")
        
        try:
            # Use the label to get detailed stock information
            stock_details = ak.stock_sector_detail(sector=label)
            
            if not stock_details.empty:
                detailed_data[target_name] = {
                    'industry_name': industry_name,
                    'label': label,
                    'stocks': stock_details
                }
                print(f"  Retrieved {len(stock_details)} stocks for {industry_name}")
            else:
                print(f"  No detailed stock data for {industry_name}")
                
        except Exception as e:
            print(f"  Error getting detailed stocks for {industry_name}: {e}")
    
    return detailed_data

def save_detailed_industry_stocks(detailed_data):
    """
    Save detailed stock information for all industries to a single CSV file with only symbol, code, and name fields
    """
    all_stocks = []
    
    for target_name, data in detailed_data.items():
        industry_name = data['industry_name']
        label = data['label']
        stocks_df = data['stocks']
        
        # Check if the required columns exist in the dataframe
        required_cols = ['symbol', 'code', 'name']
        available_cols = [col for col in required_cols if col in stocks_df.columns]
        
        if available_cols:
            # Select only the required columns that exist
            selected_stocks = stocks_df[available_cols].copy()
            # Add the industry information as a column
            selected_stocks['industry'] = target_name
            all_stocks.append(selected_stocks)
            print(f"Added {len(selected_stocks)} stocks for '{target_name}' ({industry_name})")
        else:
            print(f"No required columns found for '{target_name}'. Available columns: {stocks_df.columns.tolist()}")
    
    if all_stocks:
        # Combine all stocks from different industries
        combined_df = pd.concat(all_stocks, ignore_index=True)
        
        # Save to a single CSV file
        output_filename = "tmt_industry_stocks.csv"
        
        # Remove the file if it already exists to ensure clean output
        if os.path.exists(output_filename):
            os.remove(output_filename)
        
        combined_df.to_csv(output_filename, index=False, encoding='utf-8-sig')
        print(f"Saved {len(combined_df)} total stocks from {len(detailed_data)} industries to {output_filename}")
        
        # Show summary
        industry_summary = combined_df['industry'].value_counts()
        print(f"\nSummary by industry:")
        for industry, count in industry_summary.items():
            print(f"  {industry}: {count} stocks")
        
        return combined_df
    else:
        print("No stock data to save")
        return pd.DataFrame()

def main():
    print("Fetching industry data using stock_sector_spot...")
    
    try:
        # Get industry data using stock_sector_spot
        spot_df = ak.stock_sector_spot(indicator="行业")
        print(f"Retrieved spot data with shape: {spot_df.shape}")
        print(f"Spot data columns: {spot_df.columns.tolist()}")
        print("Sample spot data:")
        print(spot_df.head())
        
        # Get the 16 target industries
        target_industries = get_industry_mapping()
        print(f"\nTarget industries to match: {len(target_industries)}")
        for i, ind in enumerate(target_industries, 1):
            print(f"  {i}. {ind}")
        
        # Match target industries with spot data
        matched_industries = match_industries_with_spot_data(spot_df, target_industries)
        print(f"\nMatched {len(matched_industries)} industries")
        
        if matched_industries:
            # Get detailed stock information for matched industries
            detailed_data = get_detailed_stocks_for_industries(matched_industries)
            
            if detailed_data:
                print(f"\nSuccessfully retrieved detailed data for {len(detailed_data)} industries")
                
                # Save to files
                all_stocks_df = save_detailed_industry_stocks(detailed_data)
                
                if not all_stocks_df.empty:
                    print(f"\nSummary by industry:")
                    industry_summary = all_stocks_df['industry'].value_counts()
                    for industry, count in industry_summary.items():
                        print(f"  {industry}: {count} stocks")
                
                print(f"\nAll detailed data saved to 'tmt_industry_stocks.csv'")
            else:
                print("No detailed stock data retrieved for matched industries")
        else:
            print("No industries matched between target list and spot data")
            
    except Exception as e:
        print(f"Error in main function: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()