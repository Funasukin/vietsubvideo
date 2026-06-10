"""Worker: vòng lặp lấy job pending từ hàng đợi, chạy pipeline, gọi uploaders,
báo tiến độ về Telegram qua bot.notifier.

TODO Phase 2: hàng đợi SQLite (data/jobs.sqlite) + poll loop.
TODO Phase 3: gọi uploaders theo job.platforms sau khi pipeline xong,
              ghi upload_result.json, lỗi upload không đánh fail job.
"""

if __name__ == "__main__":
    raise NotImplementedError("Worker — Phase 2")
