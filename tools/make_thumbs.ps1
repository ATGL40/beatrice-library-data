<#
给封面做缩略图（图鉴卡片、排行榜用小图，滚动时解码快；详情页和梯度表导出图片仍用原图）。
只用 Windows 自带的 System.Drawing，不用另装东西；build_pack.py --thumbs 会调用它。

    powershell -NoProfile -ExecutionPolicy Bypass -File tools\make_thumbs.ps1 -Src 封面文件夹 -Dst 缩略图文件夹 [-Width 300] [-Height 225] [-Quality 80] [-Names 名单.txt]

缩略图存成 <封面文件名去掉扩展名>.jpg：从中间裁成 Width:Height（4:3，和卡片、排行榜里看到的部分一样，竖图不会被放大发糊），
再缩到 Width×Height（比它小的图不放大）。缩略图已有、而且不比封面旧的跳过。
给了 -Names（一行一个封面文件名）就只做名单里的。做不了的（比如 System.Drawing 不认识的 webp）打印出来并跳过，不算失败。
#>
param(
  [Parameter(Mandatory)][string]$Src,
  [Parameter(Mandatory)][string]$Dst,
  [int]$Width = 300,
  [int]$Height = 225,
  [int]$Quality = 80,
  [string]$Names = ''
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8  # 让调用它的 Python 读到 UTF-8
Add-Type -AssemblyName System.Drawing
New-Item -ItemType Directory -Force -Path $Dst | Out-Null
$files = if ($Names) { Get-Content -LiteralPath $Names -Encoding UTF8 | Where-Object { $_ } | ForEach-Object { Get-Item -LiteralPath (Join-Path $Src $_) } }
         else { Get-ChildItem -LiteralPath $Src -File | Where-Object { $_.Extension -match '^\.(jpe?g|png|webp)$' } }
$codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq 'image/jpeg' }
$params = New-Object System.Drawing.Imaging.EncoderParameters 1
$params.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter ([System.Drawing.Imaging.Encoder]::Quality, [long]$Quality)
$made = 0; $kept = 0; $failed = 0
foreach ($f in $files) {
  $out = Join-Path $Dst ($f.BaseName + '.jpg')
  if ((Test-Path -LiteralPath $out) -and (Get-Item -LiteralPath $out).LastWriteTimeUtc -ge $f.LastWriteTimeUtc) { $kept++; continue }
  try {
    $img = [System.Drawing.Image]::FromFile($f.FullName)
    try {
      # 从中间裁出 Width:Height 的一块（卡片里 object-fit: cover 也是居中裁）
      $a = $Width / $Height
      if ($img.Width / $img.Height -gt $a) { $cw = $img.Height * $a; $ch = $img.Height } else { $cw = $img.Width; $ch = $img.Width / $a }
      $cx = ($img.Width - $cw) / 2; $cy = ($img.Height - $ch) / 2
      $scale = [Math]::Min(1.0, $Width / $cw)
      $w = [Math]::Max(1, [int][Math]::Round($cw * $scale)); $h = [Math]::Max(1, [int][Math]::Round($ch * $scale))
      $bmp = New-Object System.Drawing.Bitmap $w, $h
      try {
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $g.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
        $g.Clear([System.Drawing.Color]::White)  # 透明的 PNG 垫白底
        # 边缘用 TileFlipXY 取样，缩小后边上不会出现一圈半透明的灰边
        $attr = New-Object System.Drawing.Imaging.ImageAttributes
        $attr.SetWrapMode([System.Drawing.Drawing2D.WrapMode]::TileFlipXY)
        $g.DrawImage($img, (New-Object System.Drawing.Rectangle 0, 0, $w, $h), $cx, $cy, $cw, $ch, [System.Drawing.GraphicsUnit]::Pixel, $attr)
        $g.Dispose(); $attr.Dispose()
        $bmp.Save($out, $codec, $params)
        $made++
      } finally { $bmp.Dispose() }
    } finally { $img.Dispose() }
  } catch {
    Remove-Item -LiteralPath $out -ErrorAction SilentlyContinue  # 写了一半的不留
    Write-Output "跳过 $($f.Name)：$($_.Exception.Message)"
    $failed++
  }
}
Write-Output "缩略图：新做 $made 张，已有 $kept 张，跳过 $failed 张"
