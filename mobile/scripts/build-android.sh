#!/usr/bin/env bash
# Costruisce l'APK. Uso: scripts/build-android.sh [versione] [versionCode]
# Con ANDROID_KEYSTORE_B64 / ANDROID_KEYSTORE_PASSWORD / ANDROID_KEY_ALIAS / ANDROID_KEY_PASSWORD produce un APK
# di release firmato con la tua chiave (aggiornabile nel tempo); altrimenti un APK firmato con la chiave di debug.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${1:-0.1.0}"
VERSION_CODE="${2:-1}"

# la stessa interfaccia dell'app Windows
(cd ../desktop && npm ci && npm run build)

npm ci
[ -d android ] || npx cap add android

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
