# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `<shape> <claim>@<seed>`, run ID trong report |
| Triệu chứng | Grader nào fail; reply nói gì so với ledger ghi gì |
| Bước sai đầu tiên | Số thứ tự event + kind + trích payload (≤1 dòng) |
| Vì sao là bước *đầu tiên* | Các bước trước đó đúng ra sao (dẫn số event) |
| Failure mode | Mã FM-xx trong `docs/failure_taxonomy.md` |
| Đối chứng | Cùng claim@seed trên shape `fixed`: bước đó khác thế nào |
| Regression test | Tên test + grader/assert nào bắt được; đã thấy fail trên variant lỗi và pass trên `fixed` chưa |
| Chưa chắc chắn | Điều trace không chứng minh được |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.

---

## Case đã làm: `seeded_regression C-008@11` (FM-08 misreport)

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-008 --seed 11
python -m lab9.trace_case --shape fixed --claim C-008 --seed 11   # đối chứng
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-008@11`, run ID `E-seeded_regression-20261118-fe14` (`reports/eval_seeded_regression.json`, dòng `E-008` seed 11) |
| Triệu chứng | Grader Lab 8 **PASS** (`ok`), `pass_rate` = True, `refund_amount_correct` = True. Chỉ `reply_matches_ledger` = **False**: reply nói "Dạ, LogiX đã hoàn **35.000đ** cho đơn O-808." trong khi ledger ghi **20.000đ** (đúng nhãn: approval A-008 chỉ duyệt 20.000đ). |
| Bước sai đầu tiên | Event 6 `reply_amount` `{"said": 35000, "committed": 20000}`: agent quyết định nói số nó đề xuất, không phải số host ghi; event 7 `reply` "đã hoàn 35.000đ" là hệ quả. (Trên `variant_agent.py` gốc không có `host_outcome`/`reply_amount`: bước sai là event 5 `reply`.) |
| Vì sao là bước *đầu tiên* | Ev1 `handoff` chỉ có field trong allowlist, `facts={}`. Ev2 `investigator` đọc đúng đơn O-808 từ DB (trễ 4 ngày, phí ship 35.000). Ev3 `quote` 35.000 theo `SHIP-LATE-03`, đúng policy hiện hành. Ev4 `refund_history` refunded 0, nên công tắc `pre_deducted` không trừ gì, đề xuất vẫn 35.000 (đề xuất đầy đủ là đúng hợp đồng). Ev5 `host_outcome` `ok: true, proposed_vnd: 35000, committed_vnd: 20000`: host lấy min(đề xuất 35.000, approval A-008 duyệt 20.000) = 20.000. Sai bắt đầu ở ev6: agent chọn báo số **nó đề xuất** thay vì số **host đã ghi**. |
| Failure mode | **FM-08** misreport (do công tắc `pre_deducted`: "FM-05 / FM-08 báo số nó tự tính", `variant_agent.py`). |
| Đối chứng | `fixed C-008@11`: cùng handoff/investigator/quote (không có `refund_history`), `host_outcome` cũng committed 20.000, nhưng `reply_amount` `{"said": 20000, "committed": 20000}` và `reply` "đã hoàn **20.000đ**", khớp ledger. Khác biệt duy nhất là số tiền trong reply. |
| Regression test | `src/tests/test_lab9_trace_case.py`: `test_lab9_trace_case_misreport_caught_on_seeded_regression` (assert grader Lab 8 PASS nhưng `ReplyMatchesLedger` = False, lý do chứa 35000) và `test_lab9_trace_case_reply_matches_ledger_on_fixed` (assert = True). Đã chạy: **fail đúng trên variant lỗi, pass trên `fixed`**; test chạy lại shape thật trên store tạm và không phụ thuộc event `host_outcome` (đã thử cả hai bản). Metric `reply_matches_ledger` (blocking, min 0.95) có trong `config/metric_spec.yaml`. |
| Chưa chắc chắn | Trace không ghi *vì sao* agent chọn số đề xuất cho reply (code chọn `said = proposal`); ta chỉ thấy hệ quả. Grader đọc số tiền bằng regex `…đ`/`VND`: reply viết số bằng chữ ("hai mươi nghìn") sẽ lọt. Với MockLLM câu chữ cố định nên regex đủ; với LLM thật cần chuẩn hóa số hoặc bắt reply nêu số theo template. |
