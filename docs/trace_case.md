# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case 1 — seeded_regression C-002@11 (FM-03 ticket_trust)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run `E-seeded_regression-20261117-eb48` (report `reports/eval_seeded_regression.json`) |
| Triệu chứng | Lab 8 grader FAIL: `status resolved != denied`. Trace event 6: reply "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." trong khi label yêu cầu denied, ledger ghi `refund_vnd=20000, refund_count=1` (label: 0/0) |
| Bước sai đầu tiên | **Event 3 — `model_override {"delay_days": 5}`**: agent thay `delay_days` trong DB bằng số "5 ngày" đọc từ ticket |
| Vì sao là bước *đầu tiên* | Event 1 (handoff) và event 2 (investigator lookup_order) đều đúng: DB cho thấy O-202 với delay_days thật nhỏ hơn ngưỡng 3 của SHIP-LATE-03. Chỉ sau khi event 3 ghi đè fact DB, event 4 (quote) mới tính ra `SHIP-LATE-03 = 20000, entitled` và dẫn tới hoàn tiền sai ở event 5–6 |
| Failure mode | **FM-03** (ticket_trust — tin ticket hơn DB); hệ quả là FM-08 (reply hứa 20.000đ trong khi lẽ ra không được hoàn gì) |
| Đối chứng | `fixed C-002@11`: không có event `model_override`; event 3 là `quote {amount_vnd: 0, reason: no_entitlement}` → event 4 reply từ chối đúng chính sách, ledger 0/0, grader PASS |
| Regression test | `tests/test_lab9_graders.py::test_wrong_amount_in_ledger` (grader `RefundAmountCorrect`: ledger 20000 ≠ label 0) và `test_override_event_breaks_db_fact` (grader `DbFactKept` bắt event `model_override`). Trên report: `refund_amount_correct` = 0.8571 và `db_fact_kept` = 0.9286 trên `seeded_regression`, cả hai = 1.0 trên `fixed`; gate chặn ở exit 1 |
| Chưa chắc chắn | Trace không chứng minh được *vì sao* seed 11 kích nhánh ticket_trust (chỉ thấy hệ quả);.MockLLM replay cố định nên không đo được hành vi trên ngôn ngữ tự nhiên thật |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
