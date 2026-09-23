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
$scratch = Join-Path $env:TEMP ("factify_roots_" + [guid]::NewGuid().ToString('N'))

$javaHome = $env:JAVA_HOME
if (-not $javaHome) { $javaHome = 'C:\Program Files\Android\Android Studio\jbr' }
$keytool = Join-Path $javaHome 'bin\keytool.exe'
$cacerts = Join-Path $javaHome 'lib\security\cacerts'

if (-not (Test-Path $keytool)) { throw "keytool not found at $keytool. Set JAVA_HOME." }

New-Item -ItemType Directory -Path $scratch -Force | Out-Null
if (Test-Path $out) { Remove-Item $out -Force }
Copy-Item $cacerts $out

$index = 0
$imported = 0
foreach ($store in @('Cert:\LocalMachine\Root', 'Cert:\CurrentUser\Root', 'Cert:\LocalMachine\CA')) {
    if (-not (Test-Path $store)) { continue }
    foreach ($cert in Get-ChildItem $store) {
        # $index advances for every certificate, successful or not, because it names
        # both the scratch file and the keystore alias. An earlier version advanced it
        # only on success, and since success was never detected (see below) every
        # certificate was written to ca_0.cer and imported as winroot_0 — so the
        # second import onwards failed on a duplicate alias and the truststore shipped
        # with exactly one Windows root in it.
        $path = Join-Path $scratch ("ca_$index.cer")
        try {
            [System.IO.File]::WriteAllBytes($path, $cert.Export('Cert'))
        } catch {
            $index++
            continue
        }

        # keytool announces "Certificate was added to keystore" on **stderr**, and
        # PowerShell 5.1 turns a native command's stderr into an ErrorRecord. Under
        # ErrorActionPreference 'Stop' that makes a success message a *terminating
        # error*, so the whole import was being swallowed by the catch that was meant
        # for genuine failures. The preference is relaxed around the call and the
        # outcome judged by the exit code, which is the only honest signal here.
        #
        # Duplicates and self-signed oddities are still expected and still fine: a
        # root that will not import is one this JDK already has or cannot use.
        $restore = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        & $keytool -importcert -noprompt -trustcacerts -keystore $out `
            -storepass changeit -alias "winroot_$index" -file $path *>$null
        $ok = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = $restore

        if ($ok) { $imported++ }
        $index++
    }
}

Remove-Item $scratch -Recurse -Force

$ErrorActionPreference = 'Continue'
$total = (& $keytool -list -keystore $out -storepass changeit *>&1 |
          Select-String 'trustedCertEntry').Count
$ErrorActionPreference = 'Stop'

# A truststore holding only the JDK's own roots is the thing this script exists to
# avoid: Gradle fails with "PKIX path building failed" and the message says nothing
# about a truststore. Better to fail here, where the cause is still in view.
if ($imported -eq 0) {
    throw "no Windows roots were imported ($index certificate(s) seen). $out now holds " +
          "only the JDK's own roots and will not resolve dependencies on this network."
}

Write-Output "wrote $out - $imported of $index Windows roots, $total trusted entries total"
