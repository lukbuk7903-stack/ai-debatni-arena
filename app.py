import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import errors, types
import time, random
from datetime import datetime
import pypdf
import os
import urllib.request
import urllib.parse
import markdown
from weasyprint import HTML, CSS
from openai import OpenAI, APITimeoutError
import base64
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
import re
import json

st.set_page_config(page_title="AI Debatní Aréna", layout="wide")

# --- 1. INICIALIZACE PAMĚTI (Session State) ---
if "debate_active" not in st.session_state:
    st.session_state.debate_active = False
if "full_history" not in st.session_state:
    st.session_state.full_history = []
if "final_summary" not in st.session_state:
    st.session_state.final_summary = ""
if "model_mod_used" not in st.session_state:
    st.session_state.model_mod_used = ""
if "current_topic" not in st.session_state:
    st.session_state.current_topic = ""

if "md_content" not in st.session_state:
    st.session_state.md_content = ""
if "pdf_bytes" not in st.session_state:
    st.session_state.pdf_bytes = b""
if "file_base_name" not in st.session_state:
    st.session_state.file_base_name = "debata"

# --- NOVÉ: Kritika ---
if "critique_md" not in st.session_state:
    st.session_state.critique_md = ""
if "critique_pdf" not in st.session_state:
    st.session_state.critique_pdf = b""
if "critique_base" not in st.session_state:
    st.session_state.critique_base = ""
if "show_critique_ui" not in st.session_state:
    st.session_state.show_critique_ui = False

form_defaults = {
    "gemini_key": "", "nim_key": "", "mistral_key": "",
    "role_a_name": "", "role_a_prompt": "", "provider_a": "Gemini", "input_type_a": "Ručně",
    "role_b_name": "", "role_b_prompt": "", "provider_b": "Gemini", "input_type_b": "Ručně",
    "provider_mod": "Gemini", "topic_input": "", "max_rounds": 4,
    "topic_input_type": "Ručně", "topic_document_text": "", "topic_summary": "",
    "uploaded_files_hash": ""
}
for key, default in form_defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default

# --- 2. POMOCNÉ FUNKCE ---
def extract_text_from_file(uploaded_file):
    if uploaded_file is None:
        return ""
    file_extension = uploaded_file.name.split('.')[-1].lower()
    try:
        if file_extension == 'pdf':
            pdf_reader = pypdf.PdfReader(uploaded_file)
            text = ""
            for page in pdf_reader.pages:
                if page.extract_text():
                    text += page.extract_text() + "\n"
            return text.strip()
        else:
            return uploaded_file.read().decode("utf-8").strip()
    except Exception as e:
        st.error(f"Chyba při čtení souboru {uploaded_file.name}: {e}")
        return ""

def generate_pdf(text_content):
    html_body = markdown.markdown(text_content, extensions=['tables', 'nl2br'])
    css_style = """
    @page { size: A4; margin: 2cm; @bottom-center { content: "Strana " counter(page) " z " counter(pages); font-size: 9pt; color: #666; } }
    body { font-family: 'DejaVu Sans', sans-serif; font-size: 11pt; line-height: 1.5; color: #333; }
    h1 { color: #1a365d; font-size: 22pt; border-bottom: 2px solid #3182ce; padding-bottom: 5px; margin-top: 25px; }
    h2 { color: #2c5282; font-size: 16pt; margin-top: 20px; }
    h3 { color: #2b6cb0; font-size: 13pt; margin-top: 15px; }
    p { margin-bottom: 10px; text-align: justify; }
    small { color: #718096; font-size: 9pt; display: block; margin-top: 5px; font-style: italic; }
    blockquote { border-left: 4px solid #cbd5e0; padding-left: 15px; color: #4a5568; font-style: italic; background-color: #f7fafc; padding: 10px 15px; margin: 10px 0; }
    table { width: 100%; border-collapse: collapse; margin: 15px 0; font-size: 10pt; }
    th, td { border: 1px solid #e2e8f0; padding: 8px 12px; text-align: left; }
    th { background-color: #edf2f7; font-weight: bold; color: #2d3748; }
    tr:nth-child(even) { background-color: #f7fafc; }
    """
    full_html = f"<!DOCTYPE html><html lang='cs'><head><meta charset='utf-8'></head><body>{html_body}</body></html>"
    try:
        return HTML(string=full_html).write_pdf(stylesheets=[CSS(string=css_style)])
    except Exception as e:
        st.error(f"Chyba při generování PDF: {e}")
        return b""

# --- 2b. CLOUDFLARE R2 ---
@st.cache_resource
def get_r2_client():
    return boto3.client(
        service_name="s3",
        endpoint_url=f"https://{st.secrets['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=st.secrets["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            request_checksum_calculation="when_required"
        ),
    )

def get_next_counter():
    s3 = get_r2_client()
    bucket = st.secrets["R2_BUCKET_NAME"]
    current = 0
    try:
        obj = s3.get_object(Bucket=bucket, Key="counter.txt")
        current = int(obj["Body"].read().decode("utf-8").strip())
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') not in ('NoSuchKey', '404', 'NoSuchBucket'):
            st.warning(f"⚠️ Nepodařilo se načíst čítač z R2: {e}")
    except Exception:
        current = 0
    next_val = current + 1
    s3.put_object(Bucket=bucket, Key="counter.txt", Body=str(next_val).encode("utf-8"))
    return f"{next_val:05d}"

def generate_filename_from_topic(topic, call_ai_func, available_providers):
    priority = []
    if "Gemini" in available_providers: priority.append("Gemini")
    if "Mistral" in available_providers: priority.append("Mistral")
    if "NVIDIA NIM" in available_providers: priority.append("NVIDIA NIM")
    if not priority: return "debata"

    prompt = (
        f"Na základě tématu diskuze vygeneruj velmi krátký název souboru "
        f"(maximálně 7 slov). Použij pouze písmena bez diakritiky, číslice a podtržítka. "
        f"Téma: '{topic}'"
    )
    system_prompt = "Jsi pomocník pro generování bezpečných názvů souborů. Odpovídej pouze názvem, nic jiného."

    for provider in priority:
        try:
            raw_name, _ = call_ai_func(system_prompt, prompt, provider)
            clean = raw_name.strip().lower()
            clean = re.sub(r"[^a-z0-9_]+", "_", clean)
            clean = re.sub(r"_+", "_", clean).strip("_")
            words = clean.split("_")
            clean = "_".join(words[:7])
            if clean: return clean
        except Exception as e:
            st.warning(f"⚠️ Generování názvu přes {provider} selhalo: {e}")
            continue
    return "debata"

GEMINI_PREFERRED = ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-3.8-flash"]
NVIDIA_PREFERRED = ["nvidia/nemotron-3-ultra-550b-a55b"]
MISTRAL_PREFERRED = ["ministral-3b-2512", "ministral-8b-2512", "codestral-2508", "mistral-large-2512"]

def get_available_gemini_models(client):
    try:
        models = client.models.list()
        available = [m.name.replace('models/', '') for m in models if 'generateContent' in getattr(m, 'supported_generation_methods', [])]
        if not available: return GEMINI_PREFERRED
        verified = [m for m in GEMINI_PREFERRED if m in available]
        return verified if verified else available
    except Exception as e:
        st.warning(f"⚠️ Nepodařilo se načíst seznam modelů Gemini: {e}")
        return GEMINI_PREFERRED

def get_available_nvidia_models(client):
    return NVIDIA_PREFERRED

def get_available_mistral_models(client):
    try:
        all_models = client.models.list()
        available_ids = [m.id for m in all_models.data if m.id]
        if not available_ids: return MISTRAL_PREFERRED
        verified = [m for m in MISTRAL_PREFERRED if m in available_ids]
        return verified if verified else available_ids[:3]
    except Exception as e:
        st.warning(f"⚠️ Nepodařilo se načíst seznam modelů Mistral: {e}")
        return MISTRAL_PREFERRED

def get_delay_for_provider(provider):
    if provider == "NVIDIA NIM": return 2.0
    elif provider == "Gemini": return 6.0
    elif provider == "Mistral": return 3.0
    return 2.0

def render_downloads():
    base_name = st.session_state.get("file_base_name", "debata")
    md_b64 = base64.b64encode(st.session_state.md_content.encode('utf-8')).decode('utf-8')
    pdf_b64 = base64.b64encode(st.session_state.pdf_bytes).decode('utf-8') if st.session_state.pdf_bytes else ""
    md_href = f"data:application/octet-stream;base64,{md_b64}"
    pdf_href = f"data:application/pdf;base64,{pdf_b64}"
    html_code = f"""
    <div style="display: flex; gap: 10px; font-family: 'Source Sans Pro', sans-serif;">
        <a href="{md_href}" download="{base_name}.md" style="flex: 1; text-align: center; padding: 10px; background-color: #f0f2f6; color: #31333f; text-decoration: none; border-radius: 5px; border: 1px solid #d6d6d6; font-size: 16px;">📥 Stáhnout jako Markdown (.md)</a>
        <a href="{pdf_href}" download="{base_name}.pdf" style="flex: 1; text-align: center; padding: 10px; background-color: #ff4b4b; color: white; text-decoration: none; border-radius: 5px; font-size: 16px;">📄 Stáhnout jako PDF (.pdf)</a>
    </div>
    """
    components.html(html_code, height=60)

# --- 2c. NEZÁVISLÁ KRITIKA ---

CRITIQUE_SYSTEM_PROMPT = (
    "Jsi nezávislý recenzent a odborník na kritické hodnocení diskuzí. "
    "Tvým úkolem je nestranně posoudit kvalitu diskuze a verdikt rozhodčího. "
    "Buď konkrétní, kritický a konstruktivní. Odpovídej česky, strukturovaně v Markdownu."
)

def build_critique_prompt(md_content, topic):
    return f"""Vyhodnoť mi tuto diskuzi. Její relevantnost a "recenzuj" verdikt rozhodčího.

**Téma diskuze:** {topic}

**Úkoly pro tebe:**
1. **Relevantnost:** Zhodnoť, zda diskuze skutečně odpovídá na zadané téma.
2. **Kvalita argumentace:** Posuď sílu argumentů obou stran – kde byly přesvědčivé, kde slabé?
3. **Recenze verdiktu:** Byl verdikt rozhodčího oprávněný? Bylo odůvodnění přesvědčivé?
4. **Silné a slabé stránky** obou diskutujících.
5. **Návrh vyváženějšího verdiktu**, pokud s ním nesouhlasíš.
6. **Doporučení** pro zlepšení příští diskuze.

**Text diskuze:**

{md_content}
"""

def get_presigned_url(key, expires_in=3600):
    """Vygeneruje dočasnou veřejnou URL k soukromému souboru na R2."""
    try:
        s3 = get_r2_client()
        bucket = st.secrets["R2_BUCKET_NAME"]
        return s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': key},
            ExpiresIn=expires_in
        )
    except Exception as e:
        st.warning(f"⚠️ Nepodařilo se vygenerovat presigned URL: {e}")
        return None

def call_critique_api(system_prompt, user_prompt, provider, keys):
    """Samostatné volání API pro kritiku – nezávislé na běhu debaty."""
    if provider == "Gemini":
        client = genai.Client(api_key=keys["gemini"], http_options=types.HttpOptions(timeout=180000))
        models = get_available_gemini_models(client)
        full = f"{system_prompt}\n\n---\n\n{user_prompt}"
        last_err = None
        for model in models:
            try:
                r = client.models.generate_content(model=model, contents=full, config=types.GenerateContentConfig())
                if r.text and r.text.strip():
                    return r.text, model
            except Exception as e:
                last_err = e
        raise Exception(f"Kritika přes Gemini selhala: {last_err}")

    elif provider == "NVIDIA NIM":
        client = OpenAI(api_key=keys["nim"], base_url="https://integrate.api.nvidia.com/v1", timeout=180.0)
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        last_err = None
        for model in NVIDIA_PREFERRED:
            try:
                r = client.chat.completions.create(model=model, messages=messages, temperature=0.7)
                if r.choices[0].message.content:
                    return r.choices[0].message.content, model
            except Exception as e:
                last_err = e
        raise Exception(f"Kritika přes NVIDIA selhala: {last_err}")

    elif provider == "Mistral":
        client = OpenAI(api_key=keys["mistral"], base_url="https://api.mistral.ai/v1", timeout=180.0)
        models = get_available_mistral_models(client)
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
        last_err = None
        for model in models:
            try:
                r = client.chat.completions.create(model=model, messages=messages, temperature=0.7)
                if r.choices[0].message.content:
                    return r.choices[0].message.content, model
            except Exception as e:
                last_err = e
        raise Exception(f"Kritika přes Mistral selhala: {last_err}")

    raise Exception(f"Neznámý poskytovatel: {provider}")

def generate_critique_md(critique_text, model_used, topic):
    ts = datetime.now().strftime('%d.%m.%Y %H:%M')
    return f"""# Nezávislá kritika diskuze

**Téma:** {topic}  
**Datum kritiky:** {ts}  
**Model kritika:** {model_used}

---

{critique_text}
"""

def save_critique_to_r2(base_name, md_content, pdf_bytes):
    """Uloží kritiku na R2 do VERDICT/markdown/ a VERDICT/pdf/."""
    try:
        s3 = get_r2_client()
        bucket = st.secrets["R2_BUCKET_NAME"]
        s3.put_object(
            Bucket=bucket, Key=f"VERDICT/markdown/{base_name}.md",
            Body=md_content.encode("utf-8"), ContentType="text/markdown"
        )
        s3.put_object(
            Bucket=bucket, Key=f"VERDICT/pdf/{base_name}.pdf",
            Body=pdf_bytes, ContentType="application/pdf"
        )
        return True, None
    except Exception as e:
        return False, str(e)

def save_critique_result(critique_text, model_used):
    """Vygeneruje PDF, uloží do session_state i na R2 a vrátí výsledek."""
    base_name = f"{st.session_state.file_base_name}_kritika"
    md_content = generate_critique_md(critique_text, model_used, st.session_state.current_topic)
    pdf_bytes = generate_pdf(md_content)
    st.session_state.critique_md = md_content
    st.session_state.critique_pdf = pdf_bytes
    st.session_state.critique_base = base_name
    ok, err = save_critique_to_r2(base_name, md_content, pdf_bytes)
    return ok, err, base_name

def build_critique_html(md_content, base_name):
    """Sestaví plnohodnotný HTML dokument pro nový panel prohlížeče."""
    md_html = markdown.markdown(md_content, extensions=['tables', 'nl2br'])
    md_b64 = base64.b64encode(md_content.encode('utf-8')).decode('utf-8')
    pdf_b64 = base64.b64encode(st.session_state.critique_pdf).decode('utf-8') if st.session_state.critique_pdf else ""

    return f"""<!DOCTYPE html>
<html lang="cs">
<head>
<meta charset="utf-8">
<title>Kritika – {base_name}</title>
<style>
    body {{ font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; max-width: 900px; margin: 30px auto; padding: 20px; line-height: 1.65; color: #2d3748; background: #fff; }}
    h1 {{ color: #1a365d; border-bottom: 3px solid #3182ce; padding-bottom: 12px; }}
    h2 {{ color: #2c5282; margin-top: 28px; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; }}
    h3 {{ color: #2b6cb0; }}
    .controls {{ position: sticky; top: 0; background: #fff; padding: 15px 0; border-bottom: 1px solid #eee; margin-bottom: 25px; display: flex; gap: 10px; z-index: 100; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }}
    .btn {{ flex: 1; text-align: center; padding: 12px 16px; text-decoration: none; border-radius: 6px; border: none; cursor: pointer; font-size: 15px; font-family: inherit; font-weight: 600; transition: opacity 0.2s; }}
    .btn-md {{ background: #f0f2f6; color: #31333f; border: 1px solid #d6d6d6; }}
    .btn-pdf {{ background: #ff4b4b; color: #fff; }}
    .btn-close {{ background: #4a5568; color: #fff; }}
    .btn:hover {{ opacity: 0.85; }}
    blockquote {{ border-left: 4px solid #cbd5e0; padding-left: 15px; color: #4a5568; background: #f7fafc; padding: 10px 15px; margin: 15px 0; }}
    table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
    th, td {{ border: 1px solid #e2e8f0; padding: 8px 12px; text-align: left; }}
    th {{ background: #edf2f7; }}
    code {{ background: #f7fafc; padding: 2px 6px; border-radius: 3px; font-family: 'Consolas', monospace; font-size: 0.92em; }}
    pre {{ background: #f7fafc; padding: 12px; border-radius: 6px; overflow-x: auto; }}
</style>
</head>
<body>
<div class="controls">
    <a href="data:application/octet-stream;base64,{md_b64}" download="{base_name}.md" class="btn btn-md">📥 Stáhnout .md</a>
    <a href="data:application/pdf;base64,{pdf_b64}" download="{base_name}.pdf" class="btn btn-pdf">📄 Stáhnout .pdf</a>
    <button class="btn btn-close" onclick="window.close()">✖ Zavřít</button>
</div>
{md_html}
</body>
</html>"""

def reset_critique_state():
    st.session_state.critique_md = ""
    st.session_state.critique_pdf = b""
    st.session_state.critique_base = ""
    st.session_state.show_critique_ui = False

def render_perplexity_ui():
    """Manuální + volitelná automatická cesta pro Perplexity."""
    st.info(
        "💡 **Perplexity nespolehlivě načítá `.md` soubory z URL.** "
        "Nejlepší cesta je **manuální**: stáhněte PDF, přiložte ho v Perplexity a vložte prompt."
    )

    if st.session_state.file_base_name == "debata":
        st.error("⚠️ Soubor diskuze nebyl nahrán na R2. Použijte prosím API variantu výše.")
        return

    base_name = st.session_state.file_base_name
    topic = st.session_state.current_topic

    # === KROK 1: Stáhnout PDF ===
    st.markdown("#### Krok 1 – Stáhněte si diskuzi jako PDF")
    pdf_b64 = base64.b64encode(st.session_state.pdf_bytes).decode('utf-8') if st.session_state.pdf_bytes else ""
    st.markdown(
        f'<a href="data:application/pdf;base64,{pdf_b64}" download="{base_name}.pdf" '
        f'style="display:block; text-align:center; padding:12px; background:#ff4b4b; color:white; '
        f'text-decoration:none; border-radius:6px; font-weight:600;">'
        f'📄 Stáhnout {base_name}.pdf</a>',
        unsafe_allow_html=True
    )

    # === KROK 2: Otevřít Perplexity ===
    st.markdown("#### Krok 2 – Otevřete Perplexity v novém panelu")
    components.html(
        '<a href="https://www.perplexity.ai/" target="_blank" rel="noopener noreferrer" '
        'style="display:block; text-align:center; padding:12px; background:#20b8cd; color:white; '
        'text-decoration:none; border-radius:6px; font-weight:600; font-family:\'Source Sans Pro\', sans-serif;">'
        '🔗 Otevřít Perplexity</a>',
        height=50
    )

    # === KROK 3: Zkopírovat prompt ===
    st.markdown("#### Krok 3 – Zkopírujte prompt a vložte ho do Perplexity")
    prompt_for_perplexity = (
        f"Vyhodnoť mi tuto diskuzi na téma: \"{topic}\". "
        f"Její relevantnost a recenzuj verdikt rozhodčího.\n\n"
        f"Zaměř se na:\n"
        f"1. Relevantnost diskuze k zadanému tématu.\n"
        f"2. Kvalitu argumentace obou stran – kde byly přesvědčivé, kde slabé.\n"
        f"3. Recenzi verdiktu rozhodčího – byl oprávněný? Bylo odůvodnění přesvědčivé?\n"
        f"4. Silné a slabé stránky obou diskutujících.\n"
        f"5. Návrh vyváženějšího verdiktu, pokud s ním nesouhlasíš.\n"
        f"6. Doporučení pro zlepšení příští diskuze.\n\n"
        f"(Přiložený PDF soubor obsahuje celou diskuzi včetně verdiktu rozhodčího.)"
    )
    st.code(prompt_for_perplexity, language=None)

    st.caption("💡 Po najetí myší na blok výše se objeví ikona 📋 pro zkopírování.")

    # === KROK 4: Vložit výsledek ===
    st.markdown("#### Krok 4 – Vložte sem výsledek kritiky z Perplexity")
    pasted = st.text_area(
        "Výsledek z Perplexity:",
        height=200,
        key="critique_pasted_perplexity",
        label_visibility="collapsed",
        placeholder="Sem vložte text kritiky, který jste zkopírovali z Perplexity..."
    )
    if st.button("💾 Uložit kritiku na R2", type="primary", use_container_width=True):
        if pasted.strip():
            ok, err, saved_base = save_critique_result(pasted, "Perplexity (manuálně)")
            if ok:
                st.success(f"✅ Uloženo jako `VERDICT/markdown/{saved_base}.md` a `VERDICT/pdf/{saved_base}.pdf`.")
            else:
                st.warning(f"⚠️ Uložení selhalo: {err}")
            # ŽÁDNÝ st.rerun() – UI se vykreslí ve stejném běhu
        else:
            st.error("Nejprve vložte text kritiky.")

    # === VOLITELNÉ: Automatická cesta ===
    with st.expander("⚙️ Pokročilé – zkusit automaticky přes PDF URL (může selhat)"):
        st.caption(
            "Tato cesta vygeneruje **presigned URL** k PDF souboru na R2 (platnost 1 hodina) "
            "a pokusí se otevřít Perplexity s promptem obsahujícím tuto URL. "
            "**Může selhat**, protože Perplexity nemá vždy stabilní extrakci obsahu z URL. "
            "Pokud selže, použijte manuální cestu výše."
        )
        if st.button("🔗 Otevřít Perplexity s PDF URL", key="pplx_auto_btn"):
            presigned = get_presigned_url(f"pdf/{base_name}.pdf", expires_in=3600)
            if presigned:
                short_prompt = (
                    f"Přečti obsah PDF souboru na této URL a proveď nezávislou kritiku diskuze na téma '{topic}'. "
                    f"Zhodnoť relevanci, kvalitu argumentace obou stran a kriticky recenzuj verdikt rozhodčího. "
                    f"Navrhni vyváženější verdikt, pokud s ním nesouhlasíš. "
                    f"URL (platnost 1 hodina): {presigned}"
                )
                pplx_url = f"https://www.perplexity.ai/search?q={urllib.parse.quote(short_prompt)}"
                components.html(
                    f'<script>window.open({json.dumps(pplx_url)}, "_blank", "noopener,noreferrer");</script>',
                    height=0
                )
                st.info("📋 Pokud Perplexity obsah nenačte, použijte manuální cestu výše.")
            else:
                st.error("Nepodařilo se vygenerovat presigned URL.")

def render_critique_ui(available_providers_list):
    """UI nezávislé kritiky – volá se za render_downloads()."""
    if not st.session_state.md_content:
        return

    st.divider()
    st.subheader("🔍 Nezávislá kritika diskuze")
    st.caption("Nechte diskuzi a verdikt rozhodčího posoudit další nezávislou AI.")

    # Tlačítko pro otevření UI – BEZ st.rerun()
    if not st.session_state.show_critique_ui and not st.session_state.critique_md:
        if st.button("Spustit nezávislou kritiku", type="primary", use_container_width=True):
            st.session_state.show_critique_ui = True
            # ŽÁDNÝ st.rerun() – vykreslí se ve stejném běhu

    # UI se zobrazí, pokud je aktivní
    if not (st.session_state.show_critique_ui or st.session_state.critique_md):
        return

    # Výběr kritika
    options = []
    if "Gemini" in available_providers_list:
        options.append("Gemini (API)")
    if "Mistral" in available_providers_list:
        options.append("Mistral (API)")
    if "NVIDIA NIM" in available_providers_list:
        options.append("NVIDIA NIM (API)")
    options.append("Perplexity (externí – nový panel)")

    if not available_providers_list:
        st.warning("⚠️ Nemáte zadán žádný API klíč – můžete použít pouze externí Perplexity.")

    selected = st.selectbox("Vyberte kritika:", options, key="critique_provider_select")
    is_perplexity = "Perplexity" in selected

    if not is_perplexity:
        provider = selected.replace(" (API)", "")
        if st.button(f"🚀 Generovat kritiku pomocí {provider}", type="primary", use_container_width=True):
            keys = {
                "gemini": st.session_state.gemini_key.strip(),
                "nim": st.session_state.nim_key.strip(),
                "mistral": st.session_state.mistral_key.strip(),
            }
            with st.spinner(f"{provider} generuje nezávislou kritiku..."):
                try:
                    critique_text, model_used = call_critique_api(
                        CRITIQUE_SYSTEM_PROMPT,
                        build_critique_prompt(st.session_state.md_content, st.session_state.current_topic),
                        provider,
                        keys,
                    )
                    ok, err, base_name = save_critique_result(critique_text, model_used)
                    if ok:
                        st.success(f"✅ Kritika uložena na R2 do `VERDICT/markdown/{base_name}.md` a `VERDICT/pdf/{base_name}.pdf`.")
                    else:
                        st.warning(f"⚠️ Kritika vygenerována, ale uložení na R2 selhalo: {err}")
                    # ŽÁDNÝ st.rerun() – UI kritiky se vykreslí níže
                except Exception as e:
                    st.error(f"Chyba při generování kritiky: {e}")

    else:
        render_perplexity_ui()

    # Zobrazení hotové kritiky
    if st.session_state.critique_md:
        st.divider()
        st.subheader("✅ Hotová kritika")
        st.caption(f"Uloženo jako: `VERDICT/markdown/{st.session_state.critique_base}.md` a `VERDICT/pdf/{st.session_state.critique_base}.pdf`")

        md_b64 = base64.b64encode(st.session_state.critique_md.encode('utf-8')).decode('utf-8')
        pdf_b64 = base64.b64encode(st.session_state.critique_pdf).decode('utf-8')
        base_name = st.session_state.critique_base

        st.markdown(
            f'<div style="display:flex; gap:10px; margin:10px 0;">'
            f'<a href="data:application/octet-stream;base64,{md_b64}" download="{base_name}.md" '
            f'style="flex:1; text-align:center; padding:10px; background:#f0f2f6; color:#31333f; text-decoration:none; border-radius:5px; border:1px solid #d6d6d6;">📥 Kritika (.md)</a>'
            f'<a href="data:application/pdf;base64,{pdf_b64}" download="{base_name}.pdf" '
            f'style="flex:1; text-align:center; padding:10px; background:#ff4b4b; color:white; text-decoration:none; border-radius:5px;">📄 Kritika (.pdf)</a>'
            f'</div>',
            unsafe_allow_html=True
        )

        # Tlačítko pro otevření nového panelu s kritikou
        html_full = build_critique_html(st.session_state.critique_md, base_name)
        html_b64 = base64.b64encode(html_full.encode('utf-8')).decode('utf-8')

        components.html(
            f'<button onclick="openCritique()" '
            f'style="padding:12px 24px; background:#4b8bf4; color:white; border:none; border-radius:6px; '
            f'cursor:pointer; font-size:16px; width:100%; font-weight:600; font-family:inherit;">'
            f'🔗 Otevřít kritiku v novém panelu prohlížeče</button>'
            f'<script>'
            f'function openCritique() {{'
            f'  try {{'
            f'    const binary = atob("{html_b64}");'
            f'    const bytes = new Uint8Array(binary.length);'
            f'    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);'
            f'    const html = new TextDecoder("utf-8").decode(bytes);'
            f'    const blob = new Blob([html], {{type: "text/html;charset=utf-8"}});'
            f'    const url = URL.createObjectURL(blob);'
            f'    const w = window.open(url, "_blank", "noopener,noreferrer");'
            f'    if (!w) alert("⚠️ Panel byl zablokován. Povolte vyskakovací okna pro tuto stránku.");'
            f'  }} catch (e) {{ alert("Chyba: " + e.message); }}'
            f'}}'
            f'</script>',
            height=70
        )

        with st.expander("📄 Náhled kritiky", expanded=False):
            st.markdown(st.session_state.critique_md)

# Načtení klíčů ze Secrets (pokud jsou nastaveny)
try: secret_gemini = st.secrets["GEMINI_API_KEY"]
except: secret_gemini = ""
try: secret_nim = st.secrets["NVIDIA_NIM_API_KEY"]
except: secret_nim = ""
try: secret_mistral = st.secrets["MISTRAL_API_KEY"]
except: secret_mistral = ""

# --- 3. POSTRANNÍ PANEL ---
with st.sidebar:
    st.header("🧭 Navigace")
    app_mode = st.radio("Vyberte sekci:", ["⚔️ Debatní Aréna", "❓ Nápověda a návody"], index=0)
    st.divider()

    if app_mode == "⚔️ Debatní Aréna":
        st.header("⚙️ Nastavení debaty")
        st.session_state.gemini_key = st.text_input("🔑 Gemini API klíč:", type="password", value=st.session_state.gemini_key or secret_gemini, placeholder="Nepovinné (AIzaSy...)")
        st.session_state.nim_key = st.text_input("🔑 NVIDIA NIM API klíč:", type="password", value=st.session_state.nim_key or secret_nim, placeholder="Nepovinné (nvapi-...)")
        st.session_state.mistral_key = st.text_input("🔑 Mistral API klíč:", type="password", value=st.session_state.mistral_key or secret_mistral, placeholder="Nepovinné (...)")

        available_providers = []
        if st.session_state.gemini_key.strip(): available_providers.append("Gemini")
        if st.session_state.nim_key.strip(): available_providers.append("NVIDIA NIM")
        if st.session_state.mistral_key.strip(): available_providers.append("Mistral")
        select_options = available_providers if available_providers else ["(Zadejte alespoň jeden klíč)"]

        if st.session_state.provider_a not in select_options: st.session_state.provider_a = select_options[0]
        if st.session_state.provider_b not in select_options: st.session_state.provider_b = select_options[0]
        if st.session_state.provider_mod not in select_options: st.session_state.provider_mod = select_options[0]

        st.divider()
        st.session_state.max_rounds = st.slider("Počet výměn názorů (kol)", min_value=2, max_value=30, value=st.session_state.max_rounds)
        memory_limit = 10

        st.subheader("Osobnost A")
        st.session_state.role_a_name = st.text_input("Jméno A", value=st.session_state.role_a_name, placeholder="Zde napiš mluvčího...")
        st.session_state.provider_a = st.selectbox("Poskytovatel A:", select_options, index=select_options.index(st.session_state.provider_a) if st.session_state.provider_a in select_options else 0)
        st.session_state.input_type_a = st.radio("Způsob zadání instrukcí pro A:", ["Ručně", "Nahrát soubor"], index=0 if st.session_state.input_type_a == "Ručně" else 1)
        if st.session_state.input_type_a == "Ručně":
            st.session_state.role_a_prompt = st.text_area("Instrukce pro A", value=st.session_state.role_a_prompt, placeholder="Zde napiš, jak se má mluvčí chovat...")
        else:
            file_a = st.file_uploader("Nahrajte charakteristiku A (PDF, MD, TXT)", type=["pdf", "md", "txt"], key="file_a")
            if file_a: st.session_state.role_a_prompt = extract_text_from_file(file_a)

        st.subheader("Osobnost B")
        st.session_state.role_b_name = st.text_input("Jméno B", value=st.session_state.role_b_name, placeholder="Zde napiš mluvčího...")
        st.session_state.provider_b = st.selectbox("Poskytovatel B:", select_options, index=select_options.index(st.session_state.provider_b) if st.session_state.provider_b in select_options else 0)
        st.session_state.input_type_b = st.radio("Způsob zadání instrukcí pro B:", ["Ručně", "Nahrát soubor"], index=0 if st.session_state.input_type_b == "Ručně" else 1)
        if st.session_state.input_type_b == "Ručně":
            st.session_state.role_b_prompt = st.text_area("Instrukce pro B", value=st.session_state.role_b_prompt, placeholder="Zde napiš, jak se má mluvčí chovat...")
        else:
            file_b = st.file_uploader("Nahrajte charakteristiku B (PDF, MD, TXT)", type=["pdf", "md", "txt"], key="file_b")
            if file_b: st.session_state.role_b_prompt = extract_text_from_file(file_b)

        st.subheader("Moderátor (Rozhodčí)")
        st.session_state.provider_mod = st.selectbox("Poskytovatel moderátora:", select_options, index=select_options.index(st.session_state.provider_mod) if st.session_state.provider_mod in select_options else 0)

# --- 4. OBSAH JEDNOTLIVÝCH SEKCI ---

if app_mode == "❓ Nápověda a návody":
    st.title("📖 Nápověda a návody")
    st.markdown("""
    Vítejte v AI Debatní Aréně! Zde najdete všechny informace k tomu, jak aplikaci ovládat a kde získat potřebné přístupy.

    ## 🚀 Obecný postup
    1. **Získejte API klíč:** Vyberte si alespoň jednoho poskytovatele AI (Gemini, NVIDIA NIM nebo Mistral). Postupy najdete níže.
    2. **Vložte klíč:** V postranním panelu vložte váš klíč do příslušného pole.
    3. **Nastavte osobnosti:** Zadejte jména diskutujících, vyberte jejich poskytovatele a napište instrukce (nebo nahrajte PDF/MD soubor).
    4. **Zadejte téma a spusťte:** Napište téma diskuze (nebo nahrajte dokumenty), zvolte počet kol a klikněte na **Spustit diskuzi**.
    5. **Exportujte:** Po skončení debaty si můžete průběh a verdikt rozhodčího stáhnout jako Markdown nebo PDF.
    6. **Nezávislá kritika:** Po skončení debaty můžete nechat diskuzi posoudit další AI – buď přes API (Gemini/Mistral/NVIDIA), nebo přes externí Perplexity.

    ---
    ## 🔑 Kde získat API klíče a jaké jsou limity
    """)

    with st.expander("🔵 Google Gemini (Doporučeno pro vyhledávání)"):
        st.markdown("""
        **Jak získat klíč:**
        1. Jděte na [Google AI Studio](https://aistudio.google.com/app/apikey).
        2. Přihlaste se vaším Google účtem.
        3. Klikněte na **Create API key** (Vytvořit API klíč).
        4. Zkopírujte vygenerovaný klíč (začíná na `AIza...`).

        **Limity (Free tier):**
        *   Rychlost: ~15 požadavků za minutu (RPM) pro Flash-Lite modely.
        *   Denní limit: 500 až 1 500 požadavků (podle modelu).
        *   *Upozornění:* Pokud zapnete vyhledávání na internetu, spotřebováváte speciální kvótu, která se může vyčerpat rychleji a způsobit chybu 429.
        """)

    with st.expander("🟢 NVIDIA NIM (Doporučeno pro rychlost)"):
        st.markdown("""
        **Jak získat klíč:**
        1. Jděte na [NVIDIA Build](https://build.nvidia.com/).
        2. Zaregistrujte se.
        3. Klikněte na své jméno vpravo nahoře -> **API Keys**.
        4. Vygenerujte nový klíč (začíná na `nvapi-...`).
        *(Ujistěte se, že váš klíč má oprávnění "Public API Endpoints", jinak se mohou objevit chyby 404.)*

        **Limity (Free tier):**
        *   Rychlost: ~40 požadavků za minutu (RPM).
        *   Tokeny: Bez přísného limitu (velmi štědré).
        """)

    with st.expander("🟠 Mistral AI (Doporučeno pro dlouhé texty)"):
        st.markdown("""
        **Jak získat klíč:**
        1. Jděte na [Mistral Console](https://console.mistral.ai/).
        2. Zaregistrujte se (ověření telefonem, platební karta není nutná).
        3. V levém menu přejděte na **API Keys**.
        4. Klikněte na **Create new key** (Vytvořit nový klíč).

        **Limity (Free tier):**
        *   Rychlost: Záleží na modelu (obvykle 1 až 12 požadavků za sekundu).
        *   Denní limit: Několik tisíc požadavků.
        """)

    with st.expander("🟣 Nezávislá kritika – jak to funguje"):
        st.markdown("""
        Po skončení debaty si můžete nechat diskuzi a verdikt rozhodčího posoudit další AI:

        **API varianta (Gemini, Mistral, NVIDIA NIM):**
        * Plně automatizované – server zavolá API, vygeneruje kritiku a uloží ji na R2 do `VERDICT/markdown/` a `VERDICT/pdf/`.

        **Externí varianta (Perplexity):**
        * Perplexity **nespolehlivě načítá `.md` soubory z URL**. Proto doporučujeme **manuální cestu**:
          1. Stáhněte si PDF diskuze (tlačítko v UI).
          2. Otevřete Perplexity v novém panelu.
          3. Přiložte PDF a vložte připravený prompt.
          4. Výsledek zkopírujte zpět do aplikace.
        * V aplikaci je i **pokročilá možnost** s presigned URL (dočasný podepsaný odkaz na PDF v R2), ale ta nemusí fungovat.

        **Výhody presigned URL:** Váš R2 bucket zůstává **soukromý** – presigned URL je dočasná (1 h) a nepředvídatelná.
        """)

elif app_mode == "⚔️ Debatní Aréna":
    st.title("🗣️ AI Debatní Aréna")
    st.caption("Automatizovaná diskuze dvou AI osobností s dynamickým výběrem modelů.")

    # --- ZADÁNÍ TÉMATU ---
    st.session_state.topic_input_type = st.radio("Způsob zadání tématu:", ["Ručně", "Nahrát soubor(y)"], index=0 if st.session_state.topic_input_type == "Ručně" else 1)
    
    if st.session_state.topic_input_type == "Ručně":
        st.session_state.topic_input = st.text_input("Téma diskuze:", value=st.session_state.topic_input, placeholder="Zadej o čem mají diskutovat...")
        topic = st.session_state.topic_input
        st.session_state.topic_document_text = ""
        st.session_state.uploaded_files_hash = ""
    else:
        st.session_state.topic_input = st.text_input("Název diskuze (pro export a název souboru):", value=st.session_state.topic_input, placeholder="Např.: Analýza výroční zprávy...")
        topic = st.session_state.topic_input
        topic_files = st.file_uploader("Nahrajte podklady pro diskuzi (PDF, MD, TXT)", type=["pdf", "md", "txt"], accept_multiple_files=True)
        
        if topic_files:
            file_names = "_".join([f.name for f in topic_files])
            if st.session_state.uploaded_files_hash != file_names:
                with st.spinner("Načítám a zpracovávám dokumenty..."):
                    full_text = ""
                    for f in topic_files:
                        full_text += f"--- Dokument: {f.name} ---\n" + extract_text_from_file(f) + "\n\n"
                    st.session_state.topic_document_text = full_text
                    st.session_state.uploaded_files_hash = file_names
                    st.success(f"✅ Úspěšně načteno {len(topic_files)} dokumentů.")

    if st.button("🚀 Spustit diskuzi", type="primary"):
        if not available_providers:
            st.error("⚠️ Pro spuštění diskuze musíte nejprve zadat alespoň jeden API klíč!")
            st.stop()
        if not topic.strip() or not st.session_state.role_a_name.strip() or not st.session_state.role_a_prompt.strip() or not st.session_state.role_b_name.strip() or not st.session_state.role_b_prompt.strip():
            st.error("⚠️ Pro spuštění diskuze musíte vyplnit téma a nastavení pro obě osobnosti!")
            st.stop()
        if st.session_state.topic_input_type == "Nahrát soubor(y)" and not st.session_state.topic_document_text:
            st.error("⚠️ Musíte nahrát alespoň jeden dokument pro diskuzi!")
            st.stop()

        st.session_state.full_history = []
        st.session_state.current_topic = topic
        st.session_state.debate_active = False
        st.session_state.md_content = ""
        st.session_state.pdf_bytes = b""
        st.session_state.file_base_name = "debata"
        st.session_state.topic_summary = ""
        reset_critique_state()

        try:
            gemini_client = genai.Client(api_key=st.session_state.gemini_key.strip(), http_options=types.HttpOptions(timeout=180000)) if "Gemini" in available_providers else None
            nim_client = OpenAI(api_key=st.session_state.nim_key.strip(), base_url="https://integrate.api.nvidia.com/v1", timeout=180.0) if "NVIDIA NIM" in available_providers else None
            mistral_client = OpenAI(api_key=st.session_state.mistral_key.strip(), base_url="https://api.mistral.ai/v1", timeout=180.0) if "Mistral" in available_providers else None
        except Exception as e:
            st.error(f"Chyba při inicializaci klienta: {e}")
            st.stop()

        with st.spinner("Zjišťuji aktuálně dostupné modely..."):
            gemini_models = get_available_gemini_models(gemini_client) if gemini_client else []
            nvidia_models = get_available_nvidia_models(nim_client) if nim_client else []
            mistral_models = get_available_mistral_models(mistral_client) if mistral_client else []

        model_info = []
        if gemini_models: model_info.append(f"Gemini: `{', '.join(gemini_models)}`")
        if nvidia_models: model_info.append(f"NVIDIA: `{', '.join(nvidia_models)}`")
        if mistral_models: model_info.append(f"Mistral: `{', '.join(mistral_models)}`")
        st.info("Použité modely: " + " | ".join(model_info))

        st.divider()
        st.markdown(f"### 📌 Téma: *{topic}*")

        chat_container = st.container()
        progress_bar = st.progress(0)

        def call_ai(system_prompt, user_prompt, provider):
            full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"
            if provider == "Gemini":
                config = types.GenerateContentConfig()
                last_error = None
                for model_name in gemini_models:
                    for attempt in range(2):
                        try:
                            response = gemini_client.models.generate_content(model=model_name, contents=full_prompt, config=config)
                            if not response.text or not response.text.strip():
                                raise Exception("Model Gemini vrátil prázdnou odpověď.")
                            return response.text, model_name
                        except Exception as e:
                            last_error = e
                            if getattr(e, 'code', None) in [503, 429] and attempt == 0: time.sleep(2)
                            else: break
                raise Exception(f"Všechny Gemini modely selhaly: {last_error}")

            elif provider == "NVIDIA NIM":
                messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
                last_error = None
                for model_name in nvidia_models:
                    for attempt in range(2):
                        try:
                            response = nim_client.chat.completions.create(model=model_name, messages=messages, temperature=0.7, extra_body={"chat_template_kwargs":{"enable_thinking":True}})
                            content = response.choices[0].message.content
                            if not content or not content.strip(): raise Exception("Model NVIDIA vrátil prázdnou odpověď.")
                            return content, model_name
                        except Exception as e:
                            last_error = e
                            if attempt == 0: time.sleep(2)
                            else: break
                raise Exception(f"Všechny NVIDIA modely selhaly: {last_error}")

            elif provider == "Mistral":
                messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
                last_error = None
                for model_name in mistral_models:
                    for attempt in range(2):
                        try:
                            response = mistral_client.chat.completions.create(model=model_name, messages=messages, temperature=0.7)
                            content = response.choices[0].message.content
                            if not content or not content.strip(): raise Exception("Model Mistral vrátil prázdnou odpověď.")
                            return content, model_name
                        except Exception as e:
                            last_error = e
                            if attempt == 0: time.sleep(2)
                            else: break
                raise Exception(f"Všechny Mistral modely selhaly: {last_error}")

        # --- GENEROVÁNÍ SOUHRNU DOKUMENTŮ ---
        if st.session_state.topic_input_type == "Nahrát soubor(y)" and st.session_state.topic_document_text:
            with st.spinner("Analyzuji nahrané dokumenty a připravuji souhrn s citacemi..."):
                summary_prompt = (
                    "Jsi expert na analýzu dokumentů. Z následujících textů vytvoř strukturovaný souhrn. "
                    "Uveď hlavní teze, klíčová fakta a přímé citace, které by měly být použity v diskuzi. "
                    "Tento souhrn bude sloužit jako podklad pro debatující strany."
                )
                try:
                    priority = []
                    if "Gemini" in available_providers: priority.append("Gemini")
                    if "Mistral" in available_providers: priority.append("Mistral")
                    if "NVIDIA NIM" in available_providers: priority.append("NVIDIA NIM")
                    
                    summary_text = None
                    for p in priority:
                        try:
                            summary_text, _ = call_ai(summary_prompt, st.session_state.topic_document_text, p)
                            break
                        except Exception:
                            continue
                    if summary_text:
                        st.session_state.topic_summary = summary_text
                    else:
                        st.session_state.topic_summary = "Nepodařilo se vygenerovat souhrn dokumentů."
                except Exception as e:
                    st.warning(f"Chyba při generování souhrnu: {e}")
                    st.session_state.topic_summary = "Souhrn dokumentů se nepodařilo vygenerovat."
            
            st.markdown("#### 📄 Úvodní souhrn dokumentů")
            st.info(st.session_state.topic_summary)
            st.divider()

        debate_context_intro = f"Téma diskuze: '{topic}'.\n\n"
        if st.session_state.topic_summary:
            debate_context_intro += f"Zde je souhrn z podkladových dokumentů, ze kterého vycházej:\n{st.session_state.topic_summary}\n\n"

        with chat_container.chat_message("user", avatar="🔵"):
            st.markdown(f"**{st.session_state.role_a_name}:**")
            with st.spinner("Zahajuje diskuzi..."):
                resp_a, mod_a = call_ai(st.session_state.role_a_prompt, debate_context_intro + "Zahaj diskuzi a předlož svůj první argument.", st.session_state.provider_a)
            st.markdown(resp_a)
            st.caption(f"🤖 `{mod_a}`")
        st.session_state.full_history.append((st.session_state.role_a_name, resp_a, mod_a))

        # Smyčka debaty
        for r in range(st.session_state.max_rounds):
            progress_bar.progress((r + 1) / st.session_state.max_rounds)
            time.sleep(get_delay_for_provider(st.session_state.provider_b))
            
            context_b = debate_context_intro + "Kontext diskuze:\n" + "\n".join([f"{s}: {t}" for s, t, m in st.session_state.full_history[-memory_limit:]]) + f"\nNyní jsi na řadě ty ({st.session_state.role_b_name}). Reaguj na argumenty oponenta."
            with chat_container.chat_message("assistant", avatar="🔴"):
                st.markdown(f"**{st.session_state.role_b_name}:**")
                with st.spinner("Reaguje..."):
                    resp_b, mod_b = call_ai(st.session_state.role_b_prompt, context_b, st.session_state.provider_b)
                st.markdown(resp_b)
                st.caption(f"🤖 `{mod_b}`")
            st.session_state.full_history.append((st.session_state.role_b_name, resp_b, mod_b))

            if r < st.session_state.max_rounds - 1:
                time.sleep(get_delay_for_provider(st.session_state.provider_a))
                context_a = debate_context_intro + "Kontext diskuze:\n" + "\n".join([f"{s}: {t}" for s, t, m in st.session_state.full_history[-memory_limit:]]) + f"\nNyní jsi na řadě ty ({st.session_state.role_a_name}). Reaguj na argumenty oponenta."
                with chat_container.chat_message("user", avatar="🔵"):
                    st.markdown(f"**{st.session_state.role_a_name}:**")
                    with st.spinner("Reaguje..."):
                        resp_a, mod_a = call_ai(st.session_state.role_a_prompt, context_a, st.session_state.provider_a)
                    st.markdown(resp_a)
                    st.caption(f"🤖 `{mod_a}`")
                st.session_state.full_history.append((st.session_state.role_a_name, resp_a, mod_a))

        progress_bar.progress(1.0)
        time.sleep(get_delay_for_provider(st.session_state.provider_mod))

        summary_context = (
            f"ZADÁNÍ TÉMATU: '{st.session_state.current_topic}'\n\n"
            f"SOUHRN DOKUMENTŮ: {st.session_state.topic_summary}\n\n"
            "PRŮBĚH DEBATY:\n" + "\n".join([f"{s}: {t}" for s, t, m in st.session_state.full_history])
        )
        judge_prompt = (
            "Jsi přísný a nestranný rozhodčí. Zhodnoť průběh debaty. "
            "NEJDŘÍVE SI PEČLIVĚ PŘEČTI 'ZADÁNÍ TÉMATU'. "
            "Pokud zadání obsahuje konkrétní požadavek na formu rozhodnutí (např. 'vyber jednu variantu', 'rozhodni pro jednoho', nebo naopak 'navrhni kompromis'), "
            "MUSÍŠ tento pokyn bezpodmínečně dodržet. "
            "Vždy jasně vysvětli, proč jsi se takto rozhodl."
        )
        
        with st.spinner("Rozhodčí vyhodnocuje argumenty..."):
            try:
                final_sum, mod_mod = call_ai(judge_prompt, summary_context, st.session_state.provider_mod)
            except Exception as e:
                final_sum = f"Rozhodčí se nemohl vyjádřit. Došlo k chybě: {e}"
                mod_mod = "Chyba API"

        st.session_state.final_summary = final_sum
        st.session_state.model_mod_used = mod_mod
        st.session_state.debate_active = True

        with chat_container.chat_message("assistant", avatar="⚖️"):
            st.markdown("**Rozhodčí:**")
            st.markdown(final_sum)
            st.caption(f"🤖 `{mod_mod}`")
            
        with st.spinner("Připravuji soubory a nahrávám na Cloudflare R2..."):
            md_history = ""
            for sender, text, model in st.session_state.full_history:
                md_history += f"### {sender}\n{text}\n\n<small>Použitý model: {model}</small>\n\n---\n\n"
            
            md_content = f"# Diskuze: {st.session_state.current_topic}\n\n**Datum:** {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            if st.session_state.topic_summary:
                md_content += f"## Úvodní souhrn dokumentů\n\n{st.session_state.topic_summary}\n\n---\n\n"
            md_content += md_history + f"### Rozhodčí\n{final_sum}\n\n<small>Použitý model: {mod_mod}</small>"
            
            st.session_state.md_content = md_content
            st.session_state.pdf_bytes = generate_pdf(st.session_state.md_content)

            try:
                counter = get_next_counter()
            except Exception as e:
                counter = f"{random.randint(10000, 99999):05d}"

            filename_base = generate_filename_from_topic(st.session_state.current_topic, call_ai, available_providers)
            full_base = f"{counter}_{filename_base}"
            st.session_state.file_base_name = full_base

            try:
                s3 = get_r2_client()
                bucket = st.secrets["R2_BUCKET_NAME"]
                s3.put_object(Bucket=bucket, Key=f"markdown/{full_base}.md", Body=st.session_state.md_content.encode("utf-8"), ContentType="text/markdown")
                s3.put_object(Bucket=bucket, Key=f"pdf/{full_base}.pdf", Body=st.session_state.pdf_bytes, ContentType="application/pdf")
                st.success(f"✅ Soubory nahrány na Cloudflare R2 jako `{full_base}.md` a `{full_base}.pdf`.")
            except Exception as e:
                st.error(f"❌ Nahrání na R2 selhalo: {e}")
        
        st.divider()
        render_downloads()
        
        # --- Nezávislá kritika ---
        render_critique_ui(available_providers)
        
        st.divider()
        if st.button("🔄 Nová debata", use_container_width=True):
            st.session_state.debate_active = False
            st.session_state.full_history = []
            st.session_state.final_summary = ""
            st.session_state.md_content = ""
            st.session_state.pdf_bytes = b""
            st.session_state.file_base_name = "debata"
            st.session_state.topic_document_text = ""
            st.session_state.topic_summary = ""
            st.session_state.uploaded_files_hash = ""
            reset_critique_state()
            st.rerun()  # tady je rerun OK – uživatel čeká kompletní reset
            
        st.stop()

    if st.session_state.debate_active:
        st.divider()
        st.markdown(f"### 📌 Téma: *{st.session_state.current_topic}*")
        
        if st.session_state.topic_summary:
            with st.expander("📄 Zobrazit úvodní souhrn dokumentů", expanded=False):
                st.markdown(st.session_state.topic_summary)

        for i, (sender, text, model_used) in enumerate(st.session_state.full_history):
            avatar = "🔵" if i % 2 == 0 else "🔴"
            role = "user" if i % 2 == 0 else "assistant"
            with st.chat_message(role, avatar=avatar):
                st.markdown(f"**{sender}:**\n\n{text}")
                st.caption(f"🤖 `{model_used}`")

        with st.chat_message("assistant", avatar="⚖️"):
            st.markdown("**Rozhodčí:**")
            st.markdown(st.session_state.final_summary)
            st.caption(f"🤖 `{st.session_state.model_mod_used}`")

        st.divider()
        render_downloads()
        
        # --- Nezávislá kritika ---
        render_critique_ui(available_providers)
                
        st.divider()
        if st.button("🔄 Nová debata", use_container_width=True):
            st.session_state.debate_active = False
            st.session_state.full_history = []
            st.session_state.final_summary = ""
            st.session_state.md_content = ""
            st.session_state.pdf_bytes = b""
            st.session_state.file_base_name = "debata"
            st.session_state.topic_document_text = ""
            st.session_state.topic_summary = ""
            st.session_state.uploaded_files_hash = ""
            reset_critique_state()
            st.rerun()  # tady je rerun OK – uživatel čeká kompletní reset
