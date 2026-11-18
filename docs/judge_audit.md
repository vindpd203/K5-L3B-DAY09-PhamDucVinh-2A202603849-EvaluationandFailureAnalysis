# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5`
Nhãn nhị phân PASS/FAIL, **FAIL là lớp dương** (nhiệm vụ của judge là TÌM lỗi). Nguồn: replay 100 reply/CSV, so judge với nhãn người.

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt (confusion: tp=24, fp=4, fn=6, tn=66) | **dùng** (sau khi vá rubric bên dưới) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | FAIL — R=0.3 chỉ bắt 9/30 lỗi, κ=0.375 (confusion: tp=9, fp=0, fn=21, tn=70) | **loại** |

Rogan–Gladen hiệu chỉnh tỷ lệ lỗi thật:
- tone: observed 0.28 → corrected **0.30** (sensitivity 0.8, specificity 0.943) — sai lệch nhỏ.
- helpful: observed 0.09 → corrected **0.30** — số lỗi thật gấp hơn 3 lần số judge báo: judge bỏ sót 2/3 reply lỗi.

## ≥5 case audit thủ công

### tone (10 bất đồng: 7 judge PASS khi human FAIL, 3 judge FAIL khi human PASS)

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | Người | xưng "em…nha" suồng sã với khách khiếu nại; judge coi là thân thiện → thêm rule cấm đại xưng "em/bạn" |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…" | PASS | FAIL | Người | "bạn ơi" với khách lớn tuổi → rubric bắt buộc "anh/chị" trong ngữ cảnh khiếu nại |
| 3 | H-029 "…Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người | giọng ra lệnh; judge chỉ thấy "Dạ, vui lòng" → thêm rule cấm chặn khách liên hệ |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ…" | FAIL | PASS | Người | ngắn nhưng đủ ý; judge phạt vì "thiếu xin lỗi" → bỏ điều kiện bắt buộc có câu xin lỗi |
| 5 | H-051 "…LogiX đã refund 90.000đ…" | FAIL | PASS | Người | từ "refund" được CS LogiX cho phép → bỏ rule phạt tiếng Anh |
| 6 | H-063 "…và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | Người | hứa hoàn thêm ngoài kết quả hệ thống → thêm rule cấm hứa ngoài dữ liệu |
| 7 | H-070 "…hoàn 90.000đ cho đơn O-909 ạ 😂😂" | PASS | FAIL | Người | emoji không phù hợp ngữ cảnh khiếu nại → cấm emoji |
| 8 | H-081 "đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành" | FAIL | PASS | **Judge** | nhãn người sai (đọc nhầm ticket) → sửa nhãn H-081 thành FAIL, rà lại batch nhãn cùng kiểu |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn 40.000đ…" | FAIL | PASS | Người | lặp "Dạ" là lỗi gõ → chỉ phạt lặp từ tạo giọng mỉa mai |
| 10 | H-094 "Da, LogiX da hoan 40.000đ cho don O-341, xin loi…" | PASS | FAIL | Người | dịch máy mất dấu tiếng Việt → thêm rule: mất dấu ≥1 câu → FAIL |

### helpful (21 bất đồng, 21/21 đều judge PASS khi human FAIL)

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 11 | HL-015 "hoàn 55.000đ cho O-112" (ledger 40.000đ) | PASS | FAIL | Người | sai tiền so ledger — judge replay không nhìn thấy ledger |
| 12 | HL-020 "hoàn 90.000đ cho O-303" (ledger 120.000đ) | PASS | FAIL | Người | cùng nhóm "sai tiền" (18/21 bất đồng) |
| 13 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | Người | sai xưng hô + không nêu kết quả cụ thể |
| 14 | HL-058 "hoàn 40.000đ cho O-107" (ledger 25.000đ) | PASS | FAIL | Người | sai tiền — lỗi capability, không phải lỗi văn bản |
| 15 | HL-097 "Ok bạn, đơn O-202 xử lý rồi nhé." | PASS | FAIL | Người | như HL-047; cả HL-091 cùng nhóm |

## Kết luận
- **`tone_ok` đạt sàn (κ 0.757, P 0.857, R 0.8) → dùng được** làm gate phụ về giọng điệu, nhưng phải vá rubric: đại xưng ("em/bạn"), emoji, hứa hẹn ngoài hệ thống, mất dấu tiếng Việt; bỏ phạt "thiếu xin lỗi" và từ "refund"; sửa nhãn H-081 (lỗi người gán nhãn, không phải judge).
- **`helpful` bị loại vì recall 0.3**: 21/21 bất đồng đều là judge PASS trong khi reply sai số tiền so ledger. Judge replay không có quyền truy cập ledger nên về nguyên tắc **không thể** phát hiện lớp lỗi này — không phải lỗi rubric mà là lỗi phạm vi. Gate dựa trên judge này sẽ cho qua 2/3 lỗi thật dù precision của nó là 1.0.
- Hệ quả: sai tiền (FM-04/05/07/08) và approval (FM-02/09) luôn chấm bằng code trên ledger/trace; judge chỉ giữ cho lớp lỗi văn bản (tone). Số tiền phải chấm bằng metric `reply_ledger_match` (thêm ở M3).
- Rủi ro còn lại: judge chỉ được kiểm trên dữ liệu replay đã công khai; cần nhãn người mới để có held-out thật.
