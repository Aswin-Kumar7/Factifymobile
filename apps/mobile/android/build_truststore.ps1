# Build the truststore Gradle needs on a machine that intercepts TLS.
#
#   powershell -ExecutionPolicy Bypass -File android\build_truststore.ps1
#
# Why this exists. Where TLS is intercepted, the interceptor's CA lives in the Windows
# certificate store and is unknown to Java, so Gradle cannot resolve a dependency it
# has not already cached: it fails with "PKIX path building failed" against
# dl.google.com and Maven Central. The tidy fix would be
# `-Djavax.net.ssl.trustStoreType=Windows-ROOT`, but the JetBrains runtime Android
# Studio ships has no SunMSCAPI provider and reports "Windows-ROOT not found".
#
# So: take the JDK's own roots, add every root Windows trusts, and point Gradle at the
# result (see org.gradle.jvmargs in gradle.properties).
#
# The output is deliberately **not** committed. It contains whatever CA this network
# intercepts with, which is a fact about one machine and belongs in nobody's history.

$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$out = Join-Path $here 'windows-roots.jks'
$scratch = Join-Path $env:TEMP ("facify_roots_" + [guid]::NewGuid().ToString('N'))

$javaHome = $env:JAVA_HOME
if (-not $javaHome) { $javaHome = 'C:\Program Files\Android\Android Studio\jbr' }
$keytool = Join-Path $javaHome 'bin\keytool.exe'
$cacerts = Join-Path $javaHome 'lib\security\cacerts'

if (-not (Test-Path $keytool)) { throw "keytool not found at $keytool. Set JAVA_HOME." }

New-Item -ItemType Directory -Path $scratch -Force | Out-Null
if (Test-Path $out) { Remove-Item $out -Force }
Copy-Item $cacerts $out

$exported = 0
foreach ($store in @('Cert:\LocalMachine\Root', 'Cert:\CurrentUser\Root', 'Cert:\LocalMachine\CA')) {
    if (-not (Test-Path $store)) { continue }
    foreach ($cert in Get-ChildItem $store) {
        try {
            $path = Join-Path $scratch ("ca_$exported.cer")
            [System.IO.File]::WriteAllBytes($path, $cert.Export('Cert'))
            # Duplicates and self-signed oddities are expected; a root that will not
            # import is one this JDK already has or cannot use, and neither is fatal.
            & $keytool -importcert -noprompt -trustcacerts -keystore $out `
                -storepass changeit -alias "winroot_$exported" -file $path 2>$null | Out-Null
            $exported++
        } catch { }
    }
}

Remove-Item $scratch -Recurse -Force
$total = (& $keytool -list -keystore $out -storepass changeit 2>$null |
          Select-String 'trustedCertEntry').Count
Write-Output "wrote $out - $exported Windows roots, $total trusted entries total"
