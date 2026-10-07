$ErrorActionPreference = "Stop"

$BaseUrl = if ($env:BASE_URL) { $env:BASE_URL } else { "http://localhost:8000" }

$response = Invoke-RestMethod `
  -Uri "$BaseUrl/api/files/" `
  -Method Post `
  -Form @{ file = Get-Item "sample_data/demo.kml" }

$response | ConvertTo-Json -Depth 10

$fileId = $response.id

Write-Host "`nFile status:"
Invoke-RestMethod "$BaseUrl/api/files/$fileId/" | ConvertTo-Json -Depth 10

Write-Host "`nMeasurements:"
Invoke-RestMethod "$BaseUrl/api/files/$fileId/measurements/" | ConvertTo-Json -Depth 10
