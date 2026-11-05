import os
import json
import pandas as pd
import datetime
import subprocess

def get_historical_return_rate_with_details(symbol, history_dir="history"):
    """
    Đọc file lịch sử giá của một mã, lọc đúng 5 năm, gom nhóm theo Quý, 
    tính giá trung bình (mean) và trả về cả CAGR lẫn thông tin chi tiết các quý.
    """
    file_path = os.path.join(history_dir, f"{symbol}.json")
    if not os.path.exists(file_path):
        return None
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        history_bars = data.get("history_d1", [])
        if len(history_bars) < 30:
            return None
            
        df = pd.DataFrame(history_bars)
        df['date'] = pd.to_datetime(df['time'])
        df = df.sort_values('date')
        
        # 1. Lọc khung 5 năm thực tế gần nhất
        max_date = df['date'].max()
        cutoff_date = max_date - pd.DateOffset(years=5)
        
        df_5years = df.loc[df['date'] >= cutoff_date].copy()
        if len(df_5years) < 30:
            return None
            
        # 2. Gom nhóm theo Quý
        df_5years.loc[:, 'year_quarter'] = df_5years['date'].dt.to_period('Q')
        df_quarterly = df_5years.groupby('year_quarter').agg({
            'close': 'mean',
            'date': 'first'
        }).reset_index()
        
        if len(df_quarterly) < 2:
            return None
            
        start_row = df_quarterly.iloc[0]
        end_row = df_quarterly.iloc[-1]
        
        start_price = start_row['close']
        end_price = end_row['close']
        
        start_date = start_row['date']
        end_date = end_row['date']
        
        start_q = str(start_row['year_quarter'])
        end_q = str(end_row['year_quarter'])
        
        # 3. Tính số năm và CAGR
        days = (end_date - start_date).days
        if days < 30:
            return None
            
        years = days / 365.25
        if years <= 0:
            return None
            
        cagr = (end_price / start_price) ** (1 / years) - 1
        cagr = max(-0.5, min(cagr, 1.0))
        
        # Trả về kết quả kèm chi tiết giá trung bình quý
        return {
            "annual_rate_percent": round(cagr * 100, 2),
            "start_quarter": start_q,
            "start_price_mean": round(start_price, 2),
            "end_quarter": end_q,
            "end_price_mean": round(end_price, 2)
        }
        
    except Exception as e:
        print(f"⚠️ Lỗi xử lý chi tiết cho {symbol}: {e}")
        return None

def run_complex_backtest_simulation(history_dir="history", 
                                    rates_json="symbol_sim_rates.json", 
                                    details_json="quarterly_mean_details.json"):
    """
    Quét toàn bộ thư mục history/ để tính toán, đồng thời xuất ra:
    1. file symbol_sim_rates.json (cho hệ thống mô phỏng cũ)
    2. file quarterly_mean_details.json (lưu riêng chi tiết giá trung bình quý 5 năm)
    """
    rates_map = {}
    details_map = {}
    
    if os.path.exists(history_dir):
        for filename in sorted(os.listdir(history_dir)):
            if filename.endswith(".json"):
                symbol = filename.replace(".json", "")
                result = get_historical_return_rate_with_details(symbol, history_dir)
                
                if result is not None:
                    # Dữ liệu cho file sim rates tiêu chuẩn
                    rates_map[symbol] = {
                        "annual_rate_percent": result["annual_rate_percent"]
                    }
                    # Dữ liệu chi tiết cho file riêng biệt
                    details_map[symbol] = result
                    print(f"[{symbol}] Quý đầu ({result['start_quarter']}): {result['start_price_mean']} | Quý cuối ({result['end_quarter']}): {result['end_price_mean']}")
                    
    # 1. Ghi file rates chuẩn
    try:
        with open(rates_json, "w", encoding="utf-8") as f:
            json.dump(rates_map, f, ensure_ascii=False, indent=4)
        print(f"✅ Đã lưu file {rates_json} thành công!")
    except Exception as e:
        print(f"⚠️ Lỗi ghi {rates_json}: {e}")

    # 2. Ghi file chi tiết giá trung bình quý riêng
    try:
        with open(details_json, "w", encoding="utf-8") as f:
            json.dump(details_map, f, ensure_ascii=False, indent=4)
        print(f"✅ Đã lưu file chi tiết riêng {details_json} với {len(details_map)} mã thành công!")
    except Exception as e:
        print(f"⚠️ Lỗi ghi {details_json}: {e}")

    return {
        "status": "success",
        "total_symbols_calculated": len(rates_map)
    }

if __name__ == "__main__":
    run_complex_backtest_simulation()
