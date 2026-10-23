package it.vyrncore.jarvis;

import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;

import androidx.core.content.FileProvider;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.regex.Pattern;

/** Aggiornamento dell'app dentro l'app: scarica l'APK dalla Release del progetto, ne verifica l'SHA-256 e apre il programma di installazione di Android. */
final class UpdateInstaller {
    private UpdateInstaller() {}

    interface Progress { void percent(int pct); }

    /** Solo file .apk delle Release GitHub: mai un indirizzo qualsiasi. */
    private static final Pattern URL_OK = Pattern.compile("^https://github\\.com/[\\w.-]+/[\\w.-]+/releases/download/[\\w.%+-]+/[\\w.%+-]+\\.apk$");
    private static final Pattern SHA = Pattern.compile("^[0-9a-f]{64}$");

    static boolean allowed(String url) { return url != null && URL_OK.matcher(url).matches(); }

    /** Android 8+: l'utente deve consentire a JARVIS di installare app. Se manca apre la schermata giusta e restituisce false. */
    static boolean canInstall(Context ctx) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O || ctx.getPackageManager().canRequestPackageInstalls()) return true;
        Intent i = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + ctx.getPackageName())).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        ctx.startActivity(i);
        return false;
    }

    static File download(Context ctx, String url, String sha256, Progress cb) throws Exception {
        File dir = new File(ctx.getCacheDir(), "updates");
        if (!dir.exists() && !dir.mkdirs()) throw new Exception("Cartella temporanea non disponibile");
        File[] old = dir.listFiles();
        if (old != null) for (File f : old) f.delete();  // niente vecchi APK che occupano spazio
        File out = new File(dir, "JARVIS-update.apk");
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(20_000);
        c.setReadTimeout(30_000);
        c.setRequestProperty("User-Agent", "jarvis-assistant");
        try {
            if (c.getResponseCode() != 200) throw new Exception("Download non riuscito (HTTP " + c.getResponseCode() + ")");
            long total = c.getContentLengthLong(), got = 0;
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            int last = -1;
            try (InputStream in = c.getInputStream(); FileOutputStream fo = new FileOutputStream(out)) {
                byte[] buf = new byte[64 * 1024];
                int n;
                while ((n = in.read(buf)) > 0) {
                    fo.write(buf, 0, n);
                    md.update(buf, 0, n);
                    got += n;
                    if (total > 0) {
                        int pct = (int) (100 * got / total);
                        if (pct != last) { last = pct; cb.percent(pct); }
                    }
                }
            }
            if (got < 100_000) throw new Exception("File scaricato incompleto");
            if (sha256 != null && SHA.matcher(sha256.toLowerCase()).matches()) {
                StringBuilder hex = new StringBuilder();
                for (byte b : md.digest()) hex.append(String.format("%02x", b));
                if (!hex.toString().equals(sha256.toLowerCase())) {
                    out.delete();
                    throw new Exception("Il file scaricato non corrisponde all'impronta SHA-256: non lo installo");
                }
            }
        } catch (Exception e) {
            out.delete();
            throw e;
        } finally {
            c.disconnect();
        }
        return out;
    }

    static void install(Context ctx, File apk) {
        Uri uri = FileProvider.getUriForFile(ctx, ctx.getPackageName() + ".fileprovider", apk);
        Intent i = new Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        ctx.startActivity(i);
    }
}
