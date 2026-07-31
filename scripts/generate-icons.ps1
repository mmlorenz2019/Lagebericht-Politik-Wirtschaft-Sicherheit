param([string]$OutputDirectory = "assets/icons")

Add-Type -AssemblyName System.Drawing
$target = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $OutputDirectory))
[System.IO.Directory]::CreateDirectory($target) | Out-Null

foreach ($size in @(192, 512)) {
    $bitmap = [System.Drawing.Bitmap]::new($size, $size)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    try {
        $navy = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml('#172554'))
        $bluePen = [System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml('#93c5fd'), [single]($size * 0.055))
        $whitePen = [System.Drawing.Pen]::new([System.Drawing.ColorTranslator]::FromHtml('#f8fafc'), [single]($size * 0.043))
        $orange = [System.Drawing.SolidBrush]::new([System.Drawing.ColorTranslator]::FromHtml('#f59e0b'))
        $whitePen.StartCap = $whitePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
        $graphics.FillRectangle($navy, 0, 0, $size, $size)
        $margin = [single]($size * 0.207)
        $diameter = [single]($size - 2 * $margin)
        $graphics.DrawEllipse($bluePen, $margin, $margin, $diameter, $diameter)
        $center = [single]($size / 2)
        $axis = [single]($size * 0.27)
        $graphics.DrawLine($whitePen, $center, $axis, $center, $size - $axis)
        $graphics.DrawLine($whitePen, $axis, $center, $size - $axis, $center)
        $dot = [single]($size * 0.133)
        $graphics.FillEllipse($orange, $center - $dot / 2, $center - $dot / 2, $dot, $dot)
        $path = Join-Path $target "icon-$size.png"
        $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
        if ($navy) { $navy.Dispose() }
        if ($bluePen) { $bluePen.Dispose() }
        if ($whitePen) { $whitePen.Dispose() }
        if ($orange) { $orange.Dispose() }
    }
}

