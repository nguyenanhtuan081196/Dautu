# Investing
1-Step: Lấy BCTC: crawl_bctc.py⁠ (PC)
2-Step: Lấy dữ liệu giá: fetch_data_local.py (PC)
3-Step: Lọc & Sắp xếp: advanced_screener.py
4-Step: Đánh giá AI: analyze_ai.py
4.5Step: Tính lợi nhuận: simulator.py
5-Step: Build: render_ui.py

#AI
1. Chạy top đầu mỗi ngành (khoảng 35 mã, không chia batch):
python ai_analysis.py --mode top
 
2. Chạy phần còn lại, chia 5 batch — lần lượt:
python ai_analysis.py --mode rest --total-batches 5 --batch 1
python ai_analysis.py --mode rest --total-batches 5 --batch 2
python ai_analysis.py --mode rest --total-batches 5 --batch 3
python ai_analysis.py --mode rest --total-batches 5 --batch 4
python ai_analysis.py --mode rest --total-batches 5 --batch 5
 
3. Chạy tất cả một lần (top trước, rồi hết phần còn lại nếu chỉ 1 batch):
python ai_analysis.py --mode all --total-batches 1
 
4. Chạy theo danh sách nhập tay qua biến môi trường (như cũ):
INPUT_SYMBOLS="ACB,FPT,MWG" python ai_analysis.py

#Workflow
1. Nếu bạn muốn chạy phân tích lại 34 mã Top đầu (mỗi ngành 5 mã)
• symbols: Để trống.
• mode: Chọn top.
• batch: Để 1 (không quan trọng).
• total_batches: Để 1 (không quan trọng).
• force: Tích chọn (như trong ảnh của bạn) - để ép chạy lại các mã vừa mới phân tích, không bị bỏ qua bởi cơ chế resume 7 ngày.
👉 Bấm Run workflow. 
2. Nếu bạn muốn chạy phần còn lại (69 mã) - Chia làm 5 lần chạy
 
Giả sử bạn muốn chạy lần 1 (khoảng 13-14 mã):
• symbols: Để trống.
• mode: Chọn rest.
• batch: Nhập 1.
• total_batches: Nhập 5.
• force: Tích hoặc không tích đều được (nếu tích thì nó sẽ chạy lại cả những mã trong danh sách "còn lại" dù mới chạy, nếu không tích nó sẽ tự động bỏ qua các mã mới chạy trong 7 ngày qua).
👉 Bấm Run workflow.
(Lần sau muốn chạy tiếp, bạn làm lại và đổi batch thành 2, 3, 4, 5). 
3. Nếu bạn muốn chạy đồng thời cả Top và Phần còn lại trong 1 lần bấm
• symbols: Để trống.
• mode: Chọn all.
• batch: 1
• total_batches: 1 (hoặc 5 nếu muốn chia nhỏ phần còn lại).
• force: Tích chọn.
👉 Bấm Run workflow. 
4. Nếu bạn chỉ muốn chạy một vài mã cụ thể (ví dụ: ACB, FPT)
• symbols: Nhập ACB, FPT (không cần dấu ngoặc kép).
• mode: Chọn top (lúc này mode không có tác dụng vì đã có symbols).
• batch / total_batches: Để 1.
• force: Tích chọn.
👉 Bấm Run workflow. 
