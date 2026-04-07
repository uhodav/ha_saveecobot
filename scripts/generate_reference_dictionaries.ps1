$ErrorActionPreference = 'Stop'

$mapsUrl = 'https://www.saveecobot.com/storage/maps_data.js'
$haUiLanguage = if ([string]::IsNullOrWhiteSpace($env:HA_UI_LANGUAGE)) { 'en' } else { $env:HA_UI_LANGUAGE }
$maxNewMarkers = 4000
$saveBatchSize = 100
$requestConcurrency = 20
$requestTimeoutSec = 30
$backfillRelationsWithoutApi = $true

$translationsRootDir = Join-Path $PSScriptRoot '..\custom_components\ha_saveecobot\translations'

function Get-NormalizedLanguageCode {
    param([string]$Language)

    $normalized = if ($null -eq $Language) { '' } else { $Language.Trim().ToLowerInvariant() }

    switch ($normalized) {
        { $_ -in @('uk', 'ua', 'uk-ua', 'ua-ua') } { return 'uk' }
        default { return 'en' }
    }
}

$languageCode = Get-NormalizedLanguageCode -Language $haUiLanguage
$dictDir = Join-Path $translationsRootDir $languageCode
$regionsFile = Join-Path $dictDir 'regions.json'
$districtsFile = Join-Path $dictDir 'districts.json'
$citiesFile = Join-Path $dictDir 'cities.json'
$markersFile = Join-Path $dictDir 'markers.json'

if (-not (Test-Path $dictDir)) {
    New-Item -Path $dictDir -ItemType Directory | Out-Null
}

function Get-StationTemplateByLanguage {
    param([string]$Language)

    $normalized = if ($null -eq $Language) { '' } else { $Language.Trim().ToLowerInvariant() }

    switch ($normalized) {
        { $_ -in @('uk', 'ua', 'uk-ua', 'ua-ua') } { return 'https://www.saveecobot.com/station/{0}.json' }
        default { return 'https://www.saveecobot.com/en/station/{0}.json' }
    }
}

function Get-StationFetchMode {
    if (Get-Command -Name Start-ThreadJob -ErrorAction SilentlyContinue) {
        return 'threadjob'
    }

    if (Get-Command -Name Start-Job -ErrorAction SilentlyContinue) {
        return 'job'
    }

    return 'sequential'
}

$stationTemplate = Get-StationTemplateByLanguage -Language $haUiLanguage
$stationFetchMode = Get-StationFetchMode

Write-Host "[saveecobot] Start dictionaries refresh"
Write-Host "[saveecobot] maps url: $mapsUrl"
Write-Host "[saveecobot] HA UI language: $haUiLanguage"
Write-Host "[saveecobot] normalized language: $languageCode"
Write-Host "[saveecobot] station template: $stationTemplate"
Write-Host "[saveecobot] station fetch mode: $stationFetchMode"
Write-Host "[saveecobot] request concurrency: $requestConcurrency"
Write-Host "[saveecobot] dict dir: $dictDir"

function Load-DictionaryObject {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return @{}
    }

    try {
        $raw = Get-Content -Path $Path -Raw -Encoding utf8
        if ([string]::IsNullOrWhiteSpace($raw)) {
            return @{}
        }

        $obj = $raw | ConvertFrom-Json
        $result = @{}
        foreach ($prop in $obj.PSObject.Properties) {
            $result[$prop.Name] = $prop.Value
        }
        return $result
    }
    catch {
        Write-Host "[saveecobot] Warning: failed to read '$Path'. Starting empty. Error: $($_.Exception.Message)"
        return @{}
    }
}

function Get-IntOrZero {
    param($Value)

    if ($null -eq $Value) {
        return 0
    }

    try {
        return [int]$Value
    }
    catch {
        return 0
    }
}

function Set-ObjectPropertyValue {
    param(
        [object]$Object,
        [string]$PropertyName,
        $Value
    )

    if ($null -eq $Object) { return }

    if (-not ($Object.PSObject.Properties.Name -contains $PropertyName)) {
        $Object | Add-Member -NotePropertyName $PropertyName -NotePropertyValue $Value
    }
    else {
        $Object.$PropertyName = $Value
    }
}

function Ensure-ArrayProperty {
    param(
        [object]$Object,
        [string]$PropertyName
    )

    if ($null -eq $Object) { return }

    if (-not ($Object.PSObject.Properties.Name -contains $PropertyName)) {
        $Object | Add-Member -NotePropertyName $PropertyName -NotePropertyValue @()
    }
    elseif ($null -eq $Object.$PropertyName) {
        $Object.$PropertyName = @()
    }
}

function Save-DictionaryObject {
    param(
        [hashtable]$Data,
        [string]$Path
    )

    $json = $Data | ConvertTo-Json -Depth 20
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

function Save-AllDictionaries {
    Save-DictionaryObject -Data $regions -Path $regionsFile
    Save-DictionaryObject -Data $districts -Path $districtsFile
    Save-DictionaryObject -Data $cities -Path $citiesFile
    Save-DictionaryObject -Data $markers -Path $markersFile
}

$regions = Load-DictionaryObject -Path $regionsFile
$districts = Load-DictionaryObject -Path $districtsFile
$cities = Load-DictionaryObject -Path $citiesFile
$markers = Load-DictionaryObject -Path $markersFile

function Backfill-RelationsWithoutApi {
    Write-Host "[saveecobot] Backfill relations from existing dictionaries (no API)"

    $cityToRegion = @{}
    foreach ($region in $regions.Values) {
        $regionId = Get-IntOrZero -Value $region.region_id
        if ($regionId -le 0) { continue }
        $regionCityIds = $region.city_ids
        if ($null -eq $regionCityIds) { continue }

        foreach ($cityIdValue in $regionCityIds) {
            $cityId = Get-IntOrZero -Value $cityIdValue
            if ($cityId -gt 0) {
                $cityToRegion["$cityId"] = $regionId
            }
        }
    }

    $cityToDistricts = @{}
    foreach ($district in $districts.Values) {
        Ensure-ArrayProperty -Object $district -PropertyName 'marker_ids'

        $districtId = Get-IntOrZero -Value $district.district_id
        if ($districtId -le 0) { continue }

        $districtCityIds = $district.city_ids
        if ($null -eq $districtCityIds) { continue }

        foreach ($cityIdValue in $districtCityIds) {
            $cityId = Get-IntOrZero -Value $cityIdValue
            if ($cityId -le 0) { continue }

            $cityKey = "$cityId"
            if (-not $cityToDistricts.ContainsKey($cityKey)) {
                $cityToDistricts[$cityKey] = New-Object System.Collections.Generic.List[int]
            }
            if (-not $cityToDistricts[$cityKey].Contains($districtId)) {
                $cityToDistricts[$cityKey].Add($districtId)
            }
        }
    }

    foreach ($city in $cities.Values) {
        $cityId = Get-IntOrZero -Value $city.city_id
        if ($cityId -le 0) { continue }

        $cityKey = "$cityId"
        Ensure-ArrayProperty -Object $city -PropertyName 'marker_ids'
        Ensure-ArrayProperty -Object $city -PropertyName 'district_ids'

        if ($cityToDistricts.ContainsKey($cityKey)) {
            foreach ($districtId in $cityToDistricts[$cityKey]) {
                if (-not ($city.district_ids -contains $districtId)) {
                    $city.district_ids += $districtId
                }
            }
        }

        $regionId = 0
        if ($cityToRegion.ContainsKey($cityKey)) {
            $regionId = Get-IntOrZero -Value $cityToRegion[$cityKey]
        }

        $cityDistrictIds = @($city.district_ids)
        $singleDistrictId = 0
        if ($cityDistrictIds.Count -eq 1) {
            $singleDistrictId = Get-IntOrZero -Value $cityDistrictIds[0]
        }

        foreach ($markerIdValue in $city.marker_ids) {
            $markerId = Get-IntOrZero -Value $markerIdValue
            if ($markerId -le 0) { continue }

            $marker = $markers["$markerId"]
            if ($null -eq $marker) { continue }

            if ((Get-IntOrZero -Value $marker.city_id) -le 0) {
                Set-ObjectPropertyValue -Object $marker -PropertyName 'city_id' -Value $cityId
            }

            if ((Get-IntOrZero -Value $marker.region_id) -le 0 -and $regionId -gt 0) {
                Set-ObjectPropertyValue -Object $marker -PropertyName 'region_id' -Value $regionId
            }

            $markerDistrictId = Get-IntOrZero -Value $marker.district_id
            if ($markerDistrictId -le 0 -and $singleDistrictId -gt 0) {
                $markerDistrictId = $singleDistrictId
                Set-ObjectPropertyValue -Object $marker -PropertyName 'district_id' -Value $markerDistrictId
            }

            if ($markerDistrictId -gt 0) {
                $district = $districts["$markerDistrictId"]
                if ($null -ne $district) {
                    Ensure-ArrayProperty -Object $district -PropertyName 'marker_ids'
                    if (-not ($district.marker_ids -contains $markerId)) {
                        $district.marker_ids += $markerId
                    }
                }
            }
        }
    }
}

if ($backfillRelationsWithoutApi) {
    Backfill-RelationsWithoutApi
}

# Build in-memory set of already known marker IDs once at startup.
$knownMarkerIds = New-Object System.Collections.Generic.HashSet[int]
foreach ($k in $markers.Keys) {
    try {
        [void]$knownMarkerIds.Add([int]$k)
    }
    catch {
        # Ignore non-int keys if any malformed data exists
    }
}

# Build in-memory sets for known region/city/district IDs once at startup.
$knownRegionIds = New-Object System.Collections.Generic.HashSet[int]
foreach ($k in $regions.Keys) {
    try {
        [void]$knownRegionIds.Add([int]$k)
    }
    catch {
        # Ignore non-int keys if any malformed data exists
    }
}

$knownDistrictIds = New-Object System.Collections.Generic.HashSet[int]
foreach ($k in $districts.Keys) {
    try {
        [void]$knownDistrictIds.Add([int]$k)
    }
    catch {
        # Ignore non-int keys if any malformed data exists
    }
}

$knownCityIds = New-Object System.Collections.Generic.HashSet[int]
foreach ($k in $cities.Keys) {
    try {
        [void]$knownCityIds.Add([int]$k)
    }
    catch {
        # Ignore non-int keys if any malformed data exists
    }
}

Write-Host "[saveecobot] Existing counts: regions=$($regions.Count), districts=$($districts.Count), cities=$($cities.Count), markers=$($markers.Count)"

Write-Host "[saveecobot] Request maps_data..."
$mapsResponse = Invoke-WebRequest -Uri $mapsUrl -UseBasicParsing -TimeoutSec 60
$mapsPayload = $mapsResponse.Content | ConvertFrom-Json
$devices = @($mapsPayload.devices)

$newMarkerIds = New-Object System.Collections.Generic.List[int]
foreach ($item in $devices) {
    if ($null -eq $item.i) { continue }

    $markerId = [int]$item.i
    if (-not $knownMarkerIds.Contains($markerId)) {
        if (-not $newMarkerIds.Contains($markerId)) {
            $newMarkerIds.Add($markerId)
        }
    }
}

$selected = @($newMarkerIds | Select-Object -First $maxNewMarkers)
Write-Host "[saveecobot] New marker_id total: $($newMarkerIds.Count). Processing first: $($selected.Count)"
if ($selected.Count -eq 0) {
    Save-AllDictionaries
    Write-Host "[saveecobot] No new marker_id found."
    Write-Host "[saveecobot] Saved local relation backfill changes"
    Write-Output $regionsFile
    Write-Output $districtsFile
    Write-Output $citiesFile
    Write-Output $markersFile
    exit 0
}

function Apply-StationData {
    param(
        [int]$MarkerId,
        [psobject]$Station
    )

    $regionIdValue = Get-IntOrZero -Value $Station.region_id
    $cityIdValue = Get-IntOrZero -Value $Station.city_id
    $districtIdValue = Get-IntOrZero -Value $Station.district_id

    # markers.json: {marker_id, type_id, platform_id, sensor_name, region_id, city_id, district_id}
    $markers["$MarkerId"] = [ordered]@{
        marker_id = $MarkerId
        type_id = $Station.type_id
        platform_id = $Station.platform_id
        sensor_name = $Station.sensor_name
        region_id = $regionIdValue
        city_id = $cityIdValue
        district_id = $districtIdValue
    }
    [void]$knownMarkerIds.Add($MarkerId)

    # cities.json: {city_id, city_name, city_type_name, marker_ids, district_ids}
    if ($cityIdValue -gt 0) {
        $cityId = $cityIdValue
        $cityKey = "$cityId"

        if (-not $knownCityIds.Contains($cityId)) {
            $cities[$cityKey] = [ordered]@{
                city_id = $cityId
                city_name = $Station.city_name
                city_type_name = $Station.city_type_name
                marker_ids = @()
                district_ids = @()
            }
            [void]$knownCityIds.Add($cityId)
        }

        if ($null -eq $cities[$cityKey].marker_ids) {
            $cities[$cityKey].marker_ids = @()
        }

        if (-not ($cities[$cityKey].marker_ids -contains $MarkerId)) {
            $cities[$cityKey].marker_ids += $MarkerId
        }

        Ensure-ArrayProperty -Object $cities[$cityKey] -PropertyName 'district_ids'

        if ($districtIdValue -gt 0 -and -not ($cities[$cityKey].district_ids -contains $districtIdValue)) {
            $cities[$cityKey].district_ids += $districtIdValue
        }
    }

    # regions.json: {region_id, region_name, city_ids}
    if ($null -ne $Station.region_id) {
        $regionId = [int]$Station.region_id
        $regionKey = "$regionId"

        if (-not $knownRegionIds.Contains($regionId)) {
            $regions[$regionKey] = [ordered]@{
                region_id = $regionId
                region_name = $Station.region_name
                city_ids = @()
            }
            [void]$knownRegionIds.Add($regionId)
        }

        if ($null -eq $regions[$regionKey].city_ids) {
            $regions[$regionKey].city_ids = @()
        }

        if ($cityIdValue -gt 0) {
            $cityId = $cityIdValue
            if (-not ($regions[$regionKey].city_ids -contains $cityId)) {
                $regions[$regionKey].city_ids += $cityId
            }
        }
    }

    # districts.json: {district_id, district_name, region_id, city_ids, marker_ids}
    if ($districtIdValue -gt 0) {
        $districtId = $districtIdValue
        $districtKey = "$districtId"

        if (-not $knownDistrictIds.Contains($districtId)) {
            $districts[$districtKey] = [ordered]@{
                district_id = $districtId
                district_name = $Station.district_name
                region_id = $Station.region_id
                city_ids = @()
                marker_ids = @()
            }
            [void]$knownDistrictIds.Add($districtId)
        }

        if ($null -eq $districts[$districtKey].city_ids) {
            $districts[$districtKey].city_ids = @()
        }

        if ($cityIdValue -gt 0) {
            $cityId = $cityIdValue
            if (-not ($districts[$districtKey].city_ids -contains $cityId)) {
                $districts[$districtKey].city_ids += $cityId
            }
        }

        Ensure-ArrayProperty -Object $districts[$districtKey] -PropertyName 'marker_ids'

        if (-not ($districts[$districtKey].marker_ids -contains $MarkerId)) {
            $districts[$districtKey].marker_ids += $MarkerId
        }
    }
}

function Invoke-StationRequestSequential {
    param([int]$MarkerId, [string]$StationUrl)

    try {
        $station = Invoke-RestMethod -Uri $StationUrl -TimeoutSec $requestTimeoutSec
        return [pscustomobject]@{ marker_id = $MarkerId; ok = $true; station = $station; error = $null }
    }
    catch {
        return [pscustomobject]@{ marker_id = $MarkerId; ok = $false; station = $null; error = $_.Exception.Message }
    }
}

function Start-StationRequestJob {
    param(
        [int]$MarkerId,
        [int]$Index,
        [int]$Total
    )

    $stationUrl = [string]::Format($stationTemplate, $MarkerId)
    Write-Host "[saveecobot] [$Index/$Total] marker_id=$MarkerId queued"

    if ($stationFetchMode -eq 'threadjob') {
        $job = Start-ThreadJob -ArgumentList $MarkerId, $stationUrl, $requestTimeoutSec -ScriptBlock {
            param($markerIdArg, $stationUrlArg, $timeoutSecArg)
            try {
                $station = Invoke-RestMethod -Uri $stationUrlArg -TimeoutSec $timeoutSecArg
                [pscustomobject]@{ marker_id = [int]$markerIdArg; ok = $true; station = $station; error = $null }
            }
            catch {
                [pscustomobject]@{ marker_id = [int]$markerIdArg; ok = $false; station = $null; error = $_.Exception.Message }
            }
        }
    }
    else {
        $job = Start-Job -ArgumentList $MarkerId, $stationUrl, $requestTimeoutSec -ScriptBlock {
            param($markerIdArg, $stationUrlArg, $timeoutSecArg)
            try {
                $station = Invoke-RestMethod -Uri $stationUrlArg -TimeoutSec $timeoutSecArg
                [pscustomobject]@{ marker_id = [int]$markerIdArg; ok = $true; station = $station; error = $null }
            }
            catch {
                [pscustomobject]@{ marker_id = [int]$markerIdArg; ok = $false; station = $null; error = $_.Exception.Message }
            }
        }
    }

    return [pscustomobject]@{
        marker_id = $MarkerId
        job = $job
    }
}

$idx = 0
$pendingFlushCount = 0

if ($stationFetchMode -eq 'sequential' -or $requestConcurrency -le 1) {
    foreach ($markerId in $selected) {
        $idx++
        Write-Host "[saveecobot] [$idx/$($selected.Count)] marker_id=$markerId queued"

        $stationUrl = [string]::Format($stationTemplate, $markerId)
        $result = Invoke-StationRequestSequential -MarkerId $markerId -StationUrl $stationUrl
        if (-not $result.ok) {
            Write-Host "[saveecobot] marker_id=$markerId error: $($result.error)"
            continue
        }

        Apply-StationData -MarkerId $markerId -Station $result.station
        $pendingFlushCount++

        if ($pendingFlushCount -ge $saveBatchSize) {
            Save-AllDictionaries
            Write-Host "[saveecobot] flushed batch: $pendingFlushCount updates"
            $pendingFlushCount = 0
        }

        Write-Host "[saveecobot] marker_id=$markerId success"
    }
}
else {
    $activeJobs = New-Object System.Collections.ArrayList
    $nextIndex = 0
    $total = $selected.Count

    while ($nextIndex -lt $total -or $activeJobs.Count -gt 0) {
        while ($activeJobs.Count -lt $requestConcurrency -and $nextIndex -lt $total) {
            $markerId = [int]$selected[$nextIndex]
            $queuePosition = $nextIndex + 1
            $nextIndex++
            $jobInfo = Start-StationRequestJob -MarkerId $markerId -Index $queuePosition -Total $total
            [void]$activeJobs.Add($jobInfo)
        }

        if ($activeJobs.Count -eq 0) {
            break
        }

        $completedJob = Wait-Job -Job @($activeJobs | ForEach-Object { $_.job }) -Any
        if ($null -eq $completedJob) {
            continue
        }

        $result = Receive-Job -Job $completedJob
        Remove-Job -Job $completedJob -Force | Out-Null

        for ($i = $activeJobs.Count - 1; $i -ge 0; $i--) {
            if ($activeJobs[$i].job.Id -eq $completedJob.Id) {
                $activeJobs.RemoveAt($i)
                break
            }
        }

        if ($null -eq $result) {
            continue
        }

        $markerId = [int]$result.marker_id
        if (-not $result.ok) {
            Write-Host "[saveecobot] marker_id=$markerId error: $($result.error)"
            continue
        }

        Apply-StationData -MarkerId $markerId -Station $result.station
        $pendingFlushCount++

        if ($pendingFlushCount -ge $saveBatchSize) {
            Save-AllDictionaries
            Write-Host "[saveecobot] flushed batch: $pendingFlushCount updates"
            $pendingFlushCount = 0
        }

        Write-Host "[saveecobot] marker_id=$markerId success"
    }
}

if ($pendingFlushCount -gt 0) {
    Save-AllDictionaries
    Write-Host "[saveecobot] flushed final batch: $pendingFlushCount updates"
}

Write-Host "[saveecobot] Completed"
Write-Host "[saveecobot] Final counts: regions=$($regions.Count), districts=$($districts.Count), cities=$($cities.Count), markers=$($markers.Count)"
Write-Output $regionsFile
Write-Output $districtsFile
Write-Output $citiesFile
Write-Output $markersFile
