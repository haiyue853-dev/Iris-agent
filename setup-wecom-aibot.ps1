[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path $projectRoot '.env'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Set-DotEnvValue([Collections.Generic.List[string]]$Target, [string]$Name, [string]$Value) {
    $escaped = $Value.Replace('\', '\\').Replace('"', '\"')
    $line = "$Name=`"$escaped`""
    for ($index = 0; $index -lt $Target.Count; $index++) {
        if ($Target[$index] -match "^$([Regex]::Escape($Name))=") {
            $Target[$index] = $line
            return
        }
    }
    $Target.Add($line)
}

function Save-Credentials([string]$BotId, [string]$BotSecret) {
    if (-not $BotId.Trim()) {
        throw 'Bot ID cannot be empty.'
    }
    if (-not $BotSecret) {
        throw 'Secret cannot be empty.'
    }
    if ($BotId.Contains("`r") -or $BotId.Contains("`n") -or $BotSecret.Contains("`r") -or $BotSecret.Contains("`n")) {
        throw 'Bot ID and Secret cannot contain a newline.'
    }
    $lines = [Collections.Generic.List[string]]::new()
    if (Test-Path -LiteralPath $envPath) {
        $lines.AddRange([string[]][IO.File]::ReadAllLines($envPath))
    }
    Set-DotEnvValue $lines 'IRIS_WECOM_BOT_ID' $BotId.Trim()
    Set-DotEnvValue $lines 'IRIS_WECOM_BOT_SECRET' $BotSecret
    $utf8WithoutBom = [Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllLines($envPath, $lines, $utf8WithoutBom)

    $written = [IO.File]::ReadAllLines($envPath)
    $hasId = $written | Where-Object { $_ -match '^IRIS_WECOM_BOT_ID=".+"$' }
    $hasSecret = $written | Where-Object { $_ -match '^IRIS_WECOM_BOT_SECRET=".+"$' }
    if (-not $hasId -or -not $hasSecret) {
        throw 'The credentials could not be verified after writing.'
    }
}

$form = New-Object Windows.Forms.Form
$form.Text = 'Iris WeCom Setup - FIXED'
$form.Size = New-Object Drawing.Size(560, 285)
$form.StartPosition = 'CenterScreen'
$form.FormBorderStyle = 'FixedDialog'
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true

$title = New-Object Windows.Forms.Label
$title.Text = 'Configure WeCom intelligent robot'
$title.Font = New-Object Drawing.Font('Segoe UI', 14, [Drawing.FontStyle]::Bold)
$title.Location = New-Object Drawing.Point(24, 18)
$title.AutoSize = $true
$form.Controls.Add($title)

$target = New-Object Windows.Forms.Label
$target.Text = "Target: $envPath"
$target.Location = New-Object Drawing.Point(26, 55)
$target.Size = New-Object Drawing.Size(505, 20)
$form.Controls.Add($target)

$botLabel = New-Object Windows.Forms.Label
$botLabel.Text = 'Bot ID'
$botLabel.Location = New-Object Drawing.Point(26, 88)
$botLabel.AutoSize = $true
$form.Controls.Add($botLabel)

$botInput = New-Object Windows.Forms.TextBox
$botInput.Location = New-Object Drawing.Point(125, 84)
$botInput.Size = New-Object Drawing.Size(400, 25)
$form.Controls.Add($botInput)

$secretLabel = New-Object Windows.Forms.Label
$secretLabel.Text = 'Secret'
$secretLabel.Location = New-Object Drawing.Point(26, 126)
$secretLabel.AutoSize = $true
$form.Controls.Add($secretLabel)

$secretInput = New-Object Windows.Forms.TextBox
$secretInput.Location = New-Object Drawing.Point(125, 122)
$secretInput.Size = New-Object Drawing.Size(400, 25)
$secretInput.UseSystemPasswordChar = $true
$form.Controls.Add($secretInput)

$status = New-Object Windows.Forms.Label
$status.Text = 'Credentials stay on this computer and are ignored by Git.'
$status.Location = New-Object Drawing.Point(26, 163)
$status.Size = New-Object Drawing.Size(500, 25)
$form.Controls.Add($status)

$save = New-Object Windows.Forms.Button
$save.Text = 'Save'
$save.Location = New-Object Drawing.Point(425, 198)
$save.Size = New-Object Drawing.Size(100, 32)
$save.Add_Click({
    try {
        Save-Credentials $botInput.Text $secretInput.Text
        $secretInput.Clear()
        [Windows.Forms.MessageBox]::Show(
            "Credentials saved and verified in:`n$envPath",
            'Iris WeCom Setup',
            [Windows.Forms.MessageBoxButtons]::OK,
            [Windows.Forms.MessageBoxIcon]::Information
        ) | Out-Null
        $form.DialogResult = [Windows.Forms.DialogResult]::OK
        $form.Close()
    }
    catch {
        $status.Text = $_.Exception.Message
        $status.ForeColor = [Drawing.Color]::Firebrick
    }
})
$form.Controls.Add($save)
$form.AcceptButton = $save

[void]$form.ShowDialog()
$secretInput.Clear()
