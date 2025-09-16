import os, ssl, smtplib, re
import urllib.parse as up
from email.message import EmailMessage
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

COMPOSE_HTML = r"""
    <!doctype html>
    <meta charset="utf-8">
    <title>Жаңа хат</title>
    <style>
      :root{--bg:#0f1117;--card:#171a22;--line:#2b2f37;--fg:#e9eef7;--muted:#9aa8c1;--accent:#07fff3;}
      body{background:var(--bg);color:var(--fg);font:16px/1.4 "Segoe UI",system-ui,sans-serif;margin:0;padding:24px;}
      .wrap{max-width:860px;margin:0 auto;}
      .card{background:var(--card);border:1px solid var(--line);border-radius:12px; padding:16px;}
      h1{margin:0 0 12px 0;font-size:22px;font-weight:800;}
      label{display:block;margin:10px 0 6px;font-weight:600;color:#cdd7ea}
      input,textarea{width:100%;box-sizing:border-box;background:#111521;border:1px solid #2b2f37;color:var(--fg);
                     border-radius:10px;padding:10px;outline:none}
      input:focus,textarea:focus{border-color:#3ddbf0}
      textarea{min-height:220px;resize:vertical}
      .row{display:grid;grid-template-columns:1fr 1fr; gap:12px}
      .btns{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
      button,.btn{background:#1a202e;border:1px solid #2b2f37;color:var(--fg);padding:10px 14px;border-radius:10px;cursor:pointer;text-decoration:none}
      button:hover,.btn:hover{border-color:#3ddbf0}
      .muted{color:var(--muted);font-size:13px}
      .ok{color:#21d07a}
      .err{color:#ff6b6b}
    </style>
    <div class="wrap">
      <div class="card">
        <h1>Жаңа хат</h1>
        <form method="post" id="composeForm">
          <label>Кімге (to):</label>
          <input name="to" value="{{ to|e }}" placeholder="user@example.com, second@example.com">
          <div class="row">
            <div>
              <label>Көшірме (cc):</label>
              <input name="cc" value="{{ cc|e }}">
            </div>
            <div>
              <label>Жасырын көшірме (bcc):</label>
              <input name="bcc" value="{{ bcc|e }}">
            </div>
          </div>
          <label>Тақырып (subject):</label>
          <input name="subject" value="{{ subject|e }}">
          <label>Мәтін (body):</label>
          <textarea name="body">{{ body|e }}</textarea>
          <div class="btns">
            <button type="submit" title="Жіберу (SMTP арқылы серверден)">Жіберу</button>
            <a class="btn" target="_blank" id="openGmail">Gmail-да ашу</a>
            <a class="btn" target="_blank" id="openOutlook">Outlook Web-те ашу</a>
            <a class="btn" id="openSystem" href="{{ mailto|e }}">Системный клиент</a>
          </div>
          <p class="muted">Егер серверде SMTP өшірілген болса — «Gmail/Outlook» немесе «Системный клиент» батырмаларын қолданыңыз.</p>
        </form>
      </div>
    </div>
    <script>
    function enc(s){return encodeURIComponent(s||"");}
    function csv(s){return (s||"").replace(/;/g,",").split(",").map(x=>x.trim()).filter(Boolean).join(",");}
    function buildGmailURL(to,cc,bcc,subj,body){
      return "https://mail.google.com/mail/?view=cm&fs=1&tf=1"
        + "&to="+enc(csv(to))+"&cc="+enc(csv(cc))+"&bcc="+enc(csv(bcc))
        + "&su="+enc(subj)+"&body="+enc(body)+"&hl=ru";
    }
    function buildOutlookURL(to,cc,bcc,subj,body){
      return "https://outlook.live.com/mail/0/deeplink/compose"
        + "?to="+enc(csv(to))+"&cc="+enc(csv(cc))+"&bcc="+enc(csv(bcc))
        + "&subject="+enc(subj)+"&body="+enc(body);
    }
    function buildMailto(to,cc,bcc,subj,body){
      const q = [];
      if (csv(cc))  q.push("cc="+enc(csv(cc)));
      if (csv(bcc)) q.push("bcc="+enc(csv(bcc)));
      if (subj)     q.push("subject="+enc(subj));
      if (body)     q.push("body="+enc(body));
      return "mailto:"+csv(to)+(q.length?"?"+q.join("&"):"");
    }
    function syncButtons(){
      const f = document.getElementById('composeForm');
      const to=f.to.value, cc=f.cc.value, bcc=f.bcc.value, subj=f.subject.value, body=f.body.value;
      document.getElementById('openGmail').href   = buildGmailURL(to,cc,bcc,subj,body);
      document.getElementById('openOutlook').href = buildOutlookURL(to,cc,bcc,subj,body);
      document.getElementById('openSystem').href  = buildMailto(to,cc,bcc,subj,body);
    }
    ['to','cc','bcc','subject','body'].forEach(id=>{
      document.querySelector(`[name="${id}"]`).addEventListener('input', syncButtons);
    });
    syncButtons();
    </script>
    """


SUCCESS_TEMPLATE = r"""
    <!doctype html>
    <meta charset="utf-8">
    <title>Хат жіберілді</title>
    <style>body{font:16px/1.4 Segoe UI,system-ui,sans-serif;background:#0f1117;color:#e9eef7;padding:24px}</style>
    <h2 style="color:#21d07a">OK: Хат сәтті жіберілді</h2>
    <p><a href="/compose">Жаңа хат</a></p>
    """

ERROR_TEMPLATE = r"""
    <!doctype html>
    <meta charset="utf-8">
    <title>Қате</title>
    <style>body{font:16px/1.4 Segoe UI,system-ui,sans-serif;background:#0f1117;color:#e9eef7;padding:24px}</style>
    <h2 style="color:#ff6b6b">Қате жіберуде</h2>
    <p>{{ error }}</p>
    <p><a href="/compose">Артқа</a></p>
    """

# ---------- Хелперы ----------
def _split_addrs(s: str) -> list[str]:
    if not s:
        return []
    return [tok.strip() for tok in re.split(r'[;,]+', s) if tok.strip()]

def _idna(addr: str) -> str:
    if not addr or '@' not in addr:
        return addr
    local, domain = addr.rsplit('@', 1)
    try:
        domain = domain.encode('idna').decode('ascii')
    except Exception:
        pass
    return f"{local}@{domain}"

def _env_bool(name: str, default=False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1","true","yes","on")

def _join_csv(items: list[str]) -> str:
    return ", ".join([i for i in (items or []) if i])

# ---------- Роут ----------
@app.route("/compose", methods=["GET", "POST"])
def compose():
    # POST: отправка через SMTP
    if request.method == "POST":
        to  = [_idna(a) for a in _split_addrs(request.form.get("to",  ""))]
        cc  = [_idna(a) for a in _split_addrs(request.form.get("cc",  ""))]
        bcc = [_idna(a) for a in _split_addrs(request.form.get("bcc", ""))]
        subject = request.form.get("subject", "") or ""
        body    = request.form.get("body",    "") or ""

        result = {"ok": False, "error": None}

        try:
            if _env_bool("SMTP_ENABLE", False):
                msg = EmailMessage()
                sender = (os.getenv("SMTP_FROM")
                          or os.getenv("SMTP_USER")
                          or "no-reply@example.com")
                msg["From"] = sender
                if to: msg["To"] = _join_csv(to)
                if cc: msg["Cc"] = _join_csv(cc)
                msg["Subject"] = subject
                msg.set_content(body)

                recipients = to + cc + bcc
                if not recipients:
                    raise RuntimeError("Нет получателей (to/cc/bcc)")

                host = os.getenv("SMTP_HOST", "smtp.gmail.com")
                port = int(os.getenv("SMTP_PORT", "587"))
                user = os.getenv("SMTP_USER", "")
                pwd  = os.getenv("SMTP_PASS", "")
                use_ssl      = _env_bool("SMTP_SSL", False)
                use_starttls = _env_bool("SMTP_STARTTLS", True)

                if use_ssl:
                    ctx = ssl.create_default_context()
                    with smtplib.SMTP_SSL(host, port, context=ctx) as s:
                        if user: s.login(user, pwd)
                        s.send_message(msg, to_addrs=recipients)
                else:
                    with smtplib.SMTP(host, port) as s:
                        s.ehlo()
                        if use_starttls:
                            s.starttls(context=ssl.create_default_context())
                        if user: s.login(user, pwd)
                        s.send_message(msg, to_addrs=recipients)

                result["ok"] = True
            else:
                result["error"] = "SMTP выключен (поставьте SMTP_ENABLE=1)."
        except Exception as e:
            result["error"] = str(e)

        wants_json = request.headers.get("Accept","").lower().startswith("application/json") or request.is_json
        if wants_json:
            return jsonify(result)
        return render_template_string(SUCCESS_TEMPLATE if result["ok"] else ERROR_TEMPLATE, **result)

    # GET: предзаполнение
    q = request.args
    to  = _join_csv(sum((_split_addrs(v) for v in q.getlist("to")),  []))
    cc  = _join_csv(sum((_split_addrs(v) for v in q.getlist("cc")),  []))
    bcc = _join_csv(sum((_split_addrs(v) for v in q.getlist("bcc")), []))
    subj = q.get("subject") or q.get("su") or q.get("subj") or ""
    body = q.get("body", "")

    mailto = "mailto:" + up.quote(to or "")
    qp = []
    if cc:   qp.append("cc="     + up.quote(cc))
    if bcc:  qp.append("bcc="    + up.quote(bcc))
    if subj: qp.append("subject="+ up.quote(subj))
    if body: qp.append("body="   + up.quote(body))
    if qp:
        mailto += "?" + "&".join(qp)

    return render_template_string(COMPOSE_HTML,
                                  to=to, cc=cc, bcc=bcc,
                                  subject=subj, body=body,
                                  mailto=mailto)

if __name__ == "__main__":
    # host=0.0.0.0 чтобы доступ был извне, порт 3232
    app.run(host="0.0.0.0", port=3232, debug=True)