package it.vyrncore.jarvis;

import android.Manifest;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.media.AudioManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.telecom.TelecomManager;
import android.telephony.TelephonyManager;

/**
 * Risposta automatica alle chiamate telefoniche, SOLO se l'utente l'ha attivata e SOLO per i numeri che ha autorizzato.
 * JARVIS accetta la chiamata (e, se richiesto, mette il viva voce): Android non permette alle app di parlare al posto dell'utente.
 */
public class CallStateReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(final Context ctx, Intent intent) {
        if (!TelephonyManager.ACTION_PHONE_STATE_CHANGED.equals(intent.getAction())) return;
        if (!TelephonyManager.EXTRA_STATE_RINGING.equals(intent.getStringExtra(TelephonyManager.EXTRA_STATE))) return;
        final PhonePrefs p = new PhonePrefs(ctx);
        if (!p.auto()) return;
        @SuppressWarnings("deprecation")
        final String number = intent.getStringExtra(TelephonyManager.EXTRA_INCOMING_NUMBER);
        if (number == null || number.isEmpty()) return;  // Android manda due avvisi: uno senza numero
        final String who = p.allowedName(number);
        if (who == null) {
            p.log("Non risposto: " + mask(number) + " non è tra i numeri autorizzati");
            return;
        }
        if (Build.VERSION.SDK_INT < 26 || ctx.checkSelfPermission(Manifest.permission.ANSWER_PHONE_CALLS) != PackageManager.PERMISSION_GRANTED) {
            p.log("Non risposto a " + who + ": manca il permesso «Rispondere alle chiamate»");
            return;
        }
        final PendingResult pending = goAsync();
        final Handler h = new Handler(Looper.getMainLooper());
        h.postDelayed(new Runnable() {
            @Override
            public void run() {
                try {
                    answer(ctx, p, who);
                } finally {
                    h.postDelayed(new Runnable() { @Override public void run() { pending.finish(); } }, p.speaker() ? 900 : 0);
                }
            }
        }, p.delayS() * 1000L);
    }

    private static void answer(Context ctx, PhonePrefs p, String who) {
        try {
            TelephonyManager tm = (TelephonyManager) ctx.getSystemService(Context.TELEPHONY_SERVICE);
            if (tm != null && tm.getCallState() != TelephonyManager.CALL_STATE_RINGING) {
                p.log("Chiamata di " + who + " già terminata o risposta da te");
                return;
            }
            TelecomManager t = (TelecomManager) ctx.getSystemService(Context.TELECOM_SERVICE);
            if (t == null) return;
            t.acceptRingingCall();
            p.log("Risposto alla chiamata di " + who);
            if (p.speaker()) {
                AudioManager am = (AudioManager) ctx.getSystemService(Context.AUDIO_SERVICE);
                if (am != null) { am.setMode(AudioManager.MODE_IN_CALL); am.setSpeakerphoneOn(true); }
            }
        } catch (SecurityException e) {
            p.log("Non risposto a " + who + ": permesso negato dal sistema");
        } catch (RuntimeException e) {
            p.log("Non risposto a " + who + ": " + e.getClass().getSimpleName());
        }
    }

    private static String mask(String n) {
        String d = n.replaceAll("[^0-9]", "");
        return d.length() <= 3 ? "un numero" : "…" + d.substring(d.length() - 3);
    }
}
