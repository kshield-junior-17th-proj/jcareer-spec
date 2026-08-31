[CmdletBinding()]
param(
    [switch] $CheckOnly
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$results = [System.Collections.Generic.List[object]]::new()

function Add-Check {
    param(
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [bool] $Passed,
        [Parameter(Mandatory)] [string] $Detail
    )

    $results.Add([pscustomobject]@{
        check  = $Name
        status = if ($Passed) { 'PASS' } else { 'FAIL' }
        detail = $Detail
    })
}

$required = @(
    'JCAREER_ASIS_SYSTEM_SPEC.md',
    'index.html',
    'architecture.html',
    'JCAREER_ASIS_SYSTEM_SPEC.pdf',
    'JCAREER_ASIS_FLOW.drawio',
    'JCAREER_ASIS_FLOW.drawio.png'
)
$missing = @($required | Where-Object { -not (Test-Path -LiteralPath (Join-Path $root $_) -PathType Leaf) })
Add-Check 'required_files' ($missing.Count -eq 0) $(if ($missing.Count) { $missing -join ', ' } else { "all $($required.Count) deliverables present" })

$spec = Get-Content -Raw -Encoding UTF8 (Join-Path $root 'JCAREER_ASIS_SYSTEM_SPEC.md')
$index = Get-Content -Raw -Encoding UTF8 (Join-Path $root 'index.html')
$architecture = Get-Content -Raw -Encoding UTF8 (Join-Path $root 'architecture.html')
$publishedText = $spec + "`n" + $index + "`n" + $architecture

$readme = Get-Content -Raw -Encoding UTF8 (Join-Path $root 'README.md')
$readmeOkay = $readme.Contains('index.html') -and
    $readme.Contains('architecture.html') -and
    $readme.Contains('validation-report.json') -and
    $readme.Contains('JCAREER_ASIS_SYSTEM_SPEC.pdf') -and
    $readme.Contains('JCAREER_ASIS_FLOW.drawio') -and
    $readme.Contains('JCAREER_ASIS_2AZ.md') -and
    $readme.Contains('JCAREER_ASIS_2AZ.drawio') -and
    $readme.Contains('보조 상세 draw.io 원본') -and
    $readme.Contains('60개 셀·14개 연결') -and
    $readme.Contains('구판(legacy)')
Add-Check 'readme_current_deliverables' $readmeOkay $(if ($readmeOkay) { 'public 60/14 diagram linked; separate detailed and legacy diagrams marked' } else { 'README routing is incomplete' })

$flowGuide = Get-Content -Raw -Encoding UTF8 (Join-Path $root 'JCAREER_ASIS_FLOW.md')
$drawioText = Get-Content -Raw -Encoding UTF8 (Join-Path $root 'JCAREER_ASIS_FLOW.drawio')
$specGuideRegion = [regex]::Match($spec, '(?s)## 0\..*?## 1\.').Value
$flowGuideRegion = [regex]::Match($flowGuide, '(?s)## 0\..*?## 1\.').Value
$specGuideHangul = [regex]::Matches($specGuideRegion, '[\uAC00-\uD7A3]').Count
$flowGuideHangul = [regex]::Matches($flowGuideRegion, '[\uAC00-\uD7A3]').Count
$drawioHangul = [regex]::Matches($drawioText, '[\uAC00-\uD7A3]').Count
$plainLanguageOkay = $spec.Contains('### 0.1 ') -and
    $spec.Contains('### 0.2 ') -and
    $spec.Contains('### 0.4 ') -and
    $specGuideHangul -ge 900 -and
    $flowGuide.Contains('## 0.') -and
    $flowGuideHangul -ge 40 -and
    $drawioText.Contains('v3.15') -and
    $drawioHangul -ge 180 -and
    -not $drawioText.Contains('web · api') -and
    -not $drawioText.Contains('2개 AZ') -and
    -not $drawioText.Contains('Terraform 생성 예정') -and
    $index.Contains('id="executive-title"') -and
    $index.Contains('data-status="MODELLED"')
Add-Check 'plain_language_reader_guide' $plainLanguageOkay "spec guide Hangul $specGuideHangul; flow guide Hangul $flowGuideHangul; drawio Hangul $drawioHangul; reader-first status labels checked"

$renderTemps = @(Get-ChildItem -LiteralPath $root -Force | Where-Object {
    ($_.PSIsContainer -and $_.Name -match '^\.edge-(?:diagram|pdf)-profile') -or
    (-not $_.PSIsContainer -and (
        $_.Name -in @('.diagram-overlay.html', '.drawio-render.html', 'JCAREER_ASIS_FLOW.base.png', 'JCAREER_ASIS_FLOW.review.png') -or
        $_.Name -match '^JCAREER_ASIS_FLOW\.v\d+.*\.png$' -or
        $_.Name -match '^JCAREER_ASIS_SYSTEM_SPEC\.(?:final|next\d*|v\d+)\.pdf$'
    ))
})
Add-Check 'render_temp_artifacts_absent' ($renderTemps.Count -eq 0) $(if ($renderTemps.Count) { ($renderTemps.Name -join ', ') } else { '0 browser profiles / intermediate renders' })

$requiredTerms = @(
    'Windows 100', 'macOS 80', 'managed create 110',
    'mock provider', 'PLANNED_UNIMPLEMENTED', '0 resources', 'fail-closed',
    'approved snapshot ingestion', 'redacted snapshot', 'per-user auth',
    'tenant isolation', 'audit logs', 'client AWS', 'ISO XLSX',
    'LOCAL_SYNTHETIC_IMPLEMENTED', 'IMPLEMENTED_GUARDED_NOT_ACTIVE',
    'BRANCH_PROTOTYPE_UNDEPLOYED', 'REPO_REPORTED_PREVIEW_DEPLOYED',
    'PEER_OBSERVED_PREVIEW_AVAILABLE', 'REQ-PC-01', 'DELETE_COMPLETE',
    'deterministic-70-20-10-v1',
    'score_effect=NONE', 'gateway source/container hash',
    'EXPERIMENT_UNWIRED_NOT_APPROVED', 'runtime_wired=false',
    'TRAINED_SYNTHETIC_NOT_APPROVED', 'MEASURED_SYNTHETIC_NOT_ASSESSED',
    'SCENARIO_USE_UNVERIFIED', 'app.slack.com', 'TRAINED_PENDING_HUMAN_REVIEW'
)
$missingTerms = @($requiredTerms | Where-Object { -not $spec.Contains($_) -or -not $index.Contains($_) })
$architectureTerms = @(
    'Windows 100', 'macOS 80', '2-AZ', '계획 110개',
    'MLOps 학습·평가', 'AWS 비접속', '고객사 AWS에 직접 연결하지 않는다',
    '승인된 비식별본', '승인 전 리소스 0개', 'TRACE·JC-RECEIPT',
    '업무망·Slack', '외부 업무도구', '기본 비활성', '시나리오 사용 미확인', 'feature-only', '추천 런타임 배선'
)
$missingArchitectureTerms = @($architectureTerms | Where-Object { -not $architecture.Contains($_) })
$scopeTermsOkay = $missingTerms.Count -eq 0 -and $missingArchitectureTerms.Count -eq 0
$scopeTermDetail = if ($scopeTermsOkay) {
    "all $($requiredTerms.Count) boundary terms in spec+index; architecture core $($architectureTerms.Count)"
} else {
    "spec/index: $($missingTerms -join ', '); architecture: $($missingArchitectureTerms -join ', ')"
}
Add-Check 'required_scope_terms' $scopeTermsOkay $scopeTermDetail

$prohibitedClaims = [ordered]@{
    live_word             = '(?i)(?<!aria-)\blive\b'
    production_in_service = '(?i)(?:AWS|service|system)\s*(?:is\s*)?(?:live|in production)'
}
$claimHits = [System.Collections.Generic.List[string]]::new()
foreach ($entry in $prohibitedClaims.GetEnumerator()) {
    if ($publishedText -match $entry.Value) { $claimHits.Add($entry.Key) }
}
Add-Check 'prohibited_live_claims' ($claimHits.Count -eq 0) $(if ($claimHits.Count) { $claimHits -join ', ' } else { '0 live / in-production claims' })

$tfFiles = @(Get-ChildItem -LiteralPath $root -Filter '*.tf' -File -Recurse)
$tfText = ($tfFiles | ForEach-Object { Get-Content -Raw -Encoding UTF8 $_.FullName }) -join "`n"
$excludedInTerraform = @('TRACE', 'JC-RECEIPT') | Where-Object { $tfText -match [regex]::Escape($_) }
Add-Check 'excluded_ai_services' ($excludedInTerraform.Count -eq 0) $(if ($excludedInTerraform.Count) { $excludedInTerraform -join ', ' } else { 'no excluded AI service in Terraform' })
Add-Check 'terraform_file_count' ($tfFiles.Count -eq 38) "$($tfFiles.Count) .tf files"
$resourceBlocks = [regex]::Matches($tfText, '(?m)^\s*resource\s+"[^"\r\n]+"\s+"[^"\r\n]+"\s*\{').Count
$moduleBlocks = [regex]::Matches($tfText, '(?m)^\s*module\s+"[^"\r\n]+"\s*\{').Count
$dataBlocks = [regex]::Matches($tfText, '(?m)^\s*data\s+"[^"\r\n]+"\s+"[^"\r\n]+"\s*\{').Count
$topologyOkay = $resourceBlocks -eq 73 -and $moduleBlocks -eq 6 -and $dataBlocks -eq 6
Add-Check 'terraform_topology_blocks' $topologyOkay "resource $resourceBlocks, module $moduleBlocks, data $dataBlocks"

$repositoryRuntimeRoot = [System.IO.Path]::GetFullPath((Join-Path $root '../../src/runtime'))
$legacySiblingRuntimeRoot = [System.IO.Path]::GetFullPath((Join-Path $root '../../../asis-runtime-mvp/src/runtime'))
$runtimeRoot = if (Test-Path -LiteralPath $repositoryRuntimeRoot -PathType Container) {
    $repositoryRuntimeRoot
} else {
    $legacySiblingRuntimeRoot
}
$runtimeSourceAvailable = Test-Path -LiteralPath $runtimeRoot -PathType Container
$apiRoutes = @()
$coreApiRoutes = @()
$guardedApiRoutes = @()
$agentRoutes = @()
$gatewayRoutes = @()
$webRoutes = @()
$runtimeRunnerChecks = 0
$runnerIncludesMlops = $false
if ($runtimeSourceAvailable) {
    $coreApiRoutes = @(Select-String -LiteralPath (Join-Path $runtimeRoot 'api/app/main.py') -Pattern '^@app\.(get|post|put|patch|delete)\(')
    $guardedApiRoutes = @(
        Select-String -LiteralPath (Join-Path $runtimeRoot 'api/app/trace_receipts.py') -Pattern '^@router\.(get|post|put|patch|delete)\('
        Select-String -LiteralPath (Join-Path $runtimeRoot 'api/app/integrations/router.py') -Pattern '^@router\.(get|post|put|patch|delete)\('
    )
    $apiRoutes = @($coreApiRoutes) + @($guardedApiRoutes)
    $agentRoutes = @(Select-String -LiteralPath (Join-Path $runtimeRoot 'agent/app/main.py') -Pattern '^@app\.(get|post|put|patch|delete)\(')
    $gatewayRoutes = @(Select-String -LiteralPath (Join-Path $runtimeRoot 'llm_gateway/app/main.py') -Pattern '^@app\.(get|post|put|patch|delete)\(')
    $webRoutes = @(Select-String -LiteralPath (Join-Path $runtimeRoot 'web/src/App.jsx') -Pattern '(?:<Route\s+path=|\{\s*path:\s*")')
    $runtimeRunnerPath = [System.IO.Path]::GetFullPath((Join-Path $runtimeRoot '../../tests/run_all_tests.sh'))
    if (Test-Path -LiteralPath $runtimeRunnerPath -PathType Leaf) {
        $runtimeRunnerLines = @(Get-Content -LiteralPath $runtimeRunnerPath -Encoding UTF8)
        $runtimeRunnerChecks = @(
            $runtimeRunnerLines |
                Where-Object { $_ -match '^"\$PYTHON" -B (?:scripts/|-m unittest )' }
        ).Count
        $runnerText = $runtimeRunnerLines -join "`n"
        $runnerIncludesMlops = (
            $runnerText.Contains('scripts/check_serverless_mlops_static.py') -and
            $runnerText.Contains('tests.test_serverless_mlops_static')
        )
    }
}
$routeCountsOkay = $apiRoutes.Count -eq 39 -and
    $coreApiRoutes.Count -eq 30 -and
    $guardedApiRoutes.Count -eq 9 -and
    $agentRoutes.Count -eq 6 -and
    $gatewayRoutes.Count -eq 4 -and
    $runtimeRunnerChecks -eq 6 -and
    $runnerIncludesMlops -and
    $spec.Contains("현재 공개 릴리스 검사는 $runtimeRunnerChecks")
Add-Check 'runtime_api_route_counts' $routeCountsOkay $(if ($runtimeSourceAvailable) { "api $($apiRoutes.Count) = core $($coreApiRoutes.Count) + guarded $($guardedApiRoutes.Count), agent $($agentRoutes.Count), gateway $($gatewayRoutes.Count); runner declares $runtimeRunnerChecks checks including MLOps" } else { "runtime source missing at expected sibling path: $runtimeRoot" })
$screenContractOkay = $webRoutes.Count -eq 23 -and $spec.Contains('/candidate/home') -and $spec.Contains('/recruiter/overview') -and
    $spec.Contains('/candidate/trace') -and $spec.Contains('/recruiter/trace') -and $spec.Contains('/admin/trace') -and
    $spec.Contains('/privacy') -and $spec.Contains('/terms')
Add-Check 'runtime_screen_contract' $screenContractOkay $(if ($runtimeSourceAvailable) { "React routes $($webRoutes.Count) including redirect/wildcard; core home and three TRACE routes documented" } else { "runtime source missing at expected sibling path: $runtimeRoot" })

$stateFiles = @(Get-ChildItem -LiteralPath $root -File -Recurse | Where-Object { $_.Name -match '^terraform\.tfstate(?:\.|$)' })
Add-Check 'terraform_state_absent' ($stateFiles.Count -eq 0) "$($stateFiles.Count) state files"

$htmlFiles = @('index.html', 'architecture.html')
$brokenLinks = [System.Collections.Generic.List[string]]::new()
$brokenFragments = [System.Collections.Generic.List[string]]::new()
$duplicateIds = [System.Collections.Generic.List[string]]::new()
$htmlIdMap = @{}
foreach ($htmlName in $htmlFiles) {
    $html = Get-Content -Raw -Encoding UTF8 (Join-Path $root $htmlName)
    $htmlIdMap[$htmlName] = [System.Collections.Generic.HashSet[string]]::new(
        [string[]]@([regex]::Matches($html, '\bid="([^"]+)"') | ForEach-Object { $_.Groups[1].Value })
    )
}
foreach ($htmlName in $htmlFiles) {
    $htmlPath = Join-Path $root $htmlName
    $html = Get-Content -Raw -Encoding UTF8 $htmlPath
    $ids = @([regex]::Matches($html, '\bid="([^"]+)"') | ForEach-Object { $_.Groups[1].Value })
    $duplicateIds.AddRange([string[]]@($ids | Group-Object | Where-Object Count -gt 1 | ForEach-Object { "$htmlName#$($_.Name)" }))
    $hrefs = @([regex]::Matches($html, '\bhref="([^"]+)"') | ForEach-Object { $_.Groups[1].Value })
    foreach ($href in $hrefs) {
        if ($href -match '^(?:https?:|mailto:|data:)') { continue }
        $parts = $href -split '#', 2
        $target = $parts[0]
        $fragment = if ($parts.Count -eq 2) { [uri]::UnescapeDataString($parts[1]) } else { '' }
        if ($target -and -not (Test-Path -LiteralPath (Join-Path $root $target))) {
            $brokenLinks.Add("$htmlName -> $href")
            continue
        }
        if ($fragment) {
            $targetHtml = if (-not $target) { $htmlName } elseif ($target -match '\.html$') { Split-Path -Leaf $target } else { '' }
            if ($targetHtml -and $htmlIdMap.ContainsKey($targetHtml) -and -not $htmlIdMap[$targetHtml].Contains($fragment)) {
                $brokenFragments.Add("$htmlName -> $href")
            }
        }
    }
}
Add-Check 'html_local_links' ($brokenLinks.Count -eq 0) $(if ($brokenLinks.Count) { $brokenLinks -join '; ' } else { '0 broken local links' })
Add-Check 'html_fragments' ($brokenFragments.Count -eq 0) $(if ($brokenFragments.Count) { $brokenFragments -join '; ' } else { '0 broken HTML fragments' })
Add-Check 'html_duplicate_ids' ($duplicateIds.Count -eq 0) $(if ($duplicateIds.Count) { $duplicateIds -join '; ' } else { '0 duplicate IDs' })

$limitRegion = [regex]::Match($index, '(?s)<h3[^>]*>8\.1 .*?</h3>(?<body>.*?)<h3[^>]*>8\.2 ')
$flowRegion = [regex]::Match($architecture, '(?s)<h2[^>]*>2\. .*?</h2>(?<body>.*?)<h2[^>]*>3\. ')
$limitLists = if ($limitRegion.Success) { [regex]::Matches($limitRegion.Groups['body'].Value, '<ol(?:\s[^>]*)?>').Count } else { 0 }
$limitItems = if ($limitRegion.Success) { [regex]::Matches($limitRegion.Groups['body'].Value, '<li>').Count } else { 0 }
$flowLists = if ($flowRegion.Success) { [regex]::Matches($flowRegion.Groups['body'].Value, '<ol(?:\s[^>]*)?>').Count } else { 0 }
$flowItems = if ($flowRegion.Success) { [regex]::Matches($flowRegion.Groups['body'].Value, '<li>').Count } else { 0 }
$listSemanticsOkay = $limitLists -eq 1 -and $limitItems -eq 22 -and $flowLists -eq 1 -and $flowItems -eq 6
Add-Check 'html_list_semantics' $listSemanticsOkay "AS-IS limits ol $limitLists/items $limitItems; architecture flow ol $flowLists/items $flowItems"

$metadataContractOkay = $index.Contains('<meta property="og:url" content="https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/">') -and
    $index.Contains('<link rel="canonical" href="https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/">') -and
    $architecture.Contains('<meta property="og:url" content="https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/architecture.html">') -and
    $architecture.Contains('<link rel="canonical" href="https://kshield-junior-17th-proj.github.io/jcareer-spec/terraform/asis/architecture.html">') -and
    $index.Contains('<meta property="og:image" content="https://') -and
    $architecture.Contains('<meta property="og:image" content="https://') -and
    $index.Contains('<meta property="og:image:alt"') -and
    $architecture.Contains('<meta property="og:image:alt"')
$uiContractOkay = $metadataContractOkay -and
    $index.Contains('class="skip"') -and
    $architecture.Contains('class="skip"') -and
    $index.Contains(':focus-visible') -and
    $index.Contains('prefers-reduced-motion') -and
    $index.Contains('scroll-margin-top') -and
    $index.Contains('loading="lazy"') -and
    $architecture.Contains('fetchpriority="high"') -and
    $architecture.Contains('id="diagram-zoom"') -and
    $architecture.Contains('aria-pressed="false"') -and
    $architecture.Contains("classList.toggle('is-zoomed')") -and
    $index.Contains('document.querySelectorAll(''.toc ol a[href^="#"]'')') -and
    $index -notmatch 'transition\s*:\s*all' -and
    $publishedText -notmatch '(?:user-scalable\s*=\s*no|maximum-scale\s*=\s*1)'
Add-Check 'html_ui_accessibility_contract' $uiContractOkay $(if ($uiContractOkay) { 'canonical Open Graph metadata, skip links, focus, reduced motion, anchor offset, responsive image hints, zoom control, safe TOC selector' } else { 'one or more metadata, accessibility, or performance guards are missing' })

$mlopsStageCount = [regex]::Matches($index, 'data-mlops-stage="[1-7]"').Count
$mlopsSummaryOkay = $index.Contains('id="mlops-overview"') -and
    $index.Contains('href="../../mlops/"') -and
    $index.Contains('data-mlops-plan="0"') -and
    $index.Contains('data-mlops-plan="13"') -and
    $index.Contains('data-mlops-plan="14"') -and
    $mlopsStageCount -eq 7 -and
    $index.Contains('기준 110개와 분리한 별도 계획이며 수치를 합산하지 않습니다') -and
    $architecture.Contains('href="../../mlops/"')
Add-Check 'mlops_first_page_summary' $mlopsSummaryOkay "top summary, plan stages 0/13/14, seven steps=$mlopsStageCount, AS-IS 110 separation, dedicated-page links"

$flowButtonCount = [regex]::Matches($architecture, 'data-flow-button="[^"]+"').Count
$flowLayerCount = [regex]::Matches($architecture, 'data-flow-layer="[^"]+"').Count
$expectedFlowKeys = @('candidate', 'explanation', 'integrations', 'mlops', 'operations', 'overview', 'recruiter', 'trace', 'workplace')
$flowButtonKeys = @([regex]::Matches($architecture, 'data-flow-button="(?<key>[^"]+)"') | ForEach-Object { $_.Groups['key'].Value } | Sort-Object)
$flowLayerKeys = @([regex]::Matches($architecture, 'data-flow-layer="(?<key>[^"]+)"') | ForEach-Object { $_.Groups['key'].Value } | Sort-Object)
$flowKeysOkay = ($flowButtonKeys -join ',') -eq ($expectedFlowKeys -join ',') -and ($flowLayerKeys -join ',') -eq ($expectedFlowKeys -join ',')
$flowDefinitionMatch = [regex]::Match($architecture, '(?s)const flowDefinitions = (?<json>\{.*?\});\s*const flowButtons')
$serviceFlowKeys = @('candidate', 'recruiter', 'explanation', 'mlops', 'workplace', 'trace', 'integrations', 'operations')
$serviceStageCounts = @{}
$stageCoordinatesOkay = $false
$flowDefinitionsOkay = $false
$detailLinksOkay = $false
if ($flowDefinitionMatch.Success) {
    try {
        $flowDefinitionsObject = $flowDefinitionMatch.Groups['json'].Value | ConvertFrom-Json
        foreach ($key in $serviceFlowKeys) {
            $serviceStageCounts[$key] = @($flowDefinitionsObject.$key.stages).Count
        }
        $badCoordinateKeys = [System.Collections.Generic.List[string]]::new()
        foreach ($key in $serviceFlowKeys) {
            $positions = @($flowDefinitionsObject.$key.stages | ForEach-Object { [int]$_.x })
            if ($positions.Count -ne 3 -or $positions[0] -ge $positions[1] -or $positions[1] -ge $positions[2]) {
                $badCoordinateKeys.Add($key)
            }
        }
        $stageCoordinatesOkay = $badCoordinateKeys.Count -eq 0
        $expectedDetailLinks = @{
            overview = @{ href = 'index.html#section-14'; label = '서비스·구성요소 명세 보기' }
            candidate = @{ href = 'index.html#section-31'; label = '공고 추천 기능 명세 보기' }
            recruiter = @{ href = 'index.html#section-31'; label = '기업용 인재 찾기 명세 보기' }
            explanation = @{ href = 'index.html#section-33'; label = 'AI 점수·설명 규칙 보기' }
            mlops = @{ href = '../../mlops/'; label = 'MLOps 7단계 상세 보기' }
            workplace = @{ href = 'index.html#section-15'; label = '업무망·Slack 경계 보기' }
            trace = @{ href = 'index.html#section-25'; label = 'TRACE·JC-RECEIPT 구현 경계 보기' }
            integrations = @{ href = 'index.html#section-25'; label = '외부 업무도구 구현 경계 보기' }
            operations = @{ href = 'index.html#section-52'; label = '보안·운영 명세 보기' }
        }
        $detailLinksOkay = $true
        foreach ($key in $expectedDetailLinks.Keys) {
            $expected = $expectedDetailLinks[$key]
            $targetExists = $true
            if ($expected.href.StartsWith('index.html#')) {
                $fragment = $expected.href.Substring('index.html#'.Length)
                $targetExists = $index.Contains("id=`"$fragment`"")
            }
            if ($flowDefinitionsObject.$key.detailHref -ne $expected.href -or
                $flowDefinitionsObject.$key.detailLabel -ne $expected.label -or
                -not $targetExists) {
                $detailLinksOkay = $false
            }
        }
        $flowDefinitionsOkay = @($flowDefinitionsObject.overview.stages).Count -eq 6 -and
            (@($serviceStageCounts.Values | Where-Object { $_ -ne 3 }).Count -eq 0) -and
            $stageCoordinatesOkay
    } catch {
        $flowDefinitionsOkay = $false
    }
}
$stepMarkerCount = [regex]::Matches($architecture, 'data-flow-step="[123]"').Count
$stepOneCount = [regex]::Matches($architecture, 'data-flow-step="1"').Count
$stepTwoCount = [regex]::Matches($architecture, 'data-flow-step="2"').Count
$stepThreeCount = [regex]::Matches($architecture, 'data-flow-step="3"').Count
$layerMarkersOkay = $true
$layerRegions = @{}
$layerOrder = @('overview', 'candidate', 'recruiter', 'explanation', 'mlops', 'workplace', 'trace', 'integrations', 'operations')
for ($layerIndex = 0; $layerIndex -lt $layerOrder.Count; $layerIndex++) {
    $key = $layerOrder[$layerIndex]
    $start = $architecture.IndexOf("data-flow-layer=`"$key`"")
    $end = if ($layerIndex -lt $layerOrder.Count - 1) {
        $architecture.IndexOf("data-flow-layer=`"$($layerOrder[$layerIndex + 1])`"", $start + 1)
    } else {
        $architecture.IndexOf('</svg>', $start + 1)
    }
    $region = if ($start -ge 0 -and $end -gt $start) { $architecture.Substring($start, $end - $start) } else { '' }
    $layerRegions[$key] = $region
    $numbers = @([regex]::Matches($region, 'data-flow-step="([123])"') | ForEach-Object { $_.Groups[1].Value })
    $expectedNumbers = if ($key -eq 'overview') { '' } else { '1,2,3' }
    if (($numbers -join ',') -ne $expectedNumbers) { $layerMarkersOkay = $false }
}
$mlopsLayerRegion = $layerRegions['mlops']
$workplaceLayerRegion = $layerRegions['workplace']
$mlopsSeparated = $mlopsLayerRegion -and
    $mlopsLayerRegion.Contains('<path class="flow-line missing" d="M438 1138H2135"') -and
    $mlopsLayerRegion.Contains('x="330" y="960" width="2030" height="380"') -and
    $mlopsLayerRegion.Contains('flow-node missing')
$workplaceNoAwsFlow = $workplaceLayerRegion -and
    -not $workplaceLayerRegion.Contains('<path') -and
    -not $workplaceLayerRegion.Contains('flow-node') -and
    $workplaceLayerRegion.Contains('flow-callout unknown')
$localAwsDataSeparated = -not $layerRegions['candidate'].Contains('flow-line local') -and
    -not $layerRegions['recruiter'].Contains('flow-line local') -and
    -not $layerRegions['candidate'].Contains('cx="1900"') -and
    -not $layerRegions['candidate'].Contains('cx="2132"') -and
    -not $layerRegions['recruiter'].Contains('cx="1900"') -and
    -not $layerRegions['recruiter'].Contains('cx="2132"')
$guardedFlowsOkay = $layerRegions['trace'].Contains('flow-line local') -and
    $layerRegions['integrations'].Contains('flow-line local') -and
    $architecture.Contains('TRACE_MODE 기본값은 disabled') -and
    $architecture.Contains('실제 credential, Slack·Notion workspace, 메일 시스템, 메시지 전송 또는 AWS 리소스는 없습니다')
$overlayLegendOkay = $architecture.Contains('legend-line record') -and
    $architecture.Contains('기록·탐지 구성') -and
    $architecture.Contains('.flow-line.record { stroke: #8a5a00; stroke-dasharray: 34 18; }') -and
    $architecture.Contains('@keyframes flowMarch')
$interactiveFlowOkay = $flowButtonCount -eq 9 -and
    $flowLayerCount -eq 9 -and
    $flowKeysOkay -and
    $flowDefinitionsOkay -and
    $detailLinksOkay -and
    $stepMarkerCount -eq 24 -and $stepOneCount -eq 8 -and $stepTwoCount -eq 8 -and $stepThreeCount -eq 8 -and
    $layerMarkersOkay -and
    $mlopsSeparated -and
    $workplaceNoAwsFlow -and
    $localAwsDataSeparated -and
    $guardedFlowsOkay -and
    $overlayLegendOkay -and
    $architecture.Contains('기업용 인재 찾기') -and
    $architecture.Contains('공고 지원자 안에서') -and
    $architecture.Contains('자사 공고에 지원한 활성 후보자를 대상으로 합니다') -and
    $architecture.Contains('AI 설명 만들기') -and
    $architecture.Contains('MLOps 학습·평가') -and
    $architecture.Contains('전체 보기 1개 · 서비스·보조 경로 8개') -and
    $architecture.Contains('모델 검증 · 검토 대기') -and
    $architecture.Contains('class="flow-step__number"') -and
    $architecture.Contains('class="flow-selector" role="group"') -and
    $architecture.Contains('aria-live="polite"') -and
    $architecture.Contains('flowSteps.replaceChildren') -and
    $architecture.Contains('id="flow-detail-link"') -and
    $architecture.Contains('flowDetailLink.href = definition.detailHref') -and
    $architecture.Contains('flowDetailLink.textContent = definition.detailLabel') -and
    $architecture.Contains('.flow-detail__link:hover { color: var(--accent); border-color: var(--accent); }') -and
    -not $architecture.Contains('var(--accent-2)') -and
    $architecture.Contains('history.replaceState') -and
    $architecture.Contains('updateAddress || requestedKey !== key') -and
    -not $architecture.Contains('<path class="flow-line local" d="M1600 582V920" />') -and
    $architecture.Contains('@media (prefers-reduced-motion: reduce)') -and
    $architecture.Contains('TRACE·JC-RECEIPT와 Slack·Notion·SMTP 어댑터는 기본 비활성 로컬 소스') -and
    $architecture.Contains('실제 외부 전송·AWS 배포·새 Terraform 리소스가 없습니다')
Add-Check 'interactive_service_flow' $interactiveFlowOkay "controls $flowButtonCount, overlay layers $flowLayerCount, eight per-layer 3-step paths, markers $stepMarkerCount; local/AWS data, MLOps, workplace and guarded-source separation, legend, URL state, detail links 9 checked"

$flowSourceText = (Get-Content -Raw -Encoding UTF8 (Join-Path $root 'JCAREER_ASIS_FLOW.md')).Replace("`r`n", "`n").Replace("`r", "`n")
$flowSourceBytes = [System.Text.Encoding]::UTF8.GetBytes($flowSourceText)
$flowSourceHasher = [System.Security.Cryptography.SHA256]::Create()
try {
    $flowSourceHash = ([System.BitConverter]::ToString($flowSourceHasher.ComputeHash($flowSourceBytes))).Replace('-', '').ToLowerInvariant()
} finally {
    $flowSourceHasher.Dispose()
}
$generationOutput = @(& node (Join-Path $root 'build-spec.mjs') --check 2>&1)
$generationExitCode = $LASTEXITCODE
$flowHashOkay = $architecture.Contains("flow-source-sha256`" content=`"$flowSourceHash`"") -and
    $architecture.Contains("data-flow-source-sha256=`"$flowSourceHash`"") -and
    $generationExitCode -eq 0
Add-Check 'flow_source_sync' $flowHashOkay $(if ($flowHashOkay) { "index+architecture match generator inputs; flow $($flowSourceHash.Substring(0, 12))..." } else { "stale generated output: $($generationOutput -join '; ')" })

[xml]$drawio = Get-Content -Raw -Encoding UTF8 (Join-Path $root 'JCAREER_ASIS_FLOW.drawio')
$cells = @($drawio.mxfile.diagram.mxGraphModel.root.mxCell)
$edges = @($cells | Where-Object { $_.edge -eq '1' })
$containers = @($cells | Where-Object { $_.style -match 'container=1' })
$ids = @($cells | ForEach-Object { [string]$_.id })
$drawioDuplicates = @($ids | Group-Object | Where-Object Count -gt 1)
$idSet = [System.Collections.Generic.HashSet[string]]::new([string[]]$ids)
$badEdges = @($edges | Where-Object { -not $idSet.Contains([string]$_.source) -or -not $idSet.Contains([string]$_.target) })
$mlopsCells = @($cells | Where-Object { $_.id -eq 'mlops_status' })
$mlopsConnectedEdges = @($edges | Where-Object { $_.source -eq 'mlops_status' -or $_.target -eq 'mlops_status' })
$slackConnectedEdges = @($edges | Where-Object { $_.source -eq 'office_slack' -or $_.target -eq 'office_slack' })
$requiredDiagramIds = @('office_declared', 'office_slack', 'ecr', 'local_extensions', 'mlops_root', 'mlops_exporter', 'mlops_input_s3', 'mlops_lambda', 'mlops_result_s3', 'mlops_dynamodb', 'mlops_cloudwatch', 'mlops_human')
$missingDiagramIds = @($requiredDiagramIds | Where-Object { -not $idSet.Contains($_) })
$edgePairs = @($edges | ForEach-Object { "$($_.source)>$($_.target)" })
$requiredMlopsEdges = @('mlops_exporter>mlops_input_s3', 'mlops_input_s3>mlops_lambda', 'mlops_lambda>mlops_result_s3', 'mlops_lambda>mlops_dynamodb', 'mlops_lambda>mlops_cloudwatch', 'mlops_dynamodb>mlops_human')
$missingMlopsEdges = @($requiredMlopsEdges | Where-Object { $_ -notin $edgePairs })
$prohibitedAwsIntegrationIcons = @($cells | Where-Object { $_.style -match 'resIcon=mxgraph\.aws4\.(?:eventbridge|sns)' -or $_.value -match '(?:AWS Chatbot|Amazon Q Developer|Slack token)' })
$ecrCells = @($cells | Where-Object { $_.id -eq 'ecr' -and $_.style -match 'resIcon=mxgraph\.aws4\.ecr' })
$drawioOkay = $cells.Count -eq 60 -and $edges.Count -eq 14 -and $drawioDuplicates.Count -eq 0 -and $badEdges.Count -eq 0 -and
    $mlopsCells.Count -eq 1 -and $mlopsConnectedEdges.Count -eq 0 -and $slackConnectedEdges.Count -eq 0 -and
    $missingDiagramIds.Count -eq 0 -and $missingMlopsEdges.Count -eq 0 -and $ecrCells.Count -eq 1 -and $prohibitedAwsIntegrationIcons.Count -eq 0
Add-Check 'drawio_xml' $drawioOkay "cells $($cells.Count), edges $($edges.Count), containers $($containers.Count), duplicate IDs $($drawioDuplicates.Count), bad edges $($badEdges.Count), Slack edges $($slackConnectedEdges.Count), official ECR icons $($ecrCells.Count), missing IDs/MLOps edges $($missingDiagramIds.Count)/$($missingMlopsEdges.Count)"

$pngPath = Join-Path $root 'JCAREER_ASIS_FLOW.drawio.png'
$drawioPath = Join-Path $root 'JCAREER_ASIS_FLOW.drawio'
$pngBytes = [System.IO.File]::ReadAllBytes($pngPath)
$pngSignature = [byte[]](137, 80, 78, 71, 13, 10, 26, 10)
$pngSignatureOkay = $pngBytes.Length -ge 24
for ($index = 0; $pngSignatureOkay -and $index -lt $pngSignature.Length; $index++) {
    $pngSignatureOkay = $pngBytes[$index] -eq $pngSignature[$index]
}
$pngIhdrOkay = $pngSignatureOkay -and [System.Text.Encoding]::ASCII.GetString($pngBytes, 12, 4) -eq 'IHDR'
$pngWidth = if ($pngIhdrOkay) {
    [uint32]($pngBytes[16] * 16777216 + $pngBytes[17] * 65536 + $pngBytes[18] * 256 + $pngBytes[19])
} else { 0 }
$pngHeight = if ($pngIhdrOkay) {
    [uint32]($pngBytes[20] * 16777216 + $pngBytes[21] * 65536 + $pngBytes[22] * 256 + $pngBytes[23])
} else { 0 }
$pngFresh = (Get-Item -LiteralPath $pngPath).LastWriteTimeUtc -ge (Get-Item -LiteralPath $drawioPath).LastWriteTimeUtc
$pngUtf8 = [System.Text.Encoding]::UTF8.GetString($pngBytes)
$pngEditable = $pngUtf8.Contains("mxfile`0<?xml") -and $pngUtf8.Contains('<mxGraphModel')
$pngOkay = $pngIhdrOkay -and $pngWidth -eq 2400 -and $pngHeight -eq 1400 -and $pngFresh -and $pngEditable
$pngDetail = "${pngWidth}x${pngHeight}; PNG signature/IHDR=$pngIhdrOkay; rendered after drawio=$pngFresh; embedded draw.io XML=$pngEditable"
Add-Check 'png_dimensions' $pngOkay $pngDetail

$pdfBytes = [System.IO.File]::ReadAllBytes((Join-Path $root 'JCAREER_ASIS_SYSTEM_SPEC.pdf'))
$pdfHeader = [System.Text.Encoding]::ASCII.GetString($pdfBytes, 0, [Math]::Min(8, $pdfBytes.Length))
Add-Check 'pdf_header' ($pdfHeader.StartsWith('%PDF-')) $pdfHeader.Trim()
$pdfAscii = [System.Text.Encoding]::ASCII.GetString($pdfBytes)
$pdfPages = [regex]::Matches($pdfAscii, '/Type\s*/Page\b').Count
$pdfPath = Join-Path $root 'JCAREER_ASIS_SYSTEM_SPEC.pdf'
$pdfFresh = (Get-Item -LiteralPath $pdfPath).LastWriteTimeUtc -ge (Get-Item -LiteralPath (Join-Path $root 'index.html')).LastWriteTimeUtc -and
    (Get-Item -LiteralPath $pdfPath).LastWriteTimeUtc -ge (Get-Item -LiteralPath (Join-Path $root 'JCAREER_ASIS_SYSTEM_SPEC.md')).LastWriteTimeUtc
$pdfSourceText = (Get-Content -Raw -Encoding UTF8 (Join-Path $root 'index.html')).Replace("`r`n", "`n").Replace("`r", "`n")
$pdfSourceBytes = [System.Text.Encoding]::UTF8.GetBytes($pdfSourceText)
$pdfSourceHasher = [System.Security.Cryptography.SHA256]::Create()
try {
    $pdfSourceHash = ([System.BitConverter]::ToString($pdfSourceHasher.ComputeHash($pdfSourceBytes))).Replace('-', '').ToLowerInvariant()
} finally {
    $pdfSourceHasher.Dispose()
}
$pdfSourceBound = $pdfAscii.Contains('% JCAREER_HTML_SOURCE: terraform/asis/index.html') -and
    $pdfAscii.Contains("% JCAREER_HTML_SHA256: $pdfSourceHash")
$pdfLoopbackLinks = [regex]::Matches($pdfAscii, '/URI\s*\(http://127\.0\.0\.1:').Count
$pdfOkay = $pdfPages -ge 1 -and $pdfSourceBound -and $pdfLoopbackLinks -eq 0
Add-Check 'pdf_page_objects' $pdfOkay "$pdfPages page objects; checkout mtime advisory=$pdfFresh; HTML source bound=$pdfSourceBound; loopback links=$pdfLoopbackLinks"

$secretPatterns = [ordered]@{
    account_id                = '\b\d{12}\b'
    access_key                = '\b(?:AKIA|ASIA)[0-9A-Z]{16}\b'
    private_key               = '-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'
    generic_secret_assignment = '(?im)\b(?:password|passwd|secret|token|api[_-]?key|client[_-]?secret)\s*[:=]\s*["'']?[A-Za-z0-9+/_=-]{8,}'
}
$secretHits = [System.Collections.Generic.List[string]]::new()
$textDeliverables = @('JCAREER_ASIS_SYSTEM_SPEC.md', 'index.html', 'architecture.html', 'JCAREER_ASIS_FLOW.md', 'JCAREER_ASIS_FLOW.drawio', 'validation-report.json')
foreach ($file in $textDeliverables) {
    $content = Get-Content -Raw -Encoding UTF8 (Join-Path $root $file)
    foreach ($entry in $secretPatterns.GetEnumerator()) {
        if ($content -match $entry.Value) { $secretHits.Add("${file}:$($entry.Key)") }
    }
}
$binaryPatterns = [ordered]@{
    account_id  = '\b\d{12}\b'
    access_key  = '\b(?:AKIA|ASIA)[0-9A-Z]{16}\b'
    private_key = '-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'
}
foreach ($file in @('JCAREER_ASIS_SYSTEM_SPEC.pdf', 'JCAREER_ASIS_FLOW.drawio.png')) {
    $binaryAscii = [System.Text.Encoding]::ASCII.GetString([System.IO.File]::ReadAllBytes((Join-Path $root $file)))
    foreach ($entry in $binaryPatterns.GetEnumerator()) {
        if ($binaryAscii -match $entry.Value) { $secretHits.Add("${file}:$($entry.Key)") }
    }
}
Add-Check 'deliverable_secret_patterns' ($secretHits.Count -eq 0) $(if ($secretHits.Count) { $secretHits -join ', ' } else { "0 patterns across $($textDeliverables.Count) UTF-8 sources + 2 binary sentinels" })

$summary = [pscustomobject]@{
    generated_at = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ssK')
    scope = 'local static validation only; no AWS API or terraform apply'
    passed = @($results | Where-Object status -eq 'PASS').Count
    failed = @($results | Where-Object status -eq 'FAIL').Count
    checks = $results
}
$reportJson = (($summary | ConvertTo-Json -Depth 5) -replace "`r`n", "`n") + "`n"
if (-not $CheckOnly) {
    [System.IO.File]::WriteAllText(
        (Join-Path $root 'validation-report.json'),
        $reportJson,
        [System.Text.UTF8Encoding]::new($false)
    )
}
$currentReport = if ($CheckOnly) {
    $reportJson
} else {
    Get-Content -Raw -Encoding UTF8 (Join-Path $root 'validation-report.json')
}
$currentReportHits = @($secretPatterns.GetEnumerator() | Where-Object { $currentReport -match $_.Value })
if ($currentReportHits.Count -gt 0) { throw 'Current validation-report.json failed the post-write secret-pattern guard' }
$results | Format-Table -AutoSize
Write-Host "PASS=$($summary.passed) FAIL=$($summary.failed)"
if ($summary.failed -gt 0) { exit 1 }
