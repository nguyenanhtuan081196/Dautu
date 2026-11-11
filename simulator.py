import pandas as pd
import math
from app.database.job_io import database, load_all_daily_history, save_simulation

def get_historical_return_rate_with_details(symbol, history_bars):
    """
    Đọc file lịch sử giá của một mã, lọc đúng 5 năm, gom nhóm theo Quý, 
    tính giá trung bình (mean) và trả về cả CAGR lẫn thông tin chi tiết các quý.
    """
    try:
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
        
        start_price = float(start_row['close'])
        end_price = float(end_row['close'])
        
        # Giá không hợp lệ (0, âm, NaN/Inf) không thể dùng để tính CAGR.
        if not (math.isfinite(start_price) and math.isfinite(end_price)):
            return None
        if start_price <= 0 or end_price <= 0:
            return None
        
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
        if not math.isfinite(cagr):
            return None
        
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

def run_complex_backtest_simulation():
    """Calculate five-year quarterly-mean CAGR from MongoDB D1 history and save results to Atlas."""
    db = database()
    history_by_symbol = load_all_daily_history(db)
    calculated = 0
    for symbol, history_bars in sorted(history_by_symbol.items()):
        result = get_historical_return_rate_with_details(symbol, history_bars)
        if result is None:
            continue
        save_simulation(db, symbol, {"annual_rate_percent": result["annual_rate_percent"], **result})
        calculated += 1
        print(f"[{symbol}] Quý đầu ({result['start_quarter']}): {result['start_price_mean']} | Quý cuối ({result['end_quarter']}): {result['end_price_mean']}")

    return {
        "status": "success",
        "total_symbols_calculated": calculated
    }

if __name__ == "__main__":
    run_complex_backtest_simulation()
