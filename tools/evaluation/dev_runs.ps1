# The development-split runs for Phase 8, one after another. Each run resumes if it is interrupted.
# From the repository root:  powershell -File tools\evaluation\dev_runs.ps1
$py = ".\.venv\Scripts\python.exe"
$runs = @(
    @("--variant", "baseline", "--pass", "1"),
    @("--variant", "baseline", "--pass", "2"),
    @("--variant", "forced_ocr", "--pass", "1", "--conditions", "clean_pdf"),
    @("--variant", "forced_ocr", "--pass", "2", "--conditions", "clean_pdf"),
    @("--variant", "text_and_image", "--pass", "1", "--conditions", "scan_heavy,phone_photo"),
    @("--variant", "text_and_image", "--pass", "2", "--conditions", "scan_heavy,phone_photo"),
    @("--variant", "thinking", "--pass", "1", "--conditions", "clean_pdf")
)
foreach ($run in $runs) {
    Write-Output ("=== " + ($run -join " ") + "  " + (Get-Date -Format s))
    & $py -m tools.evaluation.run @run
}
Write-Output ("=== all done " + (Get-Date -Format s))
