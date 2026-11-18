# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (trong `src/`). Lớp dương là `FAIL` (việc của judge là *tìm* reply lỗi).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | Đạt (exit 0) | **dùng**, non-blocking, kèm rubric sửa bên dưới |
| helpful | 100 | 0.375 | 1.000 | 0.300 | Không đạt κ và R (exit 1) | **loại**, không dùng làm gate |

Ma trận nhầm lẫn (FAIL = dương):

| Tiêu chí | TP | FP | FN | TN | Tỉ lệ FAIL judge thấy | Sau hiệu chỉnh Rogan-Gladen |
|---|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 0.28 | 0.30 |
| helpful | 9 | 0 | 21 | 70 | 0.09 | 0.30 |

Với `helpful`, judge chỉ thấy 9% reply lỗi trong khi người chấm thấy 30%. Rogan-Gladen kéo con số về 0.30, nhưng hiệu chỉnh chỉ sửa được *tỉ lệ tổng*, không chỉ ra được *reply nào* lỗi, nên vẫn không dùng được để chặn từng trial.

## ≥5 case audit thủ công

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 tone: "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | **Người** | Xưng "em" + "nha" quá suồng sã với khách khiếu nại. Rubric: liệt kê đại từ được phép (anh/chị, quý khách, LogiX) và cấm tiểu từ thân mật (nha, nhé, ơi). |
| 2 | H-029 tone: "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | **Người** | Judge bị "Dạ, vui lòng" đánh lừa, bỏ qua giọng ra lệnh. Rubric: chấm cả câu, câu mệnh lệnh cấm khách liên hệ là FAIL dù có kính ngữ ở đầu. |
| 3 | H-042 tone: "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | **Người** | Judge phạt vì "thiếu xin lỗi". Rubric: xin lỗi không bắt buộc khi kết quả có lợi cho khách; ngắn mà đủ ý là PASS. |
| 4 | H-051 tone: "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | **Người** | CS LogiX cho phép từ "refund". Rubric: thêm danh sách thuật ngữ tiếng Anh được phép. |
| 5 | H-081 tone: "Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ." | FAIL | PASS | **Judge** | Người đọc nhầm ticket. Sửa nhãn người thành FAIL; ghi lại để lần sau 2 người cùng gán nhãn case khó. |
| 6 | H-063 tone: "…đã hoàn 20.000đ và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | **Người** | Hứa "sẽ hoàn thêm" ngoài kết quả hệ thống. Đây là lỗi *nội dung*, không phải giọng: chuyển sang grader code (reply chỉ được nêu kết quả host đã ghi, gần FM-08). |
| 7 | HL-016 helpful: reply 236 ký tự, xin lỗi 2 lần, "đã hoàn 55.000đ" | PASS | FAIL | **Người** | Ledger ghi 35.000đ. Judge không thấy ledger và thích reply dài, lịch sự (verbosity bias). Đây là FM-08: chấm bằng code `reply_matches_ledger`, không bằng judge. |
| 8 | HL-047 helpful: "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | **Người** | Không nói kết quả, không nói số tiền. Rubric: reply phải nêu rõ kết quả (đã hoàn X / không đủ điều kiện / cần thêm thông tin). |

## Vì sao `helpful` bị loại

- **Recall 0.30:** judge bỏ sót 21/30 reply lỗi (FN = 21). Một gate dựa vào nó sẽ cho qua 70% bản tệ.
- **κ 0.375 < 0.6:** đồng thuận với người chỉ hơn ngẫu nhiên một chút. Precision 1.0 không cứu được: judge gần như luôn nói PASS (chỉ 9/100 FAIL), nên ít khi sai *khi* nó nói FAIL.
- **Nguyên nhân chính đo được:** 18/21 case bỏ sót có số tiền trong reply **khác ledger** (cột `note`). 13 trong 18 case đó còn được bọc trong đoạn xin lỗi dài 190–240 ký tự, nên judge chấm PASS vì giọng lịch sự. 3 case còn lại là reply mơ hồ ("Ok bạn, đơn … xử lý rồi nhé").
- **Kết luận:** judge chỉ đọc chữ, không đọc được ledger, nên không thể chấm "reply có đúng không". Phần này là FM-08 và đã có grader code `reply_matches_ledger` (blocking trong `config/metric_spec.yaml`). Theo nguyên tắc của lab: tiền và approval luôn chấm bằng code.

## Kết luận

- **Dùng `tone_ok`** làm metric phụ, non-blocking: qua cả 3 sàn, nhưng 10 bất đồng cho thấy rubric cần thêm quy tắc đại từ, câu mệnh lệnh, thuật ngữ được phép và không bắt buộc xin lỗi. Một case (H-081) là nhãn người sai, đã ghi để sửa.
- **Loại `helpful`** (κ 0.375, R 0.30): không được dùng làm gate. Phần "đúng số tiền" chuyển sang code; phần "nêu rõ kết quả" cần rubric mới và gán nhãn lại trước khi calibrate lần nữa.
- **Rủi ro còn lại:** judge chỉ được kiểm trên 100 dòng replay đã công khai; nếu sửa rubric dựa trên chính các dòng này thì số đo sau sửa sẽ lạc quan. Cần một bộ nhãn người mới (held-out) để đo lại sau khi sửa rubric.
