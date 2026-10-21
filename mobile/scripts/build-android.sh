#!/usr/bin/env bash
# Costruisce l'APK. Uso: scripts/build-android.sh [versione] [versionCode]
# Con ANDROID_KEYSTORE_B64 / ANDROID_KEYSTORE_PASSWORD / ANDROID_KEY_ALIAS / ANDROID_KEY_PASSWORD produce un APK
# di release firmato con la tua chiave (aggiornabile nel tempo); altrimenti un APK firmato con la chiave di debug.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${1:-0.1.0}"
VERSION_CODE="${2:-1}"

# notifiche push: servono il google-services.json del progetto Firebase (come segreto base64); senza, restano quelle in-app
if [ -n "${ANDROID_GOOGLE_SERVICES_JSON_B64:-}" ]; then export VITE_PUSH=1; fi

npm ci
# interfaccia pensata per il telefono (mobile/web), diversa da quella dell'app Windows
npm run build:web
[ -d android ] || npx cap add android

# sicurezza: niente backup del contenuto dell'app (il token resta nella memoria privata) e solo HTTPS
MANIFEST=android/app/src/main/AndroidManifest.xml
sed -i 's/android:allowBackup="true"/android:allowBackup="false"/' "$MANIFEST"
grep -q 'usesCleartextTraffic' "$MANIFEST" || sed -i 's/<application/<application android:usesCleartextTraffic="false"/' "$MANIFEST"
# rete: solo HTTPS, solo autorità di certificazione del sistema (niente certificati aggiunti dall'utente), e nessun backup/trasferimento dei dati (token compreso)
XML_DIR=android/app/src/main/res/xml
mkdir -p "$XML_DIR"
cat > "$XML_DIR/network_security_config.xml" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="false">
        <trust-anchors>
            <certificates src="system" />
        </trust-anchors>
    </base-config>
</network-security-config>
XML
cat > "$XML_DIR/data_extraction_rules.xml" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<data-extraction-rules>
    <cloud-backup>
        <exclude domain="root" /><exclude domain="file" /><exclude domain="database" /><exclude domain="sharedpref" /><exclude domain="external" />
    </cloud-backup>
    <device-transfer>
        <exclude domain="root" /><exclude domain="file" /><exclude domain="database" /><exclude domain="sharedpref" /><exclude domain="external" />
    </device-transfer>
</data-extraction-rules>
XML
grep -q 'networkSecurityConfig' "$MANIFEST" || sed -i 's/<application/<application android:networkSecurityConfig="@xml\/network_security_config" android:dataExtractionRules="@xml\/data_extraction_rules"/' "$MANIFEST"
grep -q 'networkSecurityConfig' "$MANIFEST" || { echo "manifest: configurazione di rete non applicata"; exit 1; }
grep -q 'allowBackup="false"' "$MANIFEST" || { echo "manifest: allowBackup non disattivato"; exit 1; }

if [ -n "${ANDROID_GOOGLE_SERVICES_JSON_B64:-}" ]; then
  echo "$ANDROID_GOOGLE_SERVICES_JSON_B64" | base64 -d > android/app/google-services.json
  grep -q '"it.vyrncore.jarvis"' android/app/google-services.json || { echo "google-services.json: package diverso da it.vyrncore.jarvis"; exit 1; }
  echo "Push Firebase attive"
else
  echo "google-services.json assente: notifiche push disattivate (restano quelle in-app)"
fi

# versione dell'app
sed -i -E "s/versionCode [0-9]+/versionCode ${VERSION_CODE}/; s/versionName \"[^\"]*\"/versionName \"${VERSION}\"/" android/app/build.gradle

# icone (se lo strumento fallisce resta l'icona predefinita)
npx @capacitor/assets generate --android --iconBackgroundColor '#07121c' --iconBackgroundColorDark '#07121c' \
  || echo "icone personalizzate non generate: uso quelle predefinite"

npx cap sync android

mkdir -p out
cd android
if [ -n "${ANDROID_KEYSTORE_B64:-}" ]; then
  ./gradlew --no-daemon assembleRelease
  BT="$(ls -d "${ANDROID_HOME}"/build-tools/* | sort -V | tail -1)"
  KS="$(mktemp)"; echo "$ANDROID_KEYSTORE_B64" | base64 -d > "$KS"
  "$BT/zipalign" -p -f 4 app/build/outputs/apk/release/app-release-unsigned.apk ../out/aligned.apk
  KS_PASS="$ANDROID_KEYSTORE_PASSWORD" KEY_PASS="${ANDROID_KEY_PASSWORD:-$ANDROID_KEYSTORE_PASSWORD}" \
    "$BT/apksigner" sign --ks "$KS" --ks-pass env:KS_PASS --key-pass env:KEY_PASS \
      --ks-key-alias "$ANDROID_KEY_ALIAS" --out "../out/JARVIS-${VERSION}.apk" ../out/aligned.apk
  rm -f "$KS" ../out/aligned.apk
  echo "APK firmato con la tua chiave: out/JARVIS-${VERSION}.apk"
else
  ./gradlew --no-daemon assembleDebug
  cp app/build/outputs/apk/debug/app-debug.apk "../out/JARVIS-${VERSION}.apk"
  echo "APK firmato con la chiave di DEBUG: out/JARVIS-${VERSION}.apk"
fi
