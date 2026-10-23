package it.vyrncore.jarvis;

import android.Manifest;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.net.Uri;
import android.provider.ContactsContract;

import com.getcapacitor.JSArray;
import com.getcapacitor.JSObject;
import com.getcapacitor.PermissionState;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.getcapacitor.annotation.Permission;
import com.getcapacitor.annotation.PermissionCallback;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Pattern;

/** Telefono e WhatsApp per JARVIS: chiamare, cercare nei contatti, risposta automatica (vedi CallStateReceiver). */
@CapacitorPlugin(
    name = "JarvisPhone",
    permissions = {
        @Permission(strings = {Manifest.permission.CALL_PHONE}, alias = "call"),
        @Permission(strings = {Manifest.permission.ANSWER_PHONE_CALLS}, alias = "answer"),
        @Permission(strings = {Manifest.permission.READ_PHONE_STATE, Manifest.permission.READ_CALL_LOG}, alias = "state"),
        @Permission(strings = {Manifest.permission.READ_CONTACTS}, alias = "contacts")
    }
)
public class JarvisPhonePlugin extends Plugin {
    private static final Pattern NUMBER = Pattern.compile("^[+0-9 ()./-]{3,24}$");
    private static final String WA_VOICE = "vnd.android.cursor.item/vnd.com.whatsapp.voip.call";
    private static final String WA_VIDEO = "vnd.android.cursor.item/vnd.com.whatsapp.video.call";

    private boolean has(String alias) { return getPermissionState(alias) == PermissionState.GRANTED; }

    private JSObject perms() {
        JSObject p = new JSObject();
        p.put("call", has("call"));
        p.put("answer", has("answer"));
        p.put("state", has("state"));
        p.put("contacts", has("contacts"));
        return p;
    }

    private boolean installed(String pkg) {
        try {
            getContext().getPackageManager().getPackageInfo(pkg, 0);
            return true;
        } catch (PackageManager.NameNotFoundException e) {
            return false;
        }
    }

    @PluginMethod
    public void status(PluginCall call) {
        PhonePrefs p = new PhonePrefs(getContext());
        JSObject out = new JSObject();
        out.put("perms", perms());
        out.put("whatsapp", installed("com.whatsapp") || installed("com.whatsapp.w4b"));
        JSObject auto = new JSObject();
        auto.put("enabled", p.auto());
        auto.put("allowed", toArray(p.allowed()));
        auto.put("delay", p.delayS());
        auto.put("speaker", p.speaker());
        out.put("auto", auto);
        call.resolve(out);
    }

    private static JSArray toArray(JSONArray a) {
        JSArray out = new JSArray();
        for (int i = 0; i < a.length(); i++) out.put(a.opt(i));
        return out;
    }

    @PluginMethod
    public void requestPermissions(PluginCall call) {
        requestPermissionForAliases(new String[] {"call", "answer", "state", "contacts"}, call, "permsDone");
    }

    @PermissionCallback
    private void permsDone(PluginCall call) {
        status(call);
    }

    /** Chiama un numero. Con il permesso parte subito, senza resta il tastierino con il numero già scritto. */
    @PluginMethod
    public void dial(PluginCall call) {
        String number = call.getString("number", "").trim();
        if (!NUMBER.matcher(number).matches()) { call.reject("Numero non valido"); return; }
        boolean direct = has("call");
        Intent i = new Intent(direct ? Intent.ACTION_CALL : Intent.ACTION_DIAL, Uri.parse("tel:" + Uri.encode(number)));
        i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        try {
            getContext().startActivity(i);
            new PhonePrefs(getContext()).log((direct ? "Chiamata a " : "Tastierino aperto per ") + number);
            JSObject out = new JSObject();
            out.put("direct", direct);
            call.resolve(out);
        } catch (SecurityException | android.content.ActivityNotFoundException e) {
            call.reject("Impossibile avviare la chiamata");
        }
    }

    /** Contatti per nome: nome e numeri (serve il permesso Contatti). */
    @PluginMethod
    public void findContacts(PluginCall call) {
        if (!has("contacts")) { call.reject("Manca il permesso Contatti"); return; }
        String q = call.getString("query", "").trim();
        if (q.length() < 2) { call.resolve(new JSObject().put("contacts", new JSArray())); return; }
        Map<String, JSArray> byName = new LinkedHashMap<>();
        try (Cursor c = getContext().getContentResolver().query(ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
                new String[] {ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME, ContactsContract.CommonDataKinds.Phone.NUMBER},
                ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME + " LIKE ?", new String[] {"%" + q + "%"},
                ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME + " ASC")) {
            while (c != null && c.moveToNext() && byName.size() < 12) {
                String name = c.getString(0), num = c.getString(1);
                if (name == null || num == null) continue;
                JSArray list = byName.get(name);
                if (list == null) { list = new JSArray(); byName.put(name, list); }
                boolean dup = false;
                for (int k = 0; k < list.length(); k++) if (PhonePrefs.key(list.optString(k)).equals(PhonePrefs.key(num))) dup = true;
                if (!dup) list.put(num);
            }
        }
        JSArray out = new JSArray();
        for (Map.Entry<String, JSArray> e : byName.entrySet()) {
            JSObject o = new JSObject();
            o.put("name", e.getKey());
            o.put("numbers", e.getValue());
            out.put(o);
        }
        call.resolve(new JSObject().put("contacts", out));
    }

    /** Chiamata WhatsApp (voce o video) a un contatto, per numero o per nome. Se il contatto non ha WhatsApp apre la chat. */
    @PluginMethod
    public void whatsapp(PluginCall call) {
        String number = call.getString("number", "").trim();
        String name = call.getString("name", "").trim();
        boolean video = Boolean.TRUE.equals(call.getBoolean("video", false));
        if (number.isEmpty() && name.isEmpty()) { call.reject("Indica un numero o un nome"); return; }
        if (!number.isEmpty() && !NUMBER.matcher(number).matches()) { call.reject("Numero non valido"); return; }
        long dataId = has("contacts") ? findWhatsAppRow(number, name, video) : 0;
        Context ctx = getContext();
        try {
            if (dataId > 0) {
                Intent i = new Intent(Intent.ACTION_VIEW);
                i.setDataAndType(Uri.parse("content://com.android.contacts/data/" + dataId), video ? WA_VIDEO : WA_VOICE);
                i.setPackage(installed("com.whatsapp") ? "com.whatsapp" : "com.whatsapp.w4b");
                i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                ctx.startActivity(i);
                new PhonePrefs(ctx).log("Chiamata WhatsApp" + (video ? " video" : "") + " a " + (name.isEmpty() ? number : name));
                call.resolve(new JSObject().put("method", "call"));
                return;
            }
            String digits = number.replaceAll("[^0-9]", "");
            if (digits.isEmpty()) { call.reject("Contatto WhatsApp non trovato: serve il numero"); return; }
            if (digits.length() <= 10 && !number.startsWith("+")) digits = "39" + digits;  // numero italiano senza prefisso
            Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse("https://wa.me/" + digits));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            ctx.startActivity(i);
            call.resolve(new JSObject().put("method", "chat"));  // la chat è aperta: la chiamata si avvia dall'icona del telefono
        } catch (android.content.ActivityNotFoundException | SecurityException e) {
            call.reject("WhatsApp non è disponibile su questo telefono");
        }
    }

    private long findWhatsAppRow(String number, String name, boolean video) {
        String key = PhonePrefs.key(number);
        String sel = ContactsContract.Data.MIMETYPE + " = ?";
        try (Cursor c = getContext().getContentResolver().query(ContactsContract.Data.CONTENT_URI,
                new String[] {ContactsContract.Data._ID, ContactsContract.Data.DISPLAY_NAME, ContactsContract.Data.DATA1},
                sel, new String[] {video ? WA_VIDEO : WA_VOICE}, null)) {
            long byName = 0;
            while (c != null && c.moveToNext()) {
                long id = c.getLong(0);
                String dn = c.getString(1) == null ? "" : c.getString(1);
                String jid = c.getString(2) == null ? "" : c.getString(2).replaceAll("[^0-9]", "");
                if (!key.isEmpty() && jid.endsWith(key)) return id;
                if (!name.isEmpty() && dn.toLowerCase().contains(name.toLowerCase()) && byName == 0) byName = id;
            }
            return byName;
        } catch (RuntimeException e) {
            return 0;
        }
    }

    @PluginMethod
    public void setAuto(PluginCall call) {
        JSONArray in = call.getArray("allowed");
        JSONArray clean = new JSONArray();
        for (int i = 0; in != null && i < in.length() && clean.length() < 50; i++) {
            JSONObject o = in.optJSONObject(i);
            if (o == null) continue;
            String num = o.optString("number", "").trim();
            if (!NUMBER.matcher(num).matches()) continue;
            try {
                clean.put(new JSONObject().put("name", o.optString("name", "").trim()).put("number", num));
            } catch (org.json.JSONException ignored) { /* voce scartata */ }
        }
        boolean enabled = Boolean.TRUE.equals(call.getBoolean("enabled", false));
        if (enabled && clean.length() == 0) { call.reject("Aggiungi almeno un numero autorizzato"); return; }
        int delay = call.getInt("delay", 3);
        new PhonePrefs(getContext()).save(enabled, clean, Math.max(0, Math.min(6, delay)), Boolean.TRUE.equals(call.getBoolean("speaker", false)));
        new PhonePrefs(getContext()).log(enabled ? "Risposta automatica attivata per " + clean.length() + " numeri" : "Risposta automatica disattivata");
        status(call);
    }

    @PluginMethod
    public void log(PluginCall call) {
        PhonePrefs p = new PhonePrefs(getContext());
        if (Boolean.TRUE.equals(call.getBoolean("clear", false))) p.clearLog();
        JSObject out = new JSObject();
        out.put("log", toArray(p.log()));
        call.resolve(out);
    }
}
