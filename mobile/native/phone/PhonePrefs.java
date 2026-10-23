package it.vyrncore.jarvis;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

/** Impostazioni della risposta automatica e registro delle chiamate gestite. Restano nella memoria privata dell'app. */
final class PhonePrefs {
    private final SharedPreferences sp;

    PhonePrefs(Context c) {
        sp = c.getSharedPreferences("jarvis_phone", Context.MODE_PRIVATE);
    }

    boolean auto() { return sp.getBoolean("auto", false); }

    /** Secondi di squillo prima di rispondere (0-6: il sistema concede al ricevitore pochi secondi). */
    int delayS() { return Math.max(0, Math.min(6, sp.getInt("delay", 3))); }

    boolean speaker() { return sp.getBoolean("speaker", false); }

    JSONArray allowed() {
        try { return new JSONArray(sp.getString("allowed", "[]")); } catch (JSONException e) { return new JSONArray(); }
    }

    void save(boolean auto, JSONArray allowed, int delay, boolean speaker) {
        sp.edit().putBoolean("auto", auto).putString("allowed", allowed.toString()).putInt("delay", delay).putBoolean("speaker", speaker).apply();
    }

    /** Ultime 9 cifre: «+39 333 123 4567» e «3331234567» sono lo stesso numero. */
    static String key(String n) {
        String d = n == null ? "" : n.replaceAll("[^0-9]", "");
        return d.length() > 9 ? d.substring(d.length() - 9) : d;
    }

    /** Il nome registrato per un numero autorizzato, oppure null se il numero non è nell'elenco. */
    String allowedName(String number) {
        String k = key(number);
        if (k.length() < 6) return null;
        JSONArray a = allowed();
        for (int i = 0; i < a.length(); i++) {
            JSONObject o = a.optJSONObject(i);
            if (o != null && key(o.optString("number")).equals(k)) return o.optString("name", "").isEmpty() ? number : o.optString("name");
        }
        return null;
    }

    void log(String text) {
        JSONArray old = log();
        JSONArray out = new JSONArray();
        try {
            out.put(new JSONObject().put("t", System.currentTimeMillis()).put("e", text));
            for (int i = 0; i < old.length() && out.length() < 30; i++) out.put(old.get(i));
        } catch (JSONException ignored) { /* registro non critico */ }
        sp.edit().putString("log", out.toString()).apply();
    }

    JSONArray log() {
        try { return new JSONArray(sp.getString("log", "[]")); } catch (JSONException e) { return new JSONArray(); }
    }

    void clearLog() { sp.edit().remove("log").apply(); }
}
