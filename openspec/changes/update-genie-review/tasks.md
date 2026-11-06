## 1. Build
- [x] 1.1 _genie_family_gate (under 13, the genie switch, quiet hours) on create and every request; teen limit in _count_call; TEEN_SAFETY and safety checks for teens
- [x] 1.2 _genie_failed: partial work kept and remembered, or a retryable error
- [x] 1.3 Snapshots: reuse an identical latest one; GENIE_SNAPSHOT_BYTES budget
- [x] 1.4 No empty project after a refused first request
- [x] 1.5 Tests: tests/test_genie_review.py; test_genie.py's undo test now makes changing requests
- [x] 1.6 Real repositories (0.1.110): edit_file, find_files, numbered read_file parts, regex search; GitHub import
      (paste a link); 600 files / 6 MB per project, deeper folders, [ ] ( ) , = ~ in names; tests/test_genie_repo_tools.py
